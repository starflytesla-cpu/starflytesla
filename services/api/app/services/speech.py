"""配音：試聽、音色樣本、成片用的配音快取。都經 ai_provider.tts，成本會記錄。

- 試聽檔存在 MEDIA_ROOT/{tenant}/tts/（網頁可以播放），worker 每小時清理 7 天前的檔案
- 音色樣本存在 MEDIA_ROOT/{tenant}/tts/samples/{voice}.*（Gemini 音色沒有官方試聽檔，第一次試聽時產生，之後重用）
- 成片配音存在 MEDIA_ROOT/{tenant}/tts-cache/（不對外提供），同樣的文字 + 音色 + 語氣只產生一次
"""

import hashlib
import time
import uuid
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.errors import bad_request
from app.models import BrandProfile, ChannelModel, ModelChannel, User
from app.services import ai_provider, media
from app.services.voices import DEFAULT_VOICE, VOICES_BY_ID, engine_for_model, resolve_voice

DEFAULT_TEST_TEXT = "Hi there! This is a quick voice test from Starfly. How does it sound?"
SAMPLE_TEXT = "Welcome to our factory. Every part is made, checked and packed right here, ready to ship worldwide."
MAX_PREVIEW_CHARS = 1500
KEEP_SECONDS = 7 * 24 * 3600
AUDIO_EXTENSIONS = (".mp3", ".wav", ".ogg", ".m4a")


def tts_dir(tenant_id: str) -> Path:
    return media.media_root() / tenant_id / "tts"


def default_voice_id(model: ChannelModel | None = None) -> str:
    return DEFAULT_VOICE[engine_for_model(model.model_key) if model else "elevenlabs"]


def voice_style(profile: BrandProfile | None) -> str:
    """給 Gemini TTS 的語氣描述：短影音商業旁白 + 帳號檔案的口吻。"""
    style = "Natural, confident commercial voiceover for a short social media video."
    if profile and profile.tone:
        style += f" Tone: {profile.tone}."
    return style


def profile_voice(model: ChannelModel, profile: BrandProfile | None) -> tuple[str, float, str]:
    """回傳 (音色, 語速, 語氣)；帳號檔案的音色和模型不同引擎時換成該引擎的預設音色。"""
    voice = resolve_voice(model.model_key, profile.voice_id if profile else "")
    return voice, (profile.voice_speed if profile else 1.0), voice_style(profile)


def model_for_voice(db: Session, tenant_id: str, voice_id: str) -> ChannelModel:
    """找能用這個音色的配音模型：預設配音模型同引擎就用它，否則找其他同引擎的模型。"""
    voice = VOICES_BY_ID.get(voice_id)
    if voice is None:
        raise bad_request("找不到這個音色", "unknown_voice")
    default = ai_provider.default_model(db, tenant_id, "tts")
    if engine_for_model(default.model_key) == voice.engine:
        return default
    for model in db.scalars(
        select(ChannelModel)
        .join(ModelChannel)
        .where(
            ModelChannel.tenant_id == tenant_id,
            ModelChannel.enabled.is_(True),
            ChannelModel.enabled.is_(True),
            ChannelModel.capability == "tts",
        )
        .order_by(ChannelModel.created_at)
    ):
        if engine_for_model(model.model_key) == voice.engine:
            return model
    name = "Gemini" if voice.engine == "gemini" else "ElevenLabs"
    raise bad_request(f"沒有可用的 {name} 配音模型，請到「模型渠道」新增或啟用", "no_model")


def _find(base: Path) -> Path | None:
    return next((base.with_suffix(ext) for ext in AUDIO_EXTENSIONS if base.with_suffix(ext).exists()), None)


def _write(base: Path, result: ai_provider.TtsResult) -> Path:
    base.parent.mkdir(parents=True, exist_ok=True)
    path = base.with_suffix(result.extension)
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_bytes(result.audio)
    tmp.replace(path)
    return path


def synthesize(
    db: Session,
    user: User,
    text: str,
    voice_id: str,
    *,
    speed: float = 1.0,
    style: str = "",
    source: str,
    model: ChannelModel | None = None,
) -> dict:
    if voice_id not in VOICES_BY_ID:
        raise bad_request("找不到這個音色", "unknown_voice")
    if len(text) > MAX_PREVIEW_CHARS:
        raise bad_request(f"試聽文字最多 {MAX_PREVIEW_CHARS} 字", "text_too_long")
    model = model or model_for_voice(db, user.tenant_id, voice_id)
    voice_id = resolve_voice(model.model_key, voice_id)
    result = ai_provider.tts(
        db, model, text, voice_id, speed=speed, style=style or voice_style(None), source=source, user=user
    )
    path = _write(tts_dir(user.tenant_id) / uuid.uuid4().hex, result)
    return {
        "audio_url": f"/media/{user.tenant_id}/tts/{path.name}",
        "characters": result.characters,
        "duration_ms": result.duration_ms,
        "cost_micros": result.cost_micros,
    }


def voice_sample(db: Session, user: User, voice_id: str) -> dict:
    """音色試聽樣本：ElevenLabs 用官方免費試聽檔；Gemini 第一次產生後保存重用。"""
    voice = VOICES_BY_ID.get(voice_id)
    if voice is None:
        raise bad_request("找不到這個音色", "unknown_voice")
    if voice.engine == "elevenlabs":
        return {"audio_url": voice.out()["preview_url"], "cost_micros": 0, "cached": True}
    base = tts_dir(user.tenant_id) / "samples" / voice.id
    if (existing := _find(base)) is not None:
        return {"audio_url": f"/media/{user.tenant_id}/tts/samples/{existing.name}", "cost_micros": 0, "cached": True}
    model = model_for_voice(db, user.tenant_id, voice_id)
    result = ai_provider.tts(
        db, model, SAMPLE_TEXT, voice.id, style=voice_style(None), source="voice_sample", user=user
    )
    path = _write(base, result)
    return {"audio_url": f"/media/{user.tenant_id}/tts/samples/{path.name}", "cost_micros": result.cost_micros, "cached": False}


def cached_tts(
    db: Session,
    user: User | None,
    model: ChannelModel,
    tenant_id: str,
    text: str,
    voice_id: str,
    speed: float,
    style: str,
    *,
    source: str,
) -> tuple[str, float]:
    """成片配音：回傳 (整理後 WAV 相對 MEDIA_ROOT 的路徑, 秒數)。同樣的模型、音色、語速、語氣、文字只產生一次。

    整理：去掉頭尾靜音、統一音量（media.clean_voice），鏡頭之間的停頓才會一致、音量不忽大忽小。
    """
    raw = f"{model.model_key}|{voice_id}|{speed:.2f}|{style}|{text}"
    base = media.media_root() / tenant_id / "tts-cache" / hashlib.sha256(raw.encode()).hexdigest()[:40]
    clean = base.with_name(base.name + ".clean.wav")
    if not clean.exists():
        path = _find(base)
        if path is None:
            result = ai_provider.tts(db, model, text, voice_id, speed=speed, style=style, source=source, user=user)
            path = _write(base, result)
        media.clean_voice(path, clean)
    return str(clean.relative_to(media.media_root())), media.audio_duration(clean)


def cleanup_previews() -> int:
    """刪除 7 天前的試聽檔（不含音色樣本），回傳刪除數量。"""
    cutoff = time.time() - KEEP_SECONDS
    removed = 0
    for path in media.media_root().glob("*/tts/*"):
        try:
            if path.is_file() and path.stat().st_mtime < cutoff:
                path.unlink()
                removed += 1
        except OSError:
            continue
    return removed
