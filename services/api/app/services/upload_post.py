"""Upload-Post 的窄入口。只保留業務需要的回應；不轉述上游錯誤或憑證。"""

import httpx

from app.config import get_settings
from app.errors import AppError, bad_request, upstream_error
from app.models import PublishChannel
from app.security import decrypt_secret
from app.services.publishing import validate_base_url

PLATFORMS = ("tiktok", "instagram", "youtube", "facebook")


class WriteUncertain(AppError):
    def __init__(self):
        super().__init__(502, "receipt_uncertain", "供應商回執尚未確認，請核對原請求，不能重送")


class ProviderRejected(AppError):
    def __init__(self, status: int):
        reason = "upstream_auth" if status in (401, 403) else "provider_rejected"
        super().__init__(502, reason, f"Upload-Post 回應 HTTP {status}，請檢查授權或服務狀態")
        self.provider_status = status


class UploadPost:
    def __init__(self, channel: PublishChannel):
        if not channel.enabled:
            raise bad_request("發佈渠道已停用", "channel_disabled")
        self.key = decrypt_secret(channel.api_key_encrypted)
        if not self.key:
            raise bad_request("請先在發佈渠道設定 API Key", "missing_api_key")
        self.base_url = channel.base_url

    def request(self, method: str, path: str, *, write: bool = False, **kwargs) -> dict:
        base = validate_base_url(self.base_url)
        headers = {"Authorization": f"Apikey {self.key}", **kwargs.pop("headers", {})}
        try:
            with httpx.Client(timeout=get_settings().upstream_timeout_seconds, trust_env=False, follow_redirects=False) as client:
                response = client.request(method, f"{base}/{path}", headers=headers, **kwargs)
        except httpx.RequestError:
            if write:
                raise WriteUncertain() from None
            raise upstream_error("Upload-Post 連線失敗，請稍後再試") from None
        if response.status_code not in (200, 201, 202):
            if write and response.status_code not in (400, 401, 403, 404, 422, 429):
                raise WriteUncertain()
            raise ProviderRejected(response.status_code)
        try:
            if len(response.content) > 4_000_000:
                raise ValueError()
            data = response.json()
            if not isinstance(data, dict):
                raise ValueError()
        except ValueError:
            if write:
                raise WriteUncertain() from None
            raise upstream_error("Upload-Post 回應格式不正確", "invalid_upstream_response") from None
        return data

    def text(self, value, limit: int) -> str:
        if not isinstance(value, (str, int)) or isinstance(value, bool):
            return ""
        value = str(value)
        if self.key in value or len(value) > limit:
            raise upstream_error("Upload-Post 回應格式不正確", "invalid_upstream_response")
        return value.strip()

    def profiles(self) -> list[dict]:
        body = self.request("GET", "uploadposts/users")
        rows = body.get("profiles")
        if body.get("success") is not True or not isinstance(rows, list) or len(rows) > 1000:
            raise upstream_error("Upload-Post 帳號清單格式不正確", "invalid_upstream_response")
        result = []
        for row in rows:
            if not isinstance(row, dict):
                raise upstream_error("Upload-Post 帳號清單格式不正確", "invalid_upstream_response")
            username = self.text(row.get("username"), 160)
            if not username:
                raise upstream_error("Upload-Post profile 缺少識別碼", "invalid_upstream_response")
            accounts = row.get("social_accounts")
            if not isinstance(accounts, dict):
                raise upstream_error("Upload-Post 社媒帳號格式不正確", "invalid_upstream_response")
            safe = {}
            for platform in PLATFORMS:
                account = accounts.get(platform)
                if not isinstance(account, dict):
                    continue
                identifier = self.text(account.get("username"), 200)
                # 缺少固定的目的帳號識別碼時不能僅憑顯示名稱判定授權完成。
                if not identifier:
                    continue
                caps = account.get("capabilities", [])
                safe[platform] = {
                    "external_account_id": identifier,
                    "display_name": self.text(account.get("display_name"), 200),
                    "handle": self.text(account.get("handle"), 200),
                    "auth_status": "reauth_required" if account.get("reauth_required") is True else "connected",
                    "capabilities": [self.text(c, 50) for c in caps[:30] if isinstance(c, str)] if isinstance(caps, list) else [],
                }
            result.append({"username": username, "accounts": safe})
        return result
