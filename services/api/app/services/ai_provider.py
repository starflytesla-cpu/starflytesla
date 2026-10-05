"""所有 AI 呼叫的唯一入口：選模型、發請求、解析用量、估算成本、寫入 usage_ledger。

- chat()：OpenAI 相容的 /chat/completions（DeepSeek、豆包 BytePlus、OpenRouter、kie.ai 的 Gemini）
- tts()：文字轉語音（kie.ai 的 Gemini 3.8 Flash TTS 與 ElevenLabs，建立任務後輪詢結果）

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
CAPABILITY_NAMES = {"text": "文字", "vision": "看圖", "tts": "配音", "music": "背景音樂", "embedding": "向量"}


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
    # 依檔案內容判斷的副檔名（.mp3 / .wav / .ogg / .m4a）
    extension: str = ".mp3"


def audio_extension(data: bytes) -> str:
    if data[:4] == b"RIFF":
        return ".wav"
    if data[:4] == b"OggS":
        return ".ogg"
    if data[4:8] == b"ftyp":
        return ".m4a"
    return ".mp3"


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
        if source in ("comment_suggest", "post_copy"):
            # Phase 4 的新入口：逾時／格式不明不等於沒消耗用量；保留待核對與未知成本。
            rejected = exc.reason == "upstream_auth" or getattr(exc, "upstream_status", None) in (400, 401, 403, 404, 422, 429)
            if not rejected:
                entry.status, entry.cost_micros = "uncertain", None
            entry.error = "AI 服務拒絕請求，請檢查模型設定" if rejected else "AI 回執未確認，請核對供應商用量紀錄"
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
        error = upstream_error(_upstream_message(response))
        error.upstream_status = response.status_code
        raise error
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


# ---------------------------------------------------------------- 豆包方舟（BytePlus / 火山引擎）
# 同一個「方舟」服務有國際版與中國區兩套，帳號與 API Key 互不相通：
# 拿火山引擎的 Key 打 BytePlus（或反過來）會回 401「The API key doesn't exist」。
ARK_ENDPOINTS = {
    "byteplus": ("BytePlus 國際版（東南亞）", "https://ark.ap-southeast.bytepluses.com/api/v3"),
    "volcengine": ("火山引擎方舟（中國區）", "https://ark.cn-beijing.volces.com/api/v3"),
}
ARK_PROBE_MODEL = "starfly-auth-probe"


def is_ark(provider: str, base_url: str) -> bool:
    return provider in ARK_ENDPOINTS or any(base_url.rstrip("/") == url for _, url in ARK_ENDPOINTS.values())


def describe_key(api_key: str) -> str:
    """描述 Key 的格式（不含 Key 內容），用來判斷是不是貼錯成 Access Key。"""
    if not api_key:
        return "未設定"
    if api_key.startswith("AK"):
        return f"AK 開頭、長度 {len(api_key)}（像是 Access Key ID，不是 API Key）"
    try:
        uuid.UUID(api_key)
        return "UUID 格式"
    except ValueError:
        return f"其他格式、長度 {len(api_key)}"


def probe_ark_auth(base_url: str, api_key: str) -> int | None:
    """用不存在的模型名稱送一次請求，只看驗證是否通過（模型不存在不會產生費用）。

    回傳 HTTP 狀態碼：401 代表這個端點不認得這把 Key；其他 4xx 代表驗證已通過；None 代表連線失敗。
    """
    try:
        response = httpx.post(
            f"{base_url}/chat/completions",
            headers={"Authorization": f"Bearer {api_key}"},
            json={"model": ARK_PROBE_MODEL, "messages": [{"role": "user", "content": "hi"}], "max_tokens": 1},
            timeout=15,
            follow_redirects=False,
        )
    except httpx.HTTPError:
        return None
    return response.status_code


def ark_key_home(api_key: str, exclude_url: str = "") -> tuple[str, str, str] | None:
    """找出這把 Key 屬於哪一個方舟端點，回傳 (provider, 名稱, 網址)。

    先用一把一定不存在的 Key 校正：如果假 Key 在該端點也不是 401，代表判斷不出來，不下結論。
    """
    for provider, (label, url) in ARK_ENDPOINTS.items():
        if url == exclude_url.rstrip("/"):
            continue
        status = probe_ark_auth(url, api_key)
        if status is None or status == 401 or status >= 500:
            continue
        if probe_ark_auth(url, str(uuid.uuid4())) == 401:
            return provider, label, url
    return None


def _ark_401_hint(api_key: str, base_url: str) -> str:
    """方舟回 401 時，說明 Key 實際屬於哪裡、該怎麼改。"""
    if api_key.startswith("AK"):
        return "。這把 Key 是 AK 開頭的 Access Key，請改填方舟控制台「API Key 管理」頁建立的 API Key"
    home = ark_key_home(api_key, exclude_url=base_url)
    if home:
        _, label, url = home
        return (
            f"。這把 Key 屬於「{label}」：請到「模型渠道」編輯這個渠道，把 Base URL 改成 {url}，"
            "並把模型名稱改成該平台控制台上的 Model ID（或用對應的豆包預設新增渠道）"
        )
    return "。BytePlus 國際版與火山引擎中國區都不認得這把 Key，請到方舟控制台確認 Key 沒有被刪除，再重新複製貼上"


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
        if response.status_code == 401 and is_ark(model.channel.provider, base_url):
            raise upstream_error(_upstream_message(response) + _ark_401_hint(api_key, base_url), "upstream_auth")
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


def _gemini_pace(speed: float) -> str:
    if speed >= 1.12:
        return "Speak at a brisk, fast pace."
    if speed >= 1.04:
        return "Speak at a slightly fast pace."
    if speed <= 0.85:
        return "Speak slowly and clearly."
    if speed <= 0.95:
        return "Speak at a relaxed, slightly slow pace."
    return ""


def _tts_input(model: ChannelModel, text: str, voice_id: str, speed: float, style: str) -> dict:
    """依模型組 kie 的 input：Gemini TTS 用對話格式（沒有語速參數，改用 style 文字描述）；ElevenLabs 用 text + voice。"""
    if model.model_key.startswith("google/gemini"):
        turn = {"speaker_id": "Speaker 1", "text": text}
        full_style = " ".join(part for part in (style.strip(), _gemini_pace(speed)) if part)
        if full_style:
            turn["style"] = full_style
        return {
            "temperature": 1,
            "speakers": [{"speaker_id": "Speaker 1", "voice_name": voice_id}],
            "dialogue_turns": [turn],
        }
    return {
        "text": text,
        "voice": voice_id,
        "stability": 0.5,
        "similarity_boost": 0.75,
        "style": 0,
        "speed": min(max(speed, 0.7), 1.2),
        "timestamps": False,
    }


def _kie_task(model: ChannelModel, api_key: str, task_input: dict, *, label: str, timeout: float) -> dict:
    """kie.ai Market 任務：createTask → 輪詢 recordInfo，回傳成功時的 data（含 resultJson、creditsConsumed）。"""
    base_url = validate_upstream_url(model.channel.base_url)
    created = _json(
        _send("POST", f"{base_url}/api/v1/jobs/createTask", api_key, {"model": model.model_key, "input": task_input})
    )
    task_id = (created.get("data") or {}).get("taskId") if created.get("code") == 200 else None
    if not task_id:
        raise upstream_error(f"建立{label}任務失敗：{created.get('msg') or created.get('code')}")

    deadline = time.monotonic() + timeout
    while True:
        info = _json(_send("GET", f"{base_url}/api/v1/jobs/recordInfo", api_key, params={"taskId": task_id}))
        data = info.get("data") or {}
        state = data.get("state")
        if state == "success":
            return data
        if state == "fail" or info.get("code") not in (200, None):
            raise upstream_error(f"{label}失敗：{data.get('failMsg') or info.get('msg') or '未知原因'}")
        if time.monotonic() > deadline:
            raise upstream_error(f"{label}逾時，請稍後再試", "upstream_timeout")
        time.sleep(TTS_POLL_SECONDS)


def _download_audio(url: str, label: str) -> bytes:
    try:
        response = httpx.get(validate_upstream_url(url), timeout=get_settings().upstream_timeout_seconds, follow_redirects=True)
    except httpx.HTTPError as exc:
        raise upstream_error(f"下載{label}失敗：{type(exc).__name__}") from None
    if response.status_code >= 400 or not response.content or len(response.content) > MAX_AUDIO_BYTES:
        raise upstream_error(f"下載{label}失敗（HTTP {response.status_code}）")
    return response.content


def _audio_urls(value) -> list[str]:
    """從 kie 的 resultJson 找出所有音檔網址（resultUrls 或 audio_url，不同模型格式不同）。"""
    found: list[str] = []

    def walk(item):
        if isinstance(item, dict):
            for key, inner in item.items():
                if key in ("resultUrls", "audio_url", "audioUrl") and isinstance(inner, (str, list)):
                    for url in [inner] if isinstance(inner, str) else inner:
                        if isinstance(url, str) and url.startswith("http") and url not in found:
                            found.append(url)
                else:
                    walk(inner)
        elif isinstance(item, list):
            for inner in item:
                walk(inner)

    walk(value)
    return found


def _kie_tts(model: ChannelModel, api_key: str, text: str, voice_id: str, speed: float, style: str) -> tuple[bytes, object]:
    """kie.ai 配音：回傳 (音檔, 消耗點數)。"""
    data = _kie_task(model, api_key, _tts_input(model, text, voice_id, speed, style), label="配音", timeout=TTS_TIMEOUT_SECONDS)
    try:
        urls = _audio_urls(json.loads(data.get("resultJson") or "{}"))
    except ValueError:
        urls = []
    if not urls:
        raise upstream_error("配音結果格式無法解析")
    return _download_audio(urls[0], "配音檔"), data.get("creditsConsumed")


def tts(
    db: Session,
    model: ChannelModel,
    text: str,
    voice_id: str,
    *,
    speed: float = 1.0,
    style: str = "",
    source: str,
    user: User | None,
) -> TtsResult:
    """產生配音。style 是給 Gemini TTS 的語氣描述（ElevenLabs 不使用）。成本記錄的 input_tokens 欄位存字元數。"""
    if model.capability != "tts":
        raise bad_request("這個模型不是配音模型", "unsupported_capability")
    if model.channel.provider != "kie":
        raise bad_request("目前只支援 kie.ai 的配音模型", "unsupported_provider")
    text = text.strip()
    if not text:
        raise bad_request("沒有可以配音的文字", "empty_text")
    api_key = _check_usable(model)

    with _ledger(db, model, "ai.tts", source, user) as entry:
        audio, credits = _kie_tts(model, api_key, text, voice_id, speed, style)
        entry.input_tokens = len(text)
        entry.cost_micros = credits_to_micros(credits) if credits is not None else None
    return TtsResult(audio, len(text), entry.duration_ms, entry.cost_micros, audio_extension(audio))


# ---------------------------------------------------------------- 背景音樂
MUSIC_TIMEOUT_SECONDS = 600.0
# Suno 版本：V6_MINI 速度快、價格低，適合當背景音樂
SUNO_VERSION = "V6_MINI"


@dataclass
class MusicResult:
    tracks: list[bytes]
    duration_ms: int
    cost_micros: int | None


def music(db: Session, model: ChannelModel, style: str, title: str, *, source: str, user: User | None) -> MusicResult:
    """用 kie.ai 的 Suno 產生純音樂（不含人聲），通常一次回傳 2 首。"""
    if model.capability != "music":
        raise bad_request("這個模型不是背景音樂模型", "unsupported_capability")
    if model.channel.provider != "kie":
        raise bad_request("目前只支援 kie.ai 的 Suno 音樂模型", "unsupported_provider")
    api_key = _check_usable(model)
    with _ledger(db, model, "ai.music", source, user) as entry:
        data = _kie_task(
            model,
            api_key,
            {
                "custom_mode": True,
                "instrumental": True,
                "model": SUNO_VERSION,
                "style": style[:1000],
                "title": title[:80],
                "negative_tags": "vocals, singing, voice, lyrics",
            },
            label="產生背景音樂",
            timeout=MUSIC_TIMEOUT_SECONDS,
        )
        try:
            urls = _audio_urls(json.loads(data.get("resultJson") or "{}"))
        except ValueError:
            urls = []
        if not urls:
            raise upstream_error("背景音樂結果格式無法解析")
        tracks = [_download_audio(url, "背景音樂") for url in urls[:2]]
        credits = data.get("creditsConsumed")
        entry.cost_micros = credits_to_micros(credits) if credits is not None else None
    return MusicResult(tracks, entry.duration_ms, entry.cost_micros)
