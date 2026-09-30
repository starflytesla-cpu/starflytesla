import base64
import hashlib
import ipaddress
import socket
import time
from collections import defaultdict, deque
from datetime import UTC, datetime, timedelta
from threading import Lock
from urllib.parse import urlparse

import bcrypt
import jwt
from cryptography.fernet import Fernet, InvalidToken

from app.config import get_settings
from app.errors import bad_request, too_many_requests

SESSION_COOKIE = "starfly_session"


# ---------------------------------------------------------------- 密碼
def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()


def verify_password(password: str, password_hash: str) -> bool:
    try:
        return bcrypt.checkpw(password.encode(), password_hash.encode())
    except ValueError:
        return False


def validate_new_password(password: str) -> None:
    if len(password) < 8:
        raise bad_request("密碼至少需要 8 個字元", "weak_password")


# ---------------------------------------------------------------- 登入 token
def _derive_key(purpose: str) -> bytes:
    # 同一把 SECRET_KEY 依用途衍生不同金鑰，避免簽章與加密共用同一把 key。
    return hashlib.sha256(f"starfly:{purpose}:{get_settings().secret_key}".encode()).digest()


def create_session_token(user_id: str, token_version: int) -> str:
    settings = get_settings()
    payload = {
        "sub": user_id,
        "ver": token_version,
        "exp": datetime.now(UTC) + timedelta(days=settings.session_days),
    }
    return jwt.encode(payload, _derive_key("session"), algorithm="HS256")


def decode_session_token(token: str) -> dict | None:
    try:
        return jwt.decode(token, _derive_key("session"), algorithms=["HS256"])
    except jwt.PyJWTError:
        return None


# ---------------------------------------------------------------- 渠道 API Key 加密
def _fernet() -> Fernet:
    return Fernet(base64.urlsafe_b64encode(_derive_key("secrets")))


def encrypt_secret(value: str) -> str:
    return _fernet().encrypt(value.encode()).decode() if value else ""


def decrypt_secret(value: str) -> str:
    if not value:
        return ""
    try:
        return _fernet().decrypt(value.encode()).decode()
    except InvalidToken:
        # SECRET_KEY 被更換過：舊的密文無法解開，視為未設定，請管理員重新填寫。
        return ""


# ---------------------------------------------------------------- 上游網址檢查（防 SSRF）
def validate_upstream_url(url: str) -> str:
    """只允許 https 的公網上游；拒絕本機、私網、link-local 等位址。"""
    url = url.strip().rstrip("/")
    parsed = urlparse(url)
    allow_private = get_settings().allow_private_upstreams
    if parsed.scheme != "https" and not (allow_private and parsed.scheme == "http"):
        raise bad_request("Base URL 必須以 https:// 開頭", "invalid_upstream")
    if not parsed.hostname:
        raise bad_request("Base URL 格式不正確", "invalid_upstream")
    if parsed.username or parsed.password:
        raise bad_request("Base URL 不能包含帳號密碼", "invalid_upstream")
    if allow_private:
        return url
    try:
        infos = socket.getaddrinfo(parsed.hostname, parsed.port or 443, proto=socket.IPPROTO_TCP)
    except socket.gaierror:
        raise bad_request("無法解析 Base URL 的網域", "invalid_upstream") from None
    for info in infos:
        ip = ipaddress.ip_address(info[4][0])
        if not ip.is_global:
            raise bad_request("Base URL 不能指向本機或內網位址", "private_upstream")
    return url


# ---------------------------------------------------------------- 登入失敗限流
class LoginRateLimiter:
    """同一個 IP + 帳號在 15 分鐘內失敗 10 次就暫時鎖定。單一程序內記憶體計數即可。"""

    def __init__(self, max_failures: int = 10, window_seconds: int = 900):
        self.max_failures = max_failures
        self.window = window_seconds
        self._failures: dict[str, deque[float]] = defaultdict(deque)
        self._lock = Lock()

    def _prune(self, key: str, now: float) -> deque[float]:
        q = self._failures[key]
        while q and now - q[0] > self.window:
            q.popleft()
        return q

    def check(self, key: str) -> None:
        with self._lock:
            if len(self._prune(key, time.monotonic())) >= self.max_failures:
                raise too_many_requests("登入失敗次數過多，請 15 分鐘後再試")

    def record_failure(self, key: str) -> None:
        with self._lock:
            now = time.monotonic()
            self._prune(key, now).append(now)

    def reset(self, key: str) -> None:
        with self._lock:
            self._failures.pop(key, None)


login_limiter = LoginRateLimiter()
