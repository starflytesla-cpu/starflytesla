"""所有 AI 呼叫的唯一入口：選模型、發請求、解析用量、估算成本、寫入 usage_ledger。

目前支援 OpenAI 相容的 /chat/completions（DeepSeek、豆包 BytePlus、OpenRouter 都適用）。
不論成功或失敗都會寫一筆成本記錄。
"""

import time
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
        detail = body.get("error", {}).get("message") or body.get("message") or ""
    except ValueError:
        detail = ""
    detail = str(detail)[:200]
    return f"上游回應 HTTP {response.status_code}" + (f"：{detail}" if detail else "")


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
        try:
            response = httpx.post(
                f"{base_url}/chat/completions",
                headers={"Authorization": f"Bearer {api_key}"},
                json={"model": model.model_key, "messages": messages, "max_tokens": max_tokens},
                timeout=get_settings().upstream_timeout_seconds,
                follow_redirects=False,
            )
        except httpx.TimeoutException:
            raise upstream_error("上游服務逾時，請稍後再試", "upstream_timeout") from None
        except httpx.HTTPError as exc:
            raise upstream_error(f"無法連線到上游服務：{type(exc).__name__}") from None
        if response.status_code >= 400:
            raise upstream_error(_upstream_message(response))
        try:
            body = response.json()
            content = body["choices"][0]["message"].get("content") or ""
        except (ValueError, KeyError, IndexError, TypeError):
            raise upstream_error("上游回應格式無法解析") from None

        usage = body.get("usage") or {}
        ledger.input_tokens = int(usage.get("prompt_tokens") or 0)
        ledger.output_tokens = int(usage.get("completion_tokens") or 0)
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
