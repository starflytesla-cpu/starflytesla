"""Upload-Post 渠道檢查；只呼叫 GET /uploadposts/me，不產生貼文。"""

import time
from urllib.parse import urlparse

import httpx
from sqlalchemy import update
from sqlalchemy.orm import Session

from app.config import get_settings
from app.errors import AppError, bad_request, conflict, upstream_error
from app.models import PublishChannel, UsageLedger, User, utcnow
from app.security import decrypt_secret, validate_upstream_url


def validate_base_url(url: str) -> str:
    try:
        parsed = urlparse(url.strip())
        parsed.port
    except ValueError:
        raise bad_request("Base URL 格式不正確", "invalid_upstream") from None
    if parsed.query or parsed.fragment:
        raise bad_request("Base URL 不能包含查詢參數或片段", "invalid_upstream")
    return validate_upstream_url(url)


def test_channel(db: Session, channel: PublishChannel, admin: User) -> dict:
    if channel.tenant_id != admin.tenant_id:
        raise bad_request("渠道不屬於這個租戶", "invalid_channel")
    if not channel.enabled:
        raise bad_request("請先啟用這個渠道", "channel_disabled")
    encrypted_key = channel.api_key_encrypted
    stored_base_url = channel.base_url
    key = decrypt_secret(encrypted_key)
    if not key:
        raise bad_request("請先設定 Upload-Post API Key", "missing_api_key")
    # 每次呼叫前重新檢查 DNS，避免設定後網域改指向內網；不跟隨轉址。
    base_url = validate_base_url(channel.base_url)
    started = time.monotonic()
    failure = None
    plan = ""
    try:
        with httpx.Client(
            timeout=get_settings().upstream_timeout_seconds,
            follow_redirects=False,
            trust_env=False,
        ) as client:
            response = client.get(
                f"{base_url}/uploadposts/me",
                headers={"Authorization": f"Apikey {key}"},
            )
        if response.status_code == 401:
            raise upstream_error("Upload-Post API Key 無效或已過期，請重新設定", "upstream_auth")
        if response.status_code == 403:
            raise upstream_error("Upload-Post 拒絕存取，請確認 API Key 權限與方案", "upstream_auth")
        if response.status_code != 200:
            # 不轉述上游 body、headers 或 exception，避免它們回顯憑證。
            raise upstream_error(f"Upload-Post 回應 HTTP {response.status_code}，請稍後再試")
        data = response.json()
        if not isinstance(data, dict) or data.get("success") is not True:
            raise upstream_error("Upload-Post 未確認 API Key 有效", "invalid_upstream_response")
        plan = data.get("plan")
        if not isinstance(plan, str) or not plan.strip() or len(plan) > 80 or key in plan:
            raise upstream_error("Upload-Post 方案回應格式不正確", "invalid_upstream_response")
        plan = plan.strip()
    except httpx.TimeoutException:
        failure = upstream_error("Upload-Post 連線逾時，請稍後再測試", "upstream_timeout")
    except httpx.RequestError:
        failure = upstream_error("無法連線到 Upload-Post，請檢查網址或稍後再試")
    except ValueError:
        failure = upstream_error("Upload-Post 回應不是有效 JSON", "invalid_upstream_response")
    except AppError as exc:
        failure = exc

    # 檢查期間可能有另一位管理員更換 Key；舊請求不能覆寫新設定的檢查狀態。
    changed = db.execute(update(PublishChannel).where(
        PublishChannel.id == channel.id,
        PublishChannel.tenant_id == admin.tenant_id,
        PublishChannel.api_key_encrypted == encrypted_key,
        PublishChannel.base_url == stored_base_url,
        PublishChannel.enabled.is_(True),
    ).values(
        checked_at=utcnow(),
        check_status="failed" if failure else "succeeded",
        check_error=failure.message if failure else "",
        plan="" if failure else plan,
    ), execution_options={"synchronize_session": False}).rowcount
    if not changed:
        failure = conflict("檢查期間渠道設定已變更，請重新檢查", "channel_changed")
    duration_ms = round((time.monotonic() - started) * 1000)
    db.add(UsageLedger(
        tenant_id=admin.tenant_id,
        user_id=admin.id,
        publish_channel_id=channel.id,
        action="publish.channel_test",
        source="publish_channel_test",
        provider="uploadpost",
        status="failed" if failure else "succeeded",
        duration_ms=duration_ms,
        # 這是查詢帳號的 GET，沒有發佈或消耗發佈額度；貼文成本要在發佈時另記。
        cost_micros=0,
        error=failure.message if failure else "",
    ))
    db.commit()
    if failure:
        raise failure
    return {"plan": plan, "duration_ms": duration_ms, "cost_usd": 0}
