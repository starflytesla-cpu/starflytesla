import uuid
from datetime import UTC, datetime
from decimal import Decimal

from sqlalchemy import (
    JSON,
    BigInteger,
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


def new_id() -> str:
    return str(uuid.uuid4())


def utcnow() -> datetime:
    return datetime.now(UTC)


class Base(DeclarativeBase):
    pass


class Tenant(Base):
    """租戶：一個客戶（工廠 / 門店）。試營運只有一個預設租戶，商品化時開放多租戶。"""

    __tablename__ = "tenants"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    name: Mapped[str] = mapped_column(String(120))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class User(Base):
    __tablename__ = "users"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    tenant_id: Mapped[str] = mapped_column(ForeignKey("tenants.id"), index=True)
    email: Mapped[str] = mapped_column(String(254), unique=True)
    display_name: Mapped[str] = mapped_column(String(80))
    password_hash: Mapped[str] = mapped_column(String(128))
    # admin：管理員，可設定渠道與帳號；shooter：拍攝員，只能上傳素材。
    role: Mapped[str] = mapped_column(String(16), default="shooter")
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    # 改密碼或停用時遞增，讓舊的登入 token 立即失效。
    token_version: Mapped[int] = mapped_column(Integer, default=0)
    last_login_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow
    )


class ModelChannel(Base):
    """模型渠道：一個 AI 服務商帳號（Base URL + API Key）。API Key 加密後存放。"""

    __tablename__ = "model_channels"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    tenant_id: Mapped[str] = mapped_column(ForeignKey("tenants.id"), index=True)
    name: Mapped[str] = mapped_column(String(80))
    provider: Mapped[str] = mapped_column(String(32))
    base_url: Mapped[str] = mapped_column(String(500))
    api_key_encrypted: Mapped[str] = mapped_column(Text, default="")
    api_key_last4: Mapped[str] = mapped_column(String(8), default="")
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow
    )

    models: Mapped[list["ChannelModel"]] = relationship(
        back_populates="channel",
        cascade="all, delete-orphan",
        order_by="ChannelModel.created_at",
    )


class ChannelModel(Base):
    """渠道下的一個模型。capability 決定它用在哪類任務；每種 capability 可以指定一個預設模型。"""

    __tablename__ = "channel_models"
    __table_args__ = (UniqueConstraint("channel_id", "model_key"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    channel_id: Mapped[str] = mapped_column(
        ForeignKey("model_channels.id", ondelete="CASCADE"), index=True
    )
    model_key: Mapped[str] = mapped_column(String(160))
    display_name: Mapped[str] = mapped_column(String(160))
    # text：文案 / 翻譯 / 評論；vision：看圖打標籤；tts：配音；embedding：向量
    capability: Mapped[str] = mapped_column(String(16), index=True)
    # 每百萬 token 的價格（USD）；未填代表不知道價格，成本記錄會標示為無法估算。
    input_price_per_m: Mapped[Decimal | None] = mapped_column(Numeric(12, 6))
    output_price_per_m: Mapped[Decimal | None] = mapped_column(Numeric(12, 6))
    is_default: Mapped[bool] = mapped_column(Boolean, default=False)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    channel: Mapped[ModelChannel] = relationship(back_populates="models")


class UsageLedger(Base):
    """成本記錄：每次 AI / 渲染 / 發佈動作一筆。試營運只記錄不扣費，商品化時據此訂積分價格。

    不保存請求與回應內容，避免把素材文字或金鑰寫進資料庫。
    """

    __tablename__ = "usage_ledger"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    tenant_id: Mapped[str] = mapped_column(ForeignKey("tenants.id"), index=True)
    user_id: Mapped[str | None] = mapped_column(ForeignKey("users.id"), index=True)
    # 例如 ai.chat、render.video、publish.post
    action: Mapped[str] = mapped_column(String(48), index=True)
    # 觸發來源，例如 channel_test、asset_analyze
    source: Mapped[str] = mapped_column(String(48))
    channel_id: Mapped[str | None] = mapped_column(
        ForeignKey("model_channels.id", ondelete="SET NULL"), index=True
    )
    provider: Mapped[str] = mapped_column(String(32), default="")
    model_key: Mapped[str] = mapped_column(String(160), default="")
    status: Mapped[str] = mapped_column(String(16), index=True)
    input_tokens: Mapped[int] = mapped_column(BigInteger, default=0)
    output_tokens: Mapped[int] = mapped_column(BigInteger, default=0)
    duration_ms: Mapped[int] = mapped_column(Integer, default=0)
    # 以百萬分之一美元為單位，避免浮點誤差；None 代表價格未知。
    cost_micros: Mapped[int | None] = mapped_column(BigInteger)
    currency: Mapped[str] = mapped_column(String(8), default="USD")
    error: Mapped[str] = mapped_column(String(500), default="")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, index=True
    )


# ---------------------------------------------------------------- Phase 1 素材中心
class Upload(Base):
    """一個斷點續傳（tus）上傳。檔案先寫到 MEDIA_ROOT/_uploads/{id}.part，傳完才建立 Asset。"""

    __tablename__ = "uploads"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    tenant_id: Mapped[str] = mapped_column(ForeignKey("tenants.id"), index=True)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
    filename: Mapped[str] = mapped_column(String(255))
    content_type: Mapped[str] = mapped_column(String(100), default="")
    size_bytes: Mapped[int] = mapped_column(BigInteger)
    offset_bytes: Mapped[int] = mapped_column(BigInteger, default=0)
    completed: Mapped[bool] = mapped_column(Boolean, default=False)
    asset_id: Mapped[str | None] = mapped_column(String(36))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow
    )


class Asset(Base):
    """一個上傳的原始素材（影片或照片）。分析後切成多個 Clip（鏡頭）。

    status：uploaded 已上傳待分析 → processing 分析中 → ready 可用 / failed 失敗 / duplicate 與既有素材完全相同
    """

    __tablename__ = "assets"
    __table_args__ = (Index("ix_assets_tenant_created", "tenant_id", "created_at"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    tenant_id: Mapped[str] = mapped_column(ForeignKey("tenants.id"), index=True)
    uploaded_by: Mapped[str | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), index=True
    )
    original_filename: Mapped[str] = mapped_column(String(255))
    # 原始檔在 MEDIA_ROOT 底下的相對路徑，例如 {tenant}/assets/{id}/original.mp4
    storage_key: Mapped[str] = mapped_column(String(500))
    kind: Mapped[str] = mapped_column(String(16))  # video / image
    status: Mapped[str] = mapped_column(String(16), default="uploaded", index=True)
    # 分析進行到哪一步，或分析完成後的提醒（例如未設定看圖模型）
    stage: Mapped[str] = mapped_column(String(200), default="")
    error: Mapped[str] = mapped_column(String(500), default="")
    size_bytes: Mapped[int] = mapped_column(BigInteger, default=0)
    sha256: Mapped[str] = mapped_column(String(64), default="", index=True)
    duration: Mapped[float | None] = mapped_column(Float)
    width: Mapped[int | None] = mapped_column(Integer)
    height: Mapped[int | None] = mapped_column(Integer)
    fps: Mapped[float | None] = mapped_column(Float)
    has_audio: Mapped[bool] = mapped_column(Boolean, default=False)
    has_proxy: Mapped[bool] = mapped_column(Boolean, default=False)
    has_poster: Mapped[bool] = mapped_column(Boolean, default=False)
    # 主要場景分類（取各鏡頭場景中時長最長者），可人工修改
    category: Mapped[str] = mapped_column(String(32), default="", index=True)
    note: Mapped[str] = mapped_column(String(500), default="")
    is_disabled: Mapped[bool] = mapped_column(Boolean, default=False)
    duplicate_of: Mapped[str | None] = mapped_column(
        ForeignKey("assets.id", ondelete="SET NULL")
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    analyzed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    clips: Mapped[list["Clip"]] = relationship(
        back_populates="asset",
        cascade="all, delete-orphan",
        passive_deletes=True,
        order_by="Clip.index",
        foreign_keys="Clip.asset_id",
    )


class Clip(Base):
    """素材中的一個鏡頭（依畫面切換自動切分）。混剪時以鏡頭為單位挑選。"""

    __tablename__ = "clips"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    asset_id: Mapped[str] = mapped_column(
        ForeignKey("assets.id", ondelete="CASCADE"), index=True
    )
    tenant_id: Mapped[str] = mapped_column(ForeignKey("tenants.id"), index=True)
    index: Mapped[int] = mapped_column(Integer)
    start: Mapped[float] = mapped_column(Float, default=0)
    end: Mapped[float] = mapped_column(Float, default=0)
    # 場景分類代碼，見 app/services/asset_analyzer.py 的 SCENES
    scene: Mapped[str] = mapped_column(String(32), default="", index=True)
    subjects: Mapped[list] = mapped_column(JSON, default=list)
    tags: Mapped[list] = mapped_column(JSON, default=list)
    description: Mapped[str] = mapped_column(String(500), default="")
    # good / ok / poor；空字串代表還沒評估
    quality: Mapped[str] = mapped_column(String(8), default="")
    is_dark: Mapped[bool] = mapped_column(Boolean, default=False)
    # 關鍵畫面的 64-bit 差異雜湊（dHash），用來找畫面幾乎相同的鏡頭
    dhash: Mapped[int | None] = mapped_column(BigInteger)
    duplicate_of_clip_id: Mapped[str | None] = mapped_column(
        ForeignKey("clips.id", ondelete="SET NULL")
    )
    is_disabled: Mapped[bool] = mapped_column(Boolean, default=False)
    # ai：AI 標註；manual：人工修改過；空字串：尚未標註
    tagged_by: Mapped[str] = mapped_column(String(8), default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    asset: Mapped[Asset] = relationship(back_populates="clips", foreign_keys=[asset_id])


class Task(Base):
    """背景任務佇列（用 PostgreSQL 取代 Redis）。worker 以 FOR UPDATE SKIP LOCKED 領取。

    status：queued → running → succeeded / failed；執行中的任務靠 lease_expires_at 判斷 worker 是否還活著，
    租約過期的任務會被其他 worker 重新領取。
    """

    __tablename__ = "tasks"
    __table_args__ = (Index("ix_tasks_pick", "status", "run_after"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    tenant_id: Mapped[str | None] = mapped_column(ForeignKey("tenants.id"), index=True)
    type: Mapped[str] = mapped_column(String(48), index=True)
    status: Mapped[str] = mapped_column(String(16), default="queued")
    payload: Mapped[dict] = mapped_column(JSON, default=dict)
    result: Mapped[dict | None] = mapped_column(JSON)
    error: Mapped[str] = mapped_column(String(1000), default="")
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    max_attempts: Mapped[int] = mapped_column(Integer, default=3)
    run_after: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    locked_by: Mapped[str] = mapped_column(String(80), default="")
    lease_expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
