from fastapi import APIRouter

from app.deps import DB, AdminUser
from app.schemas import MusicGenerateIn, MusicUpdateIn, ok
from app.services import music

router = APIRouter(prefix="/api/music", tags=["music"])


@router.get("")
def list_music(admin: AdminUser, db: DB):
    return ok({"items": music.list_tracks(db, admin.tenant_id), "presets": list(music.STYLE_PRESETS)})


@router.post("/generate")
def generate(body: MusicGenerateIn, admin: AdminUser, db: DB):
    track = music.start_generate(db, admin, body.preset, body.extra, body.title)
    return ok(music.track_out(track), "已開始產生，約 1～3 分鐘")


@router.patch("/{track_id}")
def update(track_id: str, body: MusicUpdateIn, admin: AdminUser, db: DB):
    track = music.get_track(db, admin, track_id)
    music.update_track(db, track, body.title, body.is_active)
    return ok(music.track_out(track), "已儲存")


@router.delete("/{track_id}")
def delete(track_id: str, admin: AdminUser, db: DB):
    music.delete_track(db, music.get_track(db, admin, track_id))
    return ok(None, "已刪除")
