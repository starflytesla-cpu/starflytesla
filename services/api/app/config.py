from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str = "postgresql+psycopg://starfly:starfly@localhost:5432/starfly"
    # 用於簽發登入 token 與加密渠道 API Key；更換後所有人需重新登入、已存的 API Key 需重新填寫。
    secret_key: str

    # 首次啟動且資料庫沒有任何使用者時，用這組帳密建立管理員。
    admin_email: str = ""
    admin_password: str = ""

    session_days: int = 7
    # 預設拒絕指向本機 / 私網的上游網址（防 SSRF）；只有自架模型服務時才需要打開。
    allow_private_upstreams: bool = False
    upstream_timeout_seconds: float = 60.0


@lru_cache
def get_settings() -> Settings:
    return Settings()
