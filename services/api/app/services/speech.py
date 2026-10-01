"""配音試聽：呼叫 ai_provider.tts 產生 mp3，存到 MEDIA_ROOT/{tenant}/tts/，回傳網址。

試聽檔是暫存的，worker 每小時清理 7 天前的檔案；正式成片的配音在 Phase 3 由渲染任務另外保存。
"""

import time
import uuid
from pathlib import Path

from sqlalchemy.orm import Session

from app.errors import bad_request
from app.models import ChannelModel, User
from app.services import ai_provider, media
from app.services.voices import VOICES, VOICES_BY_ID

DEFAULT_TEST_TEXT = "Hi there! This is a quick voice test from Starfly. How does it sound?"
MAX_PREVIEW_CHARS = 1500
KEEP_SECONDS = 7 * 24 * 3600


def tts_dir(tenant_id: str) -> Path:
    return media.media_root() / tenant_id / "tts"


def default_voice_id() -> str:
    return next(v.id for v in VOICES if v.recommended)


def synthesize(
    db: Session,
    user: User,
    text: str,
    voice_id: str,
    *,
    speed: float = 1.0,
    source: str,
    model: ChannelModel | None = None,
) -> dict:
    if voice_id not in VOICES_BY_ID:
        raise bad_request("找不到這個音色", "unknown_voice")
    if len(text) > MAX_PREVIEW_CHARS:
        raise bad_request(f"試聽文字最多 {MAX_PREVIEW_CHARS} 字", "text_too_long")
    model = model or ai_provider.default_model(db, user.tenant_id, "tts")
    result = ai_provider.tts(db, model, text, voice_id, speed=speed, source=source, user=user)
    directory = tts_dir(user.tenant_id)
    directory.mkdir(parents=True, exist_ok=True)
    name = f"{uuid.uuid4().hex}.mp3"
    (directory / name).write_bytes(result.audio)
    return {
        "audio_url": f"/media/{user.tenant_id}/tts/{name}",
        "characters": result.characters,
        "duration_ms": result.duration_ms,
        "cost_micros": result.cost_micros,
    }


def cleanup_previews() -> int:
    """刪除 7 天前的試聽檔，回傳刪除數量。"""
    cutoff = time.time() - KEEP_SECONDS
    removed = 0
    for path in media.media_root().glob("*/tts/*.mp3"):
        try:
            if path.stat().st_mtime < cutoff:
                path.unlink()
                removed += 1
        except OSError:
            continue
    return removed
