"""素材庫：查詢、輸出格式、修改、刪除、重新分析。"""

import re
import shutil

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.errors import bad_request, conflict, forbidden, not_found
from app.models import Asset, Clip, User
from app.schemas import AssetUpdateIn, ClipUpdateIn
from app.services import asset_analyzer, media, tasks

STATUSES = ("uploaded", "processing", "ready", "failed", "duplicate")


def _version(asset: Asset) -> str:
    stamp = asset.analyzed_at or asset.created_at
    return str(int(stamp.timestamp()))


def asset_out(asset: Asset, uploader_name: str | None = None, clip_count: int | None = None) -> dict:
    v = _version(asset)
    url = lambda name: media.asset_url(asset.tenant_id, asset.id, name, v)  # noqa: E731
    has_original = asset.status != "duplicate"
    return {
        "id": asset.id,
        "original_filename": asset.original_filename,
        "kind": asset.kind,
        "status": asset.status,
        "stage": asset.stage,
        "error": asset.error,
        "size_bytes": asset.size_bytes,
        "duration": asset.duration,
        "width": asset.width,
        "height": asset.height,
        "fps": asset.fps,
        "has_audio": asset.has_audio,
        "category": asset.category,
        "note": asset.note,
        "is_disabled": asset.is_disabled,
        "duplicate_of": asset.duplicate_of,
        "uploaded_by": asset.uploaded_by,
        "uploaded_by_name": uploader_name or "",
        "clip_count": clip_count,
        "created_at": asset.created_at.isoformat(),
        "analyzed_at": asset.analyzed_at.isoformat() if asset.analyzed_at else None,
        "poster_url": url("poster.jpg") if asset.has_poster else None,
        "proxy_url": url("proxy.mp4") if asset.has_proxy else None,
        "original_url": f"/media/{asset.storage_key}" if has_original else None,
    }


def clip_out(clip: Clip, asset: Asset, duplicates: dict[str, tuple[str, str, int]]) -> dict:
    dup = duplicates.get(clip.duplicate_of_clip_id or "")
    return {
        "id": clip.id,
        "asset_id": clip.asset_id,
        "index": clip.index,
        "start": clip.start,
        "end": clip.end,
        "duration": round(clip.end - clip.start, 3),
        "scene": clip.scene,
        "subjects": clip.subjects or [],
        "tags": clip.tags or [],
        "description": clip.description,
        "quality": clip.quality,
        "is_dark": clip.is_dark,
        "is_disabled": clip.is_disabled,
        "tagged_by": clip.tagged_by,
        "thumb_url": media.asset_url(asset.tenant_id, asset.id, f"clips/{clip.index:03d}.jpg", _version(asset)),
        "duplicate_of": (
            {"clip_id": clip.duplicate_of_clip_id, "asset_id": dup[0], "filename": dup[1], "index": dup[2]}
            if dup
            else None
        ),
    }


def list_assets(
    db: Session,
    user: User,
    *,
    status: str | None,
    category: str | None,
    kind: str | None,
    q: str | None,
    mine: bool,
    limit: int,
    offset: int,
) -> dict:
    where = [Asset.tenant_id == user.tenant_id]
    if status:
        where.append(Asset.status == status)
    if category:
        where.append(Asset.category == category)
    if kind:
        where.append(Asset.kind == kind)
    if mine:
        where.append(Asset.uploaded_by == user.id)
    if q and q.strip():
        pattern = "%" + re.sub(r"([%_\\])", r"\\\1", q.strip()) + "%"
        where.append(or_(Asset.original_filename.ilike(pattern), Asset.note.ilike(pattern)))

    total = db.scalar(select(func.count()).select_from(Asset).where(*where))
    clip_count = (
        select(func.count()).where(Clip.asset_id == Asset.id).correlate(Asset).scalar_subquery()
    )
    rows = db.execute(
        select(Asset, User.display_name, clip_count)
        .outerjoin(User, User.id == Asset.uploaded_by)
        .where(*where)
        .order_by(Asset.created_at.desc())
        .limit(limit)
        .offset(offset)
    ).all()
    return {"items": [asset_out(a, name, n) for a, name, n in rows], "total": total}


def stats(db: Session, tenant_id: str) -> dict:
    by_status = dict(
        db.execute(
            select(Asset.status, func.count()).where(Asset.tenant_id == tenant_id).group_by(Asset.status)
        ).all()
    )
    by_category = dict(
        db.execute(
            select(Asset.category, func.count())
            .where(Asset.tenant_id == tenant_id, Asset.status == "ready", Asset.category != "")
            .group_by(Asset.category)
        ).all()
    )
    clips = db.scalar(
        select(func.count())
        .select_from(Clip)
        .where(Clip.tenant_id == tenant_id, Clip.is_disabled.is_(False))
    )
    return {
        "total": sum(by_status.values()),
        "by_status": {s: by_status.get(s, 0) for s in STATUSES},
        "by_category": by_category,
        "clips": clips,
    }


def get_asset(db: Session, user: User, asset_id: str) -> Asset:
    asset = db.get(Asset, asset_id)
    if asset is None or asset.tenant_id != user.tenant_id:
        raise not_found("找不到這個素材", "asset_not_found")
    return asset


def asset_detail(db: Session, asset: Asset) -> dict:
    uploader = db.get(User, asset.uploaded_by) if asset.uploaded_by else None
    dup_ids = {c.duplicate_of_clip_id for c in asset.clips if c.duplicate_of_clip_id}
    duplicates = {
        clip_id: (asset_id, filename, index)
        for clip_id, asset_id, filename, index in db.execute(
            select(Clip.id, Asset.id, Asset.original_filename, Clip.index)
            .join(Asset, Asset.id == Clip.asset_id)
            .where(Clip.id.in_(dup_ids))
        ).all()
    } if dup_ids else {}
    data = asset_out(asset, uploader.display_name if uploader else None, len(asset.clips))
    data["clips"] = [clip_out(c, asset, duplicates) for c in asset.clips]
    if asset.duplicate_of:
        original = db.get(Asset, asset.duplicate_of)
        data["duplicate_of_filename"] = original.original_filename if original else ""
    return data


def _check_scene(scene: str) -> None:
    if scene and scene not in asset_analyzer.SCENES:
        raise bad_request("場景分類不正確", "invalid_scene")


def update_asset(db: Session, asset: Asset, body: AssetUpdateIn) -> None:
    if body.category is not None:
        _check_scene(body.category)
        asset.category = body.category
    if body.note is not None:
        asset.note = body.note.strip()
    if body.is_disabled is not None:
        asset.is_disabled = body.is_disabled
    db.commit()


def delete_asset(db: Session, user: User, asset: Asset) -> None:
    if user.role != "admin" and asset.uploaded_by != user.id:
        raise forbidden("只能刪除自己上傳的素材")
    directory = media.asset_dir(asset.tenant_id, asset.id)
    db.delete(asset)
    db.commit()
    shutil.rmtree(directory, ignore_errors=True)


def reanalyze(db: Session, asset: Asset) -> None:
    if asset.status in ("uploaded", "processing"):
        raise conflict("素材正在分析中，請稍候", "asset_busy")
    if asset.status == "duplicate":
        raise conflict("重複的素材沒有保留檔案，無法重新分析", "asset_duplicate")
    asset.status = "uploaded"
    asset.stage = "等待分析"
    asset.error = ""
    tasks.enqueue(db, asset_analyzer.TASK_TYPE, {"asset_id": asset.id}, tenant_id=asset.tenant_id)
    db.commit()


def get_clip(db: Session, user: User, clip_id: str) -> Clip:
    clip = db.get(Clip, clip_id)
    if clip is None or clip.tenant_id != user.tenant_id:
        raise not_found("找不到這個鏡頭", "clip_not_found")
    return clip


def update_clip(db: Session, clip: Clip, body: ClipUpdateIn) -> None:
    fields = body.model_dump(exclude_unset=True)
    if "scene" in fields:
        _check_scene(fields["scene"] or "")
    for key, value in fields.items():
        if value is None:
            continue
        setattr(clip, key, value.strip() if isinstance(value, str) else value)
    if set(fields) - {"is_disabled"}:
        clip.tagged_by = "manual"
    db.flush()
    asset = clip.asset
    if "scene" in fields and asset.status == "ready":
        asset.category = asset_analyzer.dominant_scene(asset.clips)
    db.commit()
