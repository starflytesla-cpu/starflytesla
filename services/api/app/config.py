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

    # ------------------------------------------------ 素材中心
    # 素材檔案存放位置（Docker 內掛載資料碟上的 volume）
    media_root: str = "/media"
    # 單一檔案上限（bytes），預設 2 GB；Caddy 的 request_body 上限也是 2 GB
    max_upload_bytes: int = 2 * 1024**3
    # 上傳前至少要保留的磁碟剩餘空間（bytes）
    min_free_bytes: int = 2 * 1024**3
    # worker 同時處理的任務數
    worker_concurrency: int = 2
    # 每支素材最多送幾個鏡頭給看圖模型（控制成本）
    vision_max_clips: int = 30


@lru_cache
def get_settings() -> Settings:
    return Settings()
