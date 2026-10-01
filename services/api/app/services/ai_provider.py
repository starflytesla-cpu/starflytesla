"""所有 AI 呼叫的唯一入口：選模型、發請求、解析用量、估算成本、寫入 usage_ledger。

- chat()：OpenAI 相容的 /chat/completions（DeepSeek、豆包 BytePlus、OpenRouter、kie.ai 的 Gemini）
- tts()：文字轉語音（目前支援 kie.ai 的 ElevenLabs，建立任務後輪詢結果）

kie.ai 的差異在 _kie_* 函式處理：每個聊天模型有自己的網址路徑、圖片要先上傳成網址、以點數計費。
不論成功或失敗都會寫一筆成本記錄。
"""

import json
import time
import uuid
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from decimal import Decimal

import httpx
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.errors import AppError, bad_request, upstream_error
from app.models import ChannelModel, ModelChannel, UsageLedger, User
from app.security import decrypt_secret, validate_upstream_url

CHAT_CAPABILITIES = {"text", "vision"}
CAPABILITY_NAMES = {"text": "文字", "vision": "看圖", "tts": "配音", "embedding": "向量"}


@dataclass
class ChatResult:
    content: str
    input_tokens: int
    output_tokens: int
    duration_ms: int
    cost_micros: int | None


@dataclass
class TtsResult:
    audio: bytes
    characters: int
    duration_ms: int
    cost_micros: int | None


def estimate_cost_micros(model: ChannelModel, input_tokens: int, output_tokens: int) -> int | None:
    if model.input_price_per_m is None or model.output_price_per_m is None:
        return None
    # 價格是「每百萬 token 的美元」，成本單位是「百萬分之一美元」，兩個百萬剛好相消。
    cost = Decimal(input_tokens) * model.input_price_per_m + Decimal(
        output_tokens
    ) * model.output_price_per_m
    return int(cost.to_integral_value())


def credits_to_micros(credits) -> int | None:
    """kie.ai 點數換算成百萬分之一美元（單價見設定 KIE_USD_PER_CREDIT）。"""
    try:
        value = Decimal(str(credits))
    except (ArithmeticError, ValueError):
        return None
    return int((value * Decimal(str(get_settings().kie_usd_per_credit)) * 1_000_000).to_integral_value())


def default_model(db: Session, tenant_id: str, capability: str) -> ChannelModel:
    stmt = (
        select(ChannelModel)
        .join(ModelChannel)
        .where(
            ModelChannel.tenant_id == tenant_id,
            ModelChannel.enabled.is_(True),
            ChannelModel.enabled.is_(True),
            ChannelModel.capability == capability,
        )
        .order_by(ChannelModel.is_default.desc(), ChannelModel.created_at)
    )
    model = db.scalars(stmt).first()
    if not model:
        name = CAPABILITY_NAMES.get(capability, capability)
        raise bad_request(f"尚未設定可用的「{name}」模型，請到模型渠道新增", "no_model")
    return model


def _upstream_message(response: httpx.Response) -> str:
    try:
        body = response.json()
        error = body.get("error")
        detail = (error.get("message") if isinstance(error, dict) else error) or body.get("message") or body.get("msg") or ""
    except (ValueError, AttributeError):
        detail = ""
    detail = str(detail)[:200]
    return f"上游回應 HTTP {response.status_code}" + (f"：{detail}" if detail else "")


def _check_usable(model: ChannelModel) -> str:
    """檢查渠道與模型可用，回傳解密後的 API Key。"""
    channel = model.channel
    if not channel.enabled or not model.enabled:
        raise bad_request("渠道或模型已停用", "model_disabled")
    api_key = decrypt_secret(channel.api_key_encrypted)
    if not api_key:
        raise bad_request("這個渠道還沒有填寫 API Key", "missing_api_key")
    return api_key


@contextmanager
def _ledger(db: Session, model: ChannelModel, action: str, source: str, user: User | None) -> Iterator[UsageLedger]:
    """包住一次上游呼叫：成功時由呼叫端填入用量與成本；失敗時成本記 0。無論如何都寫入一筆。"""
    channel = model.channel
    entry = UsageLedger(
        tenant_id=channel.tenant_id,
        user_id=user.id if user else None,
        action=action,
        source=source,
        channel_id=channel.id,
        provider=channel.provider,
        model_key=model.model_key,
        status="failed",
    )
    started = time.monotonic()
    try:
        yield entry
        entry.status = "succeeded"
    except AppError as exc:
        entry.error = exc.message[:500]
        # 失敗的呼叫沒有產生用量，成本記為 0，而不是「價格未知」。
        entry.input_tokens = entry.output_tokens = 0
        entry.cost_micros = 0
        raise
    finally:
        entry.duration_ms = int((time.monotonic() - started) * 1000)
        db.add(entry)
        db.commit()


def _send(method: str, url: str, api_key: str, body: dict | None = None, *, params: dict | None = None) -> httpx.Response:
    try:
        return httpx.request(
            method,
            url,
            headers={"Authorization": f"Bearer {api_key}"},
            json=body,
            params=params,
            timeout=get_settings().upstream_timeout_seconds,
            follow_redirects=False,
        )
    except httpx.TimeoutException:
        raise upstream_error("上游服務逾時，請稍後再試", "upstream_timeout") from None
    except httpx.HTTPError as exc:
        raise upstream_error(f"無法連線到上游服務：{type(exc).__name__}") from None


def _json(response: httpx.Response) -> dict:
    if response.status_code >= 400:
        raise upstream_error(_upstream_message(response))
    try:
        body = response.json()
    except ValueError:
        raise upstream_error("上游回應格式無法解析") from None
    if not isinstance(body, dict):
        raise upstream_error("上游回應格式無法解析")
    return body


# ---------------------------------------------------------------- 對話（文字 / 看圖）
# kie.ai 的檔案上傳服務（免費，檔案 3 天後自動刪除）。看圖模型只接受圖片網址，
# 而素材的關鍵畫面在登入保護之後，所以先上傳到這裡取得暫時網址。
KIE_UPLOAD_URL = "https://kieai.redpandaai.co/api/file-base64-upload"


def _kie_upload_image(data_url: str, api_key: str) -> str:
    response = _send(
        "POST",
        validate_upstream_url(KIE_UPLOAD_URL),
        api_key,
        {"base64Data": data_url, "uploadPath": "starfly/keyframes", "fileName": f"{uuid.uuid4().hex}.jpg"},
    )
    try:
        body = response.json()
        url = body["data"]["downloadUrl"] if body.get("success") else ""
    except (ValueError, KeyError, TypeError):
        url = ""
    if response.status_code >= 400 or not url:
        raise upstream_error("圖片上傳到 kie.ai 失敗：" + _upstream_message(response).removeprefix("上游回應 "))
    return url


def _kie_messages(messages: list[dict], api_key: str) -> list[dict]:
    """把訊息裡的 data: 圖片換成 kie 上傳後的網址。"""
    result = []
    for message in messages:
        content = message.get("content")
        if isinstance(content, list):
            parts = []
            for part in content:
                url = (part.get("image_url") or {}).get("url", "") if part.get("type") == "image_url" else ""
                if url.startswith("data:"):
                    part = {"type": "image_url", "image_url": {"url": _kie_upload_image(url, api_key)}}
                parts.append(part)
            message = {**message, "content": parts}
        result.append(message)
    return result


def _chat_request(model: ChannelModel, base_url: str, api_key: str, messages: list[dict], max_tokens: int) -> tuple[str, dict]:
    """回傳 (請求網址, 請求內容)。一律關閉串流（kie 預設是串流）。"""
    if model.channel.provider == "kie":
        # kie 每個模型有自己的路徑，例如 https://api.kie.ai/gemini-3-8-flash-openai/v1/chat/completions；
        # Gemini 會先思考再回答，max_tokens 會把思考也算進去，改用 reasoning_effort 控制成本。
        url = f"{base_url}/{model.model_key}/v1/chat/completions"
        return url, {"messages": _kie_messages(messages, api_key), "stream": False, "reasoning_effort": "low"}
    body = {"model": model.model_key, "messages": messages, "max_tokens": max_tokens, "stream": False}
    return f"{base_url}/chat/completions", body


def _parse_chat(body: dict) -> tuple[str, int, int]:
    """回傳 (回覆文字, 輸入 token, 輸出 token)。支援 OpenAI 格式，以及 kie 有時回傳的 Gemini 原生格式。"""
    if "choices" in body:
        content = body["choices"][0]["message"].get("content") or ""
        usage = body.get("usage") or {}
        return content, int(usage.get("prompt_tokens") or 0), int(usage.get("completion_tokens") or 0)
    parts = body["candidates"][0]["content"].get("parts") or []
    content = "".join(p.get("text", "") for p in parts if not p.get("thought"))
    meta = body.get("usageMetadata") or {}
    output = int(meta.get("candidatesTokenCount") or 0) + int(meta.get("thoughtsTokenCount") or 0)
    return content, int(meta.get("promptTokenCount") or 0), output


def chat(
    db: Session,
    model: ChannelModel,
    messages: list[dict],
    *,
    source: str,
    user: User | None,
    max_tokens: int = 1024,
) -> ChatResult:
    if model.capability not in CHAT_CAPABILITIES:
        raise bad_request("這個模型不是文字 / 看圖模型，無法用對話方式呼叫", "unsupported_capability")
    api_key = _check_usable(model)

    with _ledger(db, model, "ai.chat", source, user) as entry:
        base_url = validate_upstream_url(model.channel.base_url)
        url, request_body = _chat_request(model, base_url, api_key, messages, max_tokens)
        response = _send("POST", url, api_key, request_body)
        body = _json(response)
        if "choices" not in body and "candidates" not in body:
            # kie 等服務出錯時可能回 HTTP 200，錯誤放在內容的 code / msg
            raise upstream_error(_upstream_message(response).replace("HTTP 200", f"錯誤 {body.get('code', '')}".strip()))
        try:
            content, entry.input_tokens, entry.output_tokens = _parse_chat(body)
        except (KeyError, IndexError, TypeError, AttributeError):
            raise upstream_error("上游回應格式無法解析") from None
        if not isinstance(content, str):
            raise upstream_error("上游回應格式無法解析")
        entry.cost_micros = estimate_cost_micros(model, entry.input_tokens, entry.output_tokens)
        if entry.cost_micros is None and body.get("credits_consumed") is not None:
            entry.cost_micros = credits_to_micros(body["credits_consumed"])
    return ChatResult(content, entry.input_tokens, entry.output_tokens, entry.duration_ms, entry.cost_micros)


# ---------------------------------------------------------------- 文字轉語音
TTS_POLL_SECONDS = 2.0
TTS_TIMEOUT_SECONDS = 180.0
MAX_AUDIO_BYTES = 30 * 1024 * 1024


def _kie_tts(model: ChannelModel, api_key: str, text: str, voice_id: str, speed: float) -> tuple[bytes, object]:
    """kie.ai Market 任務：createTask → 輪詢 recordInfo → 下載音檔。回傳 (音檔, 消耗點數)。"""
    base_url = validate_upstream_url(model.channel.base_url)
    created = _json(
        _send(
            "POST",
            f"{base_url}/api/v1/jobs/createTask",
            api_key,
            {
                "model": model.model_key,
                "input": {
                    "text": text,
                    "voice": voice_id,
                    "stability": 0.5,
                    "similarity_boost": 0.75,
                    "style": 0,
                    "speed": min(max(speed, 0.7), 1.2),
                    "timestamps": False,
                },
            },
        )
    )
    task_id = (created.get("data") or {}).get("taskId") if created.get("code") == 200 else None
    if not task_id:
        raise upstream_error(f"建立配音任務失敗：{created.get('msg') or created.get('code')}")

    deadline = time.monotonic() + TTS_TIMEOUT_SECONDS
    while True:
        info = _json(_send("GET", f"{base_url}/api/v1/jobs/recordInfo", api_key, params={"taskId": task_id}))
        data = info.get("data") or {}
        state = data.get("state")
        if state == "success":
            break
        if state == "fail" or info.get("code") not in (200, None):
            raise upstream_error(f"配音失敗：{data.get('failMsg') or info.get('msg') or '未知原因'}")
        if time.monotonic() > deadline:
            raise upstream_error("配音逾時，請稍後再試", "upstream_timeout")
        time.sleep(TTS_POLL_SECONDS)

    try:
        audio_url = json.loads(data.get("resultJson") or "{}")["resultUrls"][0]
    except (ValueError, KeyError, IndexError, TypeError):
        raise upstream_error("配音結果格式無法解析") from None
    try:
        response = httpx.get(
            validate_upstream_url(audio_url), timeout=get_settings().upstream_timeout_seconds, follow_redirects=True
        )
    except httpx.HTTPError as exc:
        raise upstream_error(f"下載配音檔失敗：{type(exc).__name__}") from None
    if response.status_code >= 400 or not response.content or len(response.content) > MAX_AUDIO_BYTES:
        raise upstream_error(f"下載配音檔失敗（HTTP {response.status_code}）")
    return response.content, data.get("creditsConsumed")


def tts(
    db: Session,
    model: ChannelModel,
    text: str,
    voice_id: str,
    *,
    speed: float = 1.0,
    source: str,
    user: User | None,
) -> TtsResult:
    """產生配音（mp3）。成本記錄的 input_tokens 欄位存字元數。"""
    if model.capability != "tts":
        raise bad_request("這個模型不是配音模型", "unsupported_capability")
    if model.channel.provider != "kie":
        raise bad_request("目前只支援 kie.ai 的配音模型", "unsupported_provider")
    text = text.strip()
    if not text:
        raise bad_request("沒有可以配音的文字", "empty_text")
    api_key = _check_usable(model)

    with _ledger(db, model, "ai.tts", source, user) as entry:
        audio, credits = _kie_tts(model, api_key, text, voice_id, speed)
        entry.input_tokens = len(text)
        entry.cost_micros = credits_to_micros(credits) if credits is not None else None
    return TtsResult(audio, len(text), entry.duration_ms, entry.cost_micros)
