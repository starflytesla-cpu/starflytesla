import re
from datetime import datetime
from decimal import Decimal
from typing import Annotated, Literal

from pydantic import AfterValidator, BaseModel, ConfigDict, Field

from app.models import ChannelModel, ModelChannel, User

Role = Literal["admin", "shooter"]
Capability = Literal["text", "vision", "tts", "embedding"]


_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


def _normalize_email(value: str) -> str:
    # 不用 EmailStr：它會拒絕 .local 等內部網域，而工廠帳號常用內部網域當登入帳號。
    value = value.strip().lower()
    if not _EMAIL_RE.match(value):
        raise ValueError("Email 格式不正確")
    return value


Email = Annotated[str, Field(max_length=254), AfterValidator(_normalize_email)]


def ok(data=None, msg: str = "ok") -> dict:
    return {"code": 0, "data": data, "msg": msg}


# ---------------------------------------------------------------- 使用者
class UserOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    email: str
    display_name: str
    role: str
    is_active: bool
    last_login_at: datetime | None
    created_at: datetime


class LoginIn(BaseModel):
    email: Email
    password: str = Field(min_length=1, max_length=200)


class ChangePasswordIn(BaseModel):
    old_password: str = Field(min_length=1, max_length=200)
    new_password: str = Field(max_length=200)


class UserCreateIn(BaseModel):
    email: Email
    display_name: str = Field(min_length=1, max_length=80)
    password: str = Field(max_length=200)
    role: Role = "shooter"


class UserUpdateIn(BaseModel):
    display_name: str | None = Field(default=None, min_length=1, max_length=80)
    role: Role | None = None
    is_active: bool | None = None
    password: str | None = Field(default=None, max_length=200)


def user_out(user: User) -> dict:
    return UserOut.model_validate(user).model_dump(mode="json")


# ---------------------------------------------------------------- 模型渠道
class ChannelModelIn(BaseModel):
    model_key: str = Field(min_length=1, max_length=160)
    display_name: str = Field(default="", max_length=160)
    capability: Capability
    input_price_per_m: Decimal | None = Field(default=None, ge=0)
    output_price_per_m: Decimal | None = Field(default=None, ge=0)
    is_default: bool = False
    enabled: bool = True


class ChannelModelUpdateIn(BaseModel):
    display_name: str | None = Field(default=None, max_length=160)
    capability: Capability | None = None
    input_price_per_m: Decimal | None = Field(default=None, ge=0)
    output_price_per_m: Decimal | None = Field(default=None, ge=0)
    is_default: bool | None = None
    enabled: bool | None = None


class ChannelCreateIn(BaseModel):
    provider: Literal["deepseek", "byteplus", "openrouter", "kie", "custom"]
    name: str | None = Field(default=None, max_length=80)
    base_url: str | None = Field(default=None, max_length=500)
    api_key: str = Field(default="", max_length=500)


class ChannelUpdateIn(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=80)
    base_url: str | None = Field(default=None, max_length=500)
    # 留空代表不修改；要清除請傳空字串以外的操作（目前不提供清除）。
    api_key: str | None = Field(default=None, max_length=500)
    enabled: bool | None = None


class ChannelTestIn(BaseModel):
    prompt: str = Field(default="請用一句話介紹你自己。", min_length=1, max_length=2000)


def channel_model_out(model: ChannelModel) -> dict:
    return {
        "id": model.id,
        "channel_id": model.channel_id,
        "model_key": model.model_key,
        "display_name": model.display_name or model.model_key,
        "capability": model.capability,
        "input_price_per_m": _num(model.input_price_per_m),
        "output_price_per_m": _num(model.output_price_per_m),
        "is_default": model.is_default,
        "enabled": model.enabled,
    }


def channel_out(channel: ModelChannel) -> dict:
    return {
        "id": channel.id,
        "name": channel.name,
        "provider": channel.provider,
        "base_url": channel.base_url,
        # 永遠不回傳 API Key 本身，只回傳是否已設定與末 4 碼。
        "has_api_key": bool(channel.api_key_encrypted),
        "api_key_last4": channel.api_key_last4,
        "enabled": channel.enabled,
        "created_at": channel.created_at.isoformat(),
        "models": [channel_model_out(m) for m in channel.models],
    }


def _num(value: Decimal | None) -> float | None:
    return float(value) if value is not None else None


def micros_to_usd(value: int | None) -> float | None:
    return None if value is None else round(value / 1_000_000, 6)


# ---------------------------------------------------------------- 素材中心
Quality = Literal["good", "ok", "poor", ""]
TagList = Annotated[list[Annotated[str, Field(min_length=1, max_length=20)]], Field(max_length=12)]


class AssetUpdateIn(BaseModel):
    category: str | None = Field(default=None, max_length=32)
    note: str | None = Field(default=None, max_length=500)
    is_disabled: bool | None = None


class ClipUpdateIn(BaseModel):
    scene: str | None = Field(default=None, max_length=32)
    subjects: TagList | None = None
    tags: TagList | None = None
    description: str | None = Field(default=None, max_length=200)
    quality: Quality | None = None
    is_disabled: bool | None = None
