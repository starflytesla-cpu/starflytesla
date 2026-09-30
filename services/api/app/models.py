import uuid
from datetime import UTC, datetime
from decimal import Decimal

from sqlalchemy import (
    BigInteger,
    Boolean,
    DateTime,
    ForeignKey,
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
