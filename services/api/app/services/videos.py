"""成片：建立渲染、作品庫查詢、審核、換素材、重新渲染、刪除、素材覆蓋率檢查。"""

import random
import shutil
from collections import Counter

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.errors import AppError, bad_request, conflict, not_found
from app.models import Asset, Clip, Script, User, Video, new_id, utcnow
from app.services import ai_provider, media, music, posts, renderer, tasks

STATUSES = ("queued", "rendering", "pending_review", "approved", "rejected", "failed")
BUSY = ("queued", "rendering")


def _version(video: Video) -> str:
    stamp = video.rendered_at or video.updated_at
    return str(int(stamp.timestamp()))


def video_out(video: Video) -> dict:
    base = f"/media/{video.tenant_id}/videos/{video.id}"
    v = _version(video)
    return {
        "id": video.id,
        "batch_id": video.batch_id,
        "script_id": video.script_id,
        "profile_id": video.profile_id,
        "title": video.title,
        "template_name": video.template_name,
        "profile_name": video.profile_name,
        "language": video.language,
        "status": video.status,
        "stage": video.stage,
        "error": video.error,
        "style": (video.timeline or {}).get("style") or (video.options or {}).get("style", "random"),
        "duration": video.duration,
        "render_seconds": video.render_seconds,
        "review_note": video.review_note,
        "reviewed_at": video.reviewed_at.isoformat() if video.reviewed_at else None,
        "created_at": video.created_at.isoformat(),
        "rendered_at": video.rendered_at.isoformat() if video.rendered_at else None,
        "video_url": f"{base}/final.mp4?v={v}" if video.has_output else None,
        "poster_url": f"{base}/poster.jpg?v={v}" if video.has_output else None,
    }


def _thumbs(db: Session, clip_ids: set[str]) -> dict[str, dict]:
    if not clip_ids:
        return {}
    rows = db.execute(
        select(Clip.id, Clip.index, Clip.scene, Clip.description, Asset.id, Asset.tenant_id, Asset.original_filename, Asset.analyzed_at, Asset.created_at)
        .join(Asset, Asset.id == Clip.asset_id)
        .where(Clip.id.in_(clip_ids))
    ).all()
    out = {}
    for clip_id, index, scene, description, asset_id, tenant_id, filename, analyzed_at, created_at in rows:
        stamp = int((analyzed_at or created_at).timestamp())
        out[clip_id] = {
            "thumb_url": media.asset_url(tenant_id, asset_id, f"clips/{index:03d}.jpg", str(stamp)),
            "scene": scene,
            "description": description,
            "filename": filename,
        }
    return out


def video_detail(db: Session, video: Video) -> dict:
    data = video_out(video)
    timeline = video.timeline or {}
    shots = timeline.get("shots", [])
    thumbs = _thumbs(db, {seg["clip_id"] for shot in shots for seg in shot.get("segments", [])})
    t = 0.0
    out_shots = []
    for shot in shots:
        out_shots.append(
            {
                "index": shot["index"],
                "brief": shot.get("brief", ""),
                "scene": shot.get("scene", ""),
                "caption": shot.get("caption", ""),
                "voiceover": shot.get("voiceover", ""),
                "start": round(t, 2),
                "duration": shot["duration"],
                "segments": [
                    {
                        "clip_id": seg["clip_id"],
                        "duration": seg["duration"],
                        **thumbs.get(seg["clip_id"], {"thumb_url": None, "scene": "", "description": "（素材已刪除）", "filename": ""}),
                    }
                    for seg in shot.get("segments", [])
                ],
            }
        )
        t += shot["duration"]
    data["shots"] = out_shots
    data["voice_id"] = timeline.get("voice_id")
    data["bgm_title"] = (timeline.get("bgm") or {}).get("title")
    data["ambience"] = timeline.get("ambience", (video.options or {}).get("ambience"))
    return data


# ---------------------------------------------------------------- 建立與查詢
def check_ready(db: Session, tenant_id: str) -> None:
    ai_provider.default_model(db, tenant_id, "tts")
    if not renderer.load_pool(db, tenant_id):
        raise bad_request("素材庫沒有可用的鏡頭，請先到「素材中心」上傳並等待分析完成", "no_clips")


def start_render(
    db: Session,
    user: User,
    script_ids: list[str],
    per_script: int,
    style: str,
    ambience: float,
    bgm: str = "auto",
    bgm_volume: float = music.DEFAULT_VOLUME,
) -> list[Video]:
    if style != "random" and style not in renderer.STYLES:
        raise bad_request("字幕樣式不正確", "invalid_style")
    if bgm not in ("auto", "none"):
        music.get_track(db, user, bgm)
    scripts = db.scalars(select(Script).where(Script.id.in_(script_ids), Script.tenant_id == user.tenant_id)).all()
    if len(scripts) != len(set(script_ids)):
        raise not_found("有文案不存在", "script_not_found")
    if any(s.status != "approved" for s in scripts):
        raise conflict("只有「已核准」的文案可以產生成片", "script_not_approved")
    check_ready(db, user.tenant_id)
    batch_id = new_id()
    videos = []
    for script in scripts:
        for n in range(per_script):
            video = Video(
                id=new_id(),
                tenant_id=user.tenant_id,
                script_id=script.id,
                profile_id=script.profile_id,
                batch_id=batch_id,
                title=f"{script.title or script.template_name}" + (f" #{n + 1}" if per_script > 1 else ""),
                template_name=script.template_name,
                profile_name=script.profile_name,
                language=script.language,
                status="queued",
                stage="排隊中",
                options={
                    "style": style,
                    "ambience": ambience,
                    "bgm": bgm,
                    "bgm_volume": bgm_volume,
                    "seed": random.randrange(1, 2**31),
                },
                created_by=user.id,
            )
            db.add(video)
            videos.append(video)
            tasks.enqueue(db, renderer.TASK_TYPE, {"video_id": video.id, "mode": "plan"}, tenant_id=user.tenant_id, max_attempts=2)
    db.commit()
    return videos


def list_videos(db: Session, user: User, *, status: str | None, script_id: str | None, limit: int, offset: int) -> dict:
    where = [Video.tenant_id == user.tenant_id]
    if status:
        where.append(Video.status == status)
    if script_id:
        where.append(Video.script_id == script_id)
    total = db.scalar(select(func.count()).select_from(Video).where(*where))
    rows = db.scalars(select(Video).where(*where).order_by(Video.created_at.desc()).limit(limit).offset(offset)).all()
    return {"items": [video_out(v) for v in rows], "total": total}


def stats(db: Session, tenant_id: str) -> dict:
    counts = dict(db.execute(select(Video.status, func.count()).where(Video.tenant_id == tenant_id).group_by(Video.status)).all())
    return {s: counts.get(s, 0) for s in STATUSES}


def get_video(db: Session, user: User, video_id: str) -> Video:
    video = db.get(Video, video_id)
    if video is None or video.tenant_id != user.tenant_id:
        raise not_found("找不到這支成片", "video_not_found")
    return video


def coverage(db: Session, user: User, script_ids: list[str]) -> dict:
    """每份文案每個鏡頭的期望畫面，在素材庫裡有幾個可用鏡頭。"""
    pool = renderer.load_pool(db, user.tenant_id)
    by_scene = Counter(c["scene"] for c in pool)
    scripts = db.scalars(select(Script).where(Script.id.in_(script_ids), Script.tenant_id == user.tenant_id)).all()
    try:
        ai_provider.default_model(db, user.tenant_id, "tts")
        tts_ready = True
    except AppError:
        tts_ready = False
    return {
        "total_clips": len(pool),
        "tts_ready": tts_ready,
        "scripts": [
            {
                "id": s.id,
                "shots": [{"scene": shot.get("scene", ""), "clips": by_scene.get(shot.get("scene", ""), 0)} for shot in s.shots],
            }
            for s in scripts
        ],
    }


# ---------------------------------------------------------------- 審核與修改
def _ensure_idle(video: Video) -> None:
    if video.status in BUSY:
        raise conflict("成片正在渲染中，請稍候", "video_busy")


def review(db: Session, user: User, video: Video, action: str, note: str) -> None:
    posts.guard_video(db, video)
    if video.status not in ("pending_review", "approved", "rejected"):
        raise conflict("這支成片目前不能審核", "video_not_reviewable")
    if action == "reject" and not note.strip():
        raise bad_request("退回時請寫下原因，方便之後調整", "note_required")
    video.status = "approved" if action == "approve" else "rejected"
    video.review_note = note.strip()
    video.reviewed_by = user.id
    video.reviewed_at = utcnow()
    db.commit()


def _queue(db: Session, video: Video, mode: str) -> None:
    video.status, video.stage, video.error = "queued", "排隊中", ""
    tasks.enqueue(db, renderer.TASK_TYPE, {"video_id": video.id, "mode": mode}, tenant_id=video.tenant_id, max_attempts=2)
    db.commit()


def replace_clip(db: Session, video: Video, shot_index: int, clip_id: str) -> None:
    posts.guard_video(db, video)
    _ensure_idle(video)
    timeline = dict(video.timeline or {})
    shots = [dict(s) for s in timeline.get("shots", [])]
    if not 0 <= shot_index < len(shots):
        raise bad_request("鏡頭編號不正確", "invalid_shot")
    shot = shots[shot_index]
    need = shot.get("frames") or media.frames(shot["duration"])
    shot["segments"] = renderer.segment_for_clip(db, video.tenant_id, clip_id, shot, need)
    timeline["shots"] = shots
    video.timeline = timeline  # 重新指定整個 JSON，SQLAlchemy 才會偵測到變更
    _queue(db, video, "rerender")


def rerender(db: Session, video: Video, reshuffle: bool) -> None:
    posts.guard_video(db, video)
    _ensure_idle(video)
    if reshuffle:
        video.options = {**(video.options or {}), "seed": random.randrange(1, 2**31)}
    _queue(db, video, "plan" if reshuffle or not video.timeline else "rerender")


def candidates(db: Session, video: Video, shot_index: int, limit: int = 40) -> list[dict]:
    shots = (video.timeline or {}).get("shots", [])
    if not 0 <= shot_index < len(shots):
        raise bad_request("鏡頭編號不正確", "invalid_shot")
    scene = shots[shot_index].get("scene", "")
    current = {seg["clip_id"] for seg in shots[shot_index].get("segments", [])}
    pool = renderer.load_pool(db, video.tenant_id)
    quality_rank = {"good": 0, "ok": 1, "": 2, "poor": 3}
    pool.sort(key=lambda c: (c["scene"] != scene, c["duplicate"], quality_rank.get(c["quality"], 2)))
    pool = [c for c in pool if c["clip_id"] not in current][:limit]
    thumbs = _thumbs(db, {c["clip_id"] for c in pool})
    return [
        {
            "clip_id": c["clip_id"],
            "kind": c["kind"],
            "length": c["length"],
            "quality": c["quality"],
            "scene_match": c["scene"] == scene,
            **thumbs.get(c["clip_id"], {}),
        }
        for c in pool
    ]


def delete_video(db: Session, video: Video) -> None:
    posts.guard_video(db, video)
    if video.status == "rendering":
        raise conflict("成片正在渲染中，請稍候再刪除", "video_busy")
    directory = renderer.video_dir(video.tenant_id, video.id)
    db.delete(video)
    db.commit()
    shutil.rmtree(directory, ignore_errors=True)
