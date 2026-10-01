"""背景音樂庫：上傳音樂、用 AI（kie.ai Suno）產生純音樂、渲染時為每支成片挑一首。

檔案在 MEDIA_ROOT/{tenant}/music/{track_id}.{ext}，網址 /media/{tenant}/music/... 經 /api/media/auth 檢查權限。
同一支成片從頭到尾只用同一首（解決各片段原聲不一致的問題），配音時自動壓低音量（見 media.compose_final）。
"""

import logging
import random
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.errors import AppError, bad_request, conflict, not_found
from app.models import MusicTrack, Task, Upload, User, new_id
from app.services import ai_provider, media, tasks
from app.services.tasks import will_retry

log = logging.getLogger("starfly.music")

TASK_TYPE = "music.generate"
EXTENSIONS = {".mp3", ".m4a", ".aac", ".wav", ".ogg"}
MAX_UPLOAD_BYTES = 50 * 1024 * 1024
DEFAULT_VOLUME = 0.22

# 產生時可選的風格（給 Suno 的英文描述）
STYLE_PRESETS = {
    "corporate": "upbeat corporate background music, positive, modern, light percussion, no vocals",
    "industrial": "modern industrial electronic background beat, confident, rhythmic, no vocals",
    "inspiring": "inspiring cinematic background music, warm piano and strings, building, no vocals",
    "chill": "chill lo-fi background music, relaxed, soft beat, no vocals",
    "energetic": "energetic pop background track for social media, catchy, upbeat, no vocals",
}


def music_dir(tenant_id: str) -> Path:
    return media.media_root() / tenant_id / "music"


def track_out(track: MusicTrack) -> dict:
    url = f"/media/{track.storage_key}?v={int(track.created_at.timestamp())}" if track.storage_key and track.status == "ready" else None
    return {
        "id": track.id,
        "title": track.title,
        "source": track.source,
        "style": track.style,
        "status": track.status,
        "error": track.error,
        "duration": track.duration,
        "size_bytes": track.size_bytes,
        "is_active": track.is_active,
        "audio_url": url,
        "created_at": track.created_at.isoformat(),
    }


def list_tracks(db: Session, tenant_id: str) -> list[dict]:
    rows = db.scalars(select(MusicTrack).where(MusicTrack.tenant_id == tenant_id).order_by(MusicTrack.created_at.desc())).all()
    return [track_out(t) for t in rows]


def get_track(db: Session, user: User, track_id: str) -> MusicTrack:
    track = db.get(MusicTrack, track_id)
    if track is None or track.tenant_id != user.tenant_id:
        raise not_found("找不到這首音樂", "music_not_found")
    return track


def update_track(db: Session, track: MusicTrack, title: str | None, is_active: bool | None) -> None:
    if title is not None:
        if not title.strip():
            raise bad_request("請填寫名稱", "title_required")
        track.title = title.strip()[:120]
    if is_active is not None:
        track.is_active = is_active
    db.commit()


def delete_track(db: Session, track: MusicTrack) -> None:
    if track.status == "generating":
        raise conflict("音樂還在產生中，請稍候再刪除", "music_busy")
    path = media.media_root() / track.storage_key if track.storage_key else None
    db.delete(track)
    db.commit()
    if path is not None:
        path.unlink(missing_ok=True)


# ---------------------------------------------------------------- 上傳
def register_upload(db: Session, upload: Upload, part: Path) -> MusicTrack:
    """tus 上傳完成：確認是可播放的音檔、搬到音樂目錄、建立記錄。"""
    ext = Path(upload.filename).suffix.lower()
    track_id = new_id()
    directory = music_dir(upload.tenant_id)
    directory.mkdir(parents=True, exist_ok=True)
    dest = directory / f"{track_id}{ext}"
    part.replace(dest)
    try:
        duration = media.audio_duration(dest)
    except media.MediaError:
        dest.unlink(missing_ok=True)
        raise bad_request("無法讀取這個音檔，請確認是 mp3 / m4a / wav 等音樂檔", "invalid_audio") from None
    track = MusicTrack(
        id=track_id,
        tenant_id=upload.tenant_id,
        title=Path(upload.filename).stem[:120] or "未命名音樂",
        source="upload",
        status="ready",
        storage_key=str(dest.relative_to(media.media_root())),
        duration=round(duration, 2),
        size_bytes=dest.stat().st_size,
        created_by=upload.user_id,
    )
    db.add(track)
    return track


# ---------------------------------------------------------------- AI 產生
def start_generate(db: Session, user: User, preset: str, extra: str, title: str) -> MusicTrack:
    if preset not in STYLE_PRESETS:
        raise bad_request("音樂風格不正確", "invalid_style")
    ai_provider.default_model(db, user.tenant_id, "music")  # 沒有音樂模型時立即提示
    style = STYLE_PRESETS[preset] + (f", {extra.strip()}" if extra.strip() else "")
    track = MusicTrack(
        tenant_id=user.tenant_id,
        title=title.strip()[:120] or "AI 背景音樂",
        source="ai",
        style=style[:500],
        status="generating",
        created_by=user.id,
    )
    db.add(track)
    db.flush()
    tasks.enqueue(db, TASK_TYPE, {"track_id": track.id}, tenant_id=user.tenant_id, max_attempts=2)
    db.commit()
    return track


class MusicError(Exception):
    def __init__(self, message: str, *, retryable: bool):
        super().__init__(message)
        self.retryable = retryable


def _save(track: MusicTrack, audio: bytes) -> None:
    ext = ai_provider.audio_extension(audio)
    directory = music_dir(track.tenant_id)
    directory.mkdir(parents=True, exist_ok=True)
    dest = directory / f"{track.id}{ext}"
    dest.write_bytes(audio)
    track.storage_key = str(dest.relative_to(media.media_root()))
    track.size_bytes = len(audio)
    track.duration = round(media.audio_duration(dest), 2)
    track.status = "ready"
    track.error = ""


def generate_task(db: Session, task: Task) -> dict:
    track = db.get(MusicTrack, task.payload.get("track_id"))
    if track is None:
        return {"skipped": "track_deleted"}
    track.status, track.error = "generating", ""
    db.commit()
    try:
        model = ai_provider.default_model(db, track.tenant_id, "music")
        creator = db.get(User, track.created_by) if track.created_by else None
        result = ai_provider.music(db, model, track.style, track.title, source="music_generate", user=creator)
        _save(track, result.tracks[0])
        for n, audio in enumerate(result.tracks[1:], 2):
            extra = MusicTrack(
                tenant_id=track.tenant_id, title=f"{track.title} ({n})", source="ai", style=track.style,
                status="ready", created_by=track.created_by,
            )
            db.add(extra)
            db.flush()
            _save(extra, audio)
        db.commit()
        return {"tracks": len(result.tracks)}
    except Exception as exc:
        db.rollback()
        track = db.get(MusicTrack, track.id)
        if track is None:
            return {"skipped": "track_deleted"}
        if isinstance(exc, AppError):
            message, retryable = exc.message, exc.status >= 500
        elif isinstance(exc, media.MediaError):
            message, retryable = str(exc), True
        else:
            log.exception("背景音樂產生失敗")
            message, retryable = "產生背景音樂時發生未預期的錯誤", True
        retrying = retryable and will_retry(task)
        track.status = "generating" if retrying else "failed"
        track.error = (f"{message}，稍後自動重試" if retrying else message)[:500]
        db.commit()
        raise MusicError(message, retryable=retryable) from exc


# ---------------------------------------------------------------- 渲染時挑選
def pick_for_video(db: Session, tenant_id: str, options: dict, rng: random.Random) -> dict | None:
    """依產生選項挑背景音樂：auto 隨機（同批成片各自不同）、none 不用、或指定某一首。"""
    choice = options.get("bgm", "auto")
    volume = float(options.get("bgm_volume", DEFAULT_VOLUME))
    if choice == "none" or volume <= 0:
        return None
    tracks = db.scalars(
        select(MusicTrack).where(
            MusicTrack.tenant_id == tenant_id, MusicTrack.status == "ready", MusicTrack.storage_key != ""
        ).order_by(MusicTrack.created_at)
    ).all()
    track = next((t for t in tracks if t.id == choice), None)
    if track is None:
        active = [t for t in tracks if t.is_active]
        if not active:
            return None
        track = rng.choice(active)
    return {"track_id": track.id, "title": track.title, "source": track.storage_key, "volume": round(volume, 3)}

