from fastapi import APIRouter, Query

from app.deps import DB, AdminUser
from app.schemas import CoverageIn, RenderIn, ReplaceClipIn, RerenderIn, ReviewIn, ok
from app.services import renderer, videos

router = APIRouter(prefix="/api/videos", tags=["videos"])


@router.get("")
def list_videos(
    admin: AdminUser,
    db: DB,
    status: str | None = Query(None, pattern="^(queued|rendering|pending_review|approved|rejected|failed)$"),
    script_id: str | None = Query(None, max_length=36),
    limit: int = Query(24, ge=1, le=100),
    offset: int = Query(0, ge=0),
):
    return ok(videos.list_videos(db, admin, status=status, script_id=script_id, limit=limit, offset=offset))


@router.get("/stats")
def video_stats(admin: AdminUser, db: DB):
    return ok(videos.stats(db, admin.tenant_id))


@router.get("/styles")
def styles(admin: AdminUser):
    return ok({key: value["label"] for key, value in renderer.STYLES.items()})


@router.post("/coverage")
def coverage(body: CoverageIn, admin: AdminUser, db: DB):
    return ok(videos.coverage(db, admin, body.script_ids))


@router.post("/generate")
def generate(body: RenderIn, admin: AdminUser, db: DB):
    created = videos.start_render(
        db, admin, body.script_ids, body.per_script, body.style, body.ambience, body.bgm, body.bgm_volume
    )
    return ok([videos.video_out(v) for v in created], f"已排入 {len(created)} 支成片，每支約 1～3 分鐘")


@router.get("/{video_id}")
def get_video(video_id: str, admin: AdminUser, db: DB):
    return ok(videos.video_detail(db, videos.get_video(db, admin, video_id)))


@router.post("/{video_id}/review")
def review(video_id: str, body: ReviewIn, admin: AdminUser, db: DB):
    video = videos.get_video(db, admin, video_id)
    videos.review(db, admin, video, body.action, body.note)
    return ok(videos.video_detail(db, video), "已通過" if body.action == "approve" else "已退回")


@router.get("/{video_id}/candidates")
def candidates(video_id: str, admin: AdminUser, db: DB, shot: int = Query(ge=0, le=50)):
    return ok(videos.candidates(db, videos.get_video(db, admin, video_id), shot))


@router.post("/{video_id}/replace")
def replace(video_id: str, body: ReplaceClipIn, admin: AdminUser, db: DB):
    video = videos.get_video(db, admin, video_id)
    videos.replace_clip(db, video, body.shot_index, body.clip_id)
    return ok(videos.video_detail(db, video), "已換素材，重新渲染中")


@router.post("/{video_id}/rerender")
def rerender(video_id: str, body: RerenderIn, admin: AdminUser, db: DB):
    video = videos.get_video(db, admin, video_id)
    videos.rerender(db, video, body.reshuffle)
    return ok(videos.video_detail(db, video), "已重新挑素材並渲染" if body.reshuffle else "已重新渲染")


@router.delete("/{video_id}")
def delete_video(video_id: str, admin: AdminUser, db: DB):
    videos.delete_video(db, videos.get_video(db, admin, video_id))
    return ok(None, "已刪除")
