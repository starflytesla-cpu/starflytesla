"""帳號檔案（品牌人設）的輸出格式與修改。"""

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.errors import bad_request, not_found
from app.models import BrandProfile, Script, User
from app.services.voices import VOICES_BY_ID

# 文案與配音語言（ElevenLabs Multilingual v2 都支援）
LANGUAGES = {
    "en": "English 英文",
    "es": "Español 西班牙文",
    "pt": "Português 葡萄牙文",
    "fr": "Français 法文",
    "de": "Deutsch 德文",
    "it": "Italiano 義大利文",
    "ru": "Русский 俄文",
    "ar": "العربية 阿拉伯文",
    "tr": "Türkçe 土耳其文",
    "id": "Bahasa Indonesia 印尼文",
    "vi": "Tiếng Việt 越南文",
    "th": "ไทย 泰文",
    "ja": "日本語 日文",
    "ko": "한국어 韓文",
    "zh-TW": "繁體中文",
}

FIELDS = (
    "name",
    "industry",
    "audience",
    "selling_points",
    "product_details",
    "tone",
    "target_language",
    "call_to_action",
    "hashtags",
    "banned_words",
    "voice_id",
    "voice_speed",
)


def profile_out(profile: BrandProfile, script_count: int | None = None) -> dict:
    voice = VOICES_BY_ID.get(profile.voice_id)
    data = {key: getattr(profile, key) for key in FIELDS}
    data.update(
        id=profile.id,
        voice_name=voice.name if voice else "",
        script_count=script_count,
        created_at=profile.created_at.isoformat(),
        updated_at=profile.updated_at.isoformat(),
    )
    return data


def list_profiles(db: Session, tenant_id: str) -> list[dict]:
    counts = dict(
        db.execute(
            select(Script.profile_id, func.count())
            .where(Script.tenant_id == tenant_id, Script.profile_id.is_not(None))
            .group_by(Script.profile_id)
        ).all()
    )
    profiles = db.scalars(
        select(BrandProfile).where(BrandProfile.tenant_id == tenant_id).order_by(BrandProfile.created_at)
    ).all()
    return [profile_out(p, counts.get(p.id, 0)) for p in profiles]


def get_profile(db: Session, user: User, profile_id: str) -> BrandProfile:
    profile = db.get(BrandProfile, profile_id)
    if profile is None or profile.tenant_id != user.tenant_id:
        raise not_found("找不到這個帳號檔案", "profile_not_found")
    return profile


def _clean_list(values: list[str], limit: int) -> list[str]:
    out: list[str] = []
    for value in values:
        value = value.strip()
        if value and value not in out:
            out.append(value)
    return out[:limit]


def apply_changes(profile: BrandProfile, changes: dict) -> None:
    if "target_language" in changes and changes["target_language"] not in LANGUAGES:
        raise bad_request("不支援這個語言", "invalid_language")
    if changes.get("voice_id") and changes["voice_id"] not in VOICES_BY_ID:
        raise bad_request("找不到這個音色", "unknown_voice")
    for key, value in changes.items():
        if key not in FIELDS or value is None:
            continue
        if key in ("selling_points", "banned_words"):
            value = _clean_list(value, 12)
        elif key == "hashtags":
            value = _clean_list([("#" + v.strip().lstrip("#")).replace(" ", "") for v in value if v.strip("# ")], 15)
        elif isinstance(value, str):
            value = value.strip()
        setattr(profile, key, value)
    if not profile.name:
        raise bad_request("請填寫名稱", "name_required")
