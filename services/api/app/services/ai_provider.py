"""所有 AI 呼叫的唯一入口：選模型、發請求、解析用量、估算成本、寫入 usage_ledger。

目前支援 OpenAI 相容的 /chat/completions（DeepSeek、豆包 BytePlus、OpenRouter 都適用）。
kie.ai 的差異在 _kie_* 函式處理：每個模型有自己的網址路徑、圖片要先上傳成網址。
不論成功或失敗都會寫一筆成本記錄。
"""

import time
import uuid
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


@dataclass
class ChatResult:
    content: str
    input_tokens: int
    output_tokens: int
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
        raise bad_request(f"尚未設定可用的「{capability}」模型，請到模型渠道新增", "no_model")
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


# kie.ai 的檔案上傳服務（免費，檔案 3 天後自動刪除）。看圖模型只接受圖片網址，
# 而素材的關鍵畫面在登入保護之後，所以先上傳到這裡取得暫時網址。
KIE_UPLOAD_URL = "https://kieai.redpandaai.co/api/file-base64-upload"


def _post(url: str, api_key: str, body: dict) -> httpx.Response:
    try:
        return httpx.post(
            url,
            headers={"Authorization": f"Bearer {api_key}"},
            json=body,
            timeout=get_settings().upstream_timeout_seconds,
            follow_redirects=False,
        )
    except httpx.TimeoutException:
        raise upstream_error("上游服務逾時，請稍後再試", "upstream_timeout") from None
    except httpx.HTTPError as exc:
        raise upstream_error(f"無法連線到上游服務：{type(exc).__name__}") from None


def _kie_upload_image(data_url: str, api_key: str) -> str:
    response = _post(
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


def _request(channel: ModelChannel, model: ChannelModel, base_url: str, api_key: str, messages: list[dict], max_tokens: int) -> tuple[str, dict]:
    """回傳 (請求網址, 請求內容)。一律關閉串流（kie 預設是串流）。"""
    if channel.provider == "kie":
        # kie 每個模型有自己的路徑，例如 https://api.kie.ai/gemini-3-8-flash-openai/v1/chat/completions；
        # Gemini 會先思考再回答，max_tokens 會把思考也算進去，改用 reasoning_effort 控制成本。
        url = f"{base_url}/{model.model_key}/v1/chat/completions"
        body = {"messages": _kie_messages(messages, api_key), "stream": False, "reasoning_effort": "low"}
        return url, body
    body = {"model": model.model_key, "messages": messages, "max_tokens": max_tokens, "stream": False}
    return f"{base_url}/chat/completions", body


def _parse(body: dict) -> tuple[str, int, int]:
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
    channel = model.channel
    if model.capability not in CHAT_CAPABILITIES:
        raise bad_request("這個模型不是文字 / 看圖模型，無法用對話方式呼叫", "unsupported_capability")
    if not channel.enabled or not model.enabled:
        raise bad_request("渠道或模型已停用", "model_disabled")
    api_key = decrypt_secret(channel.api_key_encrypted)
    if not api_key:
        raise bad_request("這個渠道還沒有填寫 API Key", "missing_api_key")

    ledger = UsageLedger(
        tenant_id=channel.tenant_id,
        user_id=user.id if user else None,
        action="ai.chat",
        source=source,
        channel_id=channel.id,
        provider=channel.provider,
        model_key=model.model_key,
        status="failed",
    )
    started = time.monotonic()
    try:
        base_url = validate_upstream_url(channel.base_url)
        url, request_body = _request(channel, model, base_url, api_key, messages, max_tokens)
        response = _post(url, api_key, request_body)
        if response.status_code >= 400:
            raise upstream_error(_upstream_message(response))
        try:
            body = response.json()
        except ValueError:
            raise upstream_error("上游回應格式無法解析") from None
        if isinstance(body, dict) and "choices" not in body and "candidates" not in body:
            # kie 等服務出錯時可能回 HTTP 200，錯誤放在內容的 code / msg
            raise upstream_error(_upstream_message(response).replace("HTTP 200", f"錯誤 {body.get('code', '')}".strip()))
        try:
            content, ledger.input_tokens, ledger.output_tokens = _parse(body)
        except (ValueError, KeyError, IndexError, TypeError, AttributeError):
            raise upstream_error("上游回應格式無法解析") from None
        if not isinstance(content, str):
            raise upstream_error("上游回應格式無法解析")
        ledger.cost_micros = estimate_cost_micros(model, ledger.input_tokens, ledger.output_tokens)
        ledger.status = "succeeded"
    except AppError as exc:
        ledger.error = exc.message[:500]
        # 失敗的呼叫沒有產生用量，成本記為 0，而不是「價格未知」。
        ledger.input_tokens = ledger.output_tokens = 0
        ledger.cost_micros = 0
        raise
    finally:
        ledger.duration_ms = int((time.monotonic() - started) * 1000)
        db.add(ledger)
        db.commit()
    return ChatResult(
        content=content,
        input_tokens=ledger.input_tokens,
        output_tokens=ledger.output_tokens,
        duration_ms=ledger.duration_ms,
        cost_micros=ledger.cost_micros,
    )
