import re
from datetime import datetime
from decimal import Decimal
from typing import Annotated, Literal
from uuid import UUID

from pydantic import AfterValidator, BaseModel, ConfigDict, Field, StringConstraints

from app.models import ChannelModel, ModelChannel, PublishChannel, User

Role = Literal["admin", "shooter"]
Capability = Literal["text", "vision", "tts", "music", "embedding"]


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


# ---------------------------------------------------------------- 發佈渠道
def _publish_key(value: str) -> str:
    value = value.strip()
    if value and (len(value) < 8 or any(not 33 <= ord(c) <= 126 for c in value)):
        raise ValueError("API Key 格式不正確")
    return value


PublishKey = Annotated[str, Field(max_length=500), AfterValidator(_publish_key)]
ChannelName = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=80)]


class PublishChannelCreateIn(BaseModel):
    name: ChannelName = "Upload-Post"
    base_url: str = Field(default="https://api.upload-post.com/api", max_length=500)
    api_key: PublishKey = ""
    enabled: bool = True


class PublishChannelUpdateIn(BaseModel):
    name: ChannelName | None = None
    base_url: str | None = Field(default=None, max_length=500)
    api_key: PublishKey | None = None
    clear_api_key: bool = False
    enabled: bool | None = None


def publish_channel_out(channel: PublishChannel) -> dict:
    # 明確列出可公開的欄位，不能使用 ORM 的完整序列化。
    return {
        "id": channel.id,
        "name": channel.name,
        "provider": channel.provider,
        "base_url": channel.base_url,
        "has_api_key": bool(channel.api_key_encrypted),
        "api_key_last4": channel.api_key_last4,
        "enabled": channel.enabled,
        "check_status": channel.check_status,
        "check_error": channel.check_error,
        "plan": channel.plan,
        "checked_at": channel.checked_at.isoformat() if channel.checked_at else None,
        "created_at": channel.created_at.isoformat(),
    }


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
    provider: Literal["deepseek", "byteplus", "volcengine", "openrouter", "kie", "custom"]
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


# ---------------------------------------------------------------- 帳號檔案、模板、文案、音色
ShortList = Annotated[list[Annotated[str, Field(max_length=200)]], Field(max_length=15)]


class ProfileIn(BaseModel):
    name: str | None = Field(default=None, max_length=80)
    industry: str | None = Field(default=None, max_length=120)
    audience: str | None = Field(default=None, max_length=500)
    selling_points: ShortList | None = None
    product_details: str | None = Field(default=None, max_length=5000)
    tone: str | None = Field(default=None, max_length=200)
    target_language: str | None = Field(default=None, max_length=16)
    call_to_action: str | None = Field(default=None, max_length=200)
    hashtags: ShortList | None = None
    banned_words: ShortList | None = None
    voice_id: str | None = Field(default=None, max_length=40)
    voice_speed: float | None = Field(default=None, ge=0.7, le=1.2)


class ShotIn(BaseModel):
    brief: str = Field(min_length=1, max_length=300)
    scene: str = Field(default="", max_length=32)
    seconds: float = Field(default=4, ge=1, le=30)


class TemplateIn(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=80)
    strategy: Literal["persona", "traffic", "conversion"] | None = None
    description: str | None = Field(default=None, max_length=500)
    shots: Annotated[list[ShotIn], Field(min_length=1, max_length=12)] | None = None
    is_active: bool | None = None


class GenerateScriptsIn(BaseModel):
    template_id: str
    profile_id: str
    variants: int = Field(default=3, ge=1, le=5)


class ScriptShotIn(BaseModel):
    voiceover: str = Field(default="", max_length=600)
    caption: str = Field(default="", max_length=120)


class ScriptUpdateIn(BaseModel):
    title: str | None = Field(default=None, max_length=200)
    hook: str | None = Field(default=None, max_length=300)
    shots: list[ScriptShotIn] | None = None
    post_caption: str | None = Field(default=None, max_length=2200)
    hashtags: ShortList | None = None
    status: Literal["draft", "approved"] | None = None


class VoicePreviewIn(BaseModel):
    voice_id: str = Field(max_length=40)
    text: str = Field(min_length=1, max_length=1500)
    speed: float = Field(default=1.0, ge=0.7, le=1.2)


# ---------------------------------------------------------------- 成片
class RenderIn(BaseModel):
    script_ids: Annotated[list[str], Field(min_length=1, max_length=20)]
    per_script: int = Field(default=1, ge=1, le=5)
    style: str = Field(default="random", max_length=20)
    # 素材現場原聲音量；預設 0（各片段原聲不一致，改用統一的背景音樂）
    ambience: float = Field(default=0.0, ge=0, le=0.6)
    # 背景音樂：auto 每支隨機挑一首、none 不用、或指定音樂 ID
    bgm: str = Field(default="auto", max_length=36)
    bgm_volume: float = Field(default=0.22, ge=0, le=0.6)


class CoverageIn(BaseModel):
    script_ids: Annotated[list[str], Field(max_length=50)]


class ReviewIn(BaseModel):
    action: Literal["approve", "reject"]
    note: str = Field(default="", max_length=500)


class ReplaceClipIn(BaseModel):
    shot_index: int = Field(ge=0, le=50)
    clip_id: str = Field(max_length=36)


class RerenderIn(BaseModel):
    reshuffle: bool = False


# ---------------------------------------------------------------- 背景音樂
class MusicGenerateIn(BaseModel):
    preset: str = Field(max_length=32)
    extra: str = Field(default="", max_length=300)
    title: str = Field(default="", max_length=120)


class MusicUpdateIn(BaseModel):
    title: str | None = Field(default=None, max_length=120)
    is_active: bool | None = None


# ---------------------------------------------------------------- 發佈與評論
Platform = Literal["tiktok", "instagram", "youtube", "facebook"]


class BindAccountsIn(BaseModel):
    channel_id: str = Field(max_length=36)
    profile_id: str = Field(max_length=36)
    remote_profile: str = Field(min_length=1, max_length=160)
    platforms: Annotated[list[Platform], Field(min_length=1, max_length=4)]


class AccountUpdateIn(BaseModel):
    enabled: bool | None = None
    auto_suggest_enabled: bool | None = None


class PostCopyIn(BaseModel):
    video_id: str = Field(max_length=36)
    platform: Platform


class SchedulePostIn(BaseModel):
    request_key: UUID
    video_id: str = Field(max_length=36)
    account_id: str = Field(max_length=36)
    title: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=100)]
    description: str = Field(default="", max_length=2000)
    hashtags: Annotated[list[Annotated[str, StringConstraints(pattern=r"^#[\w]+$", max_length=50)]], Field(max_length=10)] = []
    schedule_at: datetime
    confirmed: Literal[True]
    is_ai_generated: bool = True


class ReplyCommentIn(BaseModel):
    text: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=2000)]
    confirmed: Literal[True]
    version: str = Field(min_length=64, max_length=64, pattern=r"^[0-9a-f]+$")
