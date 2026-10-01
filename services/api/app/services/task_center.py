"""任務中心：查看背景任務的進度與錯誤，手動重試失敗的任務。"""

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.errors import conflict, not_found
from app.models import Asset, Script, Task, User, Video, utcnow

TYPE_LABELS = {
    "asset.analyze": "素材分析",
    "script.generate": "產生文案",
    "video.render": "渲染成片",
}


def _target(task: Task) -> str:
    payload = task.payload or {}
    if task.type == "asset.analyze":
        return payload.get("asset_id", "")
    if task.type == "video.render":
        return payload.get("video_id", "")
    if task.type == "script.generate":
        return ",".join(payload.get("script_ids", []))
    return ""


def task_out(task: Task, label: str = "") -> dict:
    return {
        "id": task.id,
        "type": task.type,
        "type_label": TYPE_LABELS.get(task.type, task.type),
        "target": _target(task),
        "label": label,
        "status": task.status,
        "attempts": task.attempts,
        "max_attempts": task.max_attempts,
        "error": task.error,
        "created_at": task.created_at.isoformat(),
        "started_at": task.started_at.isoformat() if task.started_at else None,
        "finished_at": task.finished_at.isoformat() if task.finished_at else None,
        "run_after": task.run_after.isoformat(),
    }


def _labels(db: Session, rows: list[Task]) -> dict[str, str]:
    """給每個任務一個看得懂的名稱（素材檔名 / 成片標題 / 文案模板）。"""
    asset_ids = {(t.payload or {}).get("asset_id") for t in rows if t.type == "asset.analyze"}
    video_ids = {(t.payload or {}).get("video_id") for t in rows if t.type == "video.render"}
    script_ids = {(t.payload or {}).get("script_ids", [None])[0] for t in rows if t.type == "script.generate"}
    names: dict[str, str] = {}
    if asset_ids:
        names.update(dict(db.execute(select(Asset.id, Asset.original_filename).where(Asset.id.in_(asset_ids))).all()))
    if video_ids:
        names.update(dict(db.execute(select(Video.id, Video.title).where(Video.id.in_(video_ids))).all()))
    if script_ids:
        for sid, template, profile in db.execute(
            select(Script.id, Script.template_name, Script.profile_name).where(Script.id.in_(script_ids))
        ).all():
            names[sid] = f"{template} · {profile}"
    out = {}
    for t in rows:
        payload = t.payload or {}
        key = payload.get("asset_id") or payload.get("video_id") or (payload.get("script_ids") or [None])[0]
        out[t.id] = names.get(key, "（已刪除）")
    return out


def list_tasks(db: Session, user: User, *, status: str | None, task_type: str | None, limit: int, offset: int) -> dict:
    where = [or_(Task.tenant_id == user.tenant_id, Task.tenant_id.is_(None))]
    if status:
        where.append(Task.status == status)
    if task_type:
        where.append(Task.type == task_type)
    total = db.scalar(select(func.count()).select_from(Task).where(*where))
    rows = db.scalars(select(Task).where(*where).order_by(Task.created_at.desc()).limit(limit).offset(offset)).all()
    labels = _labels(db, rows)
    counts = dict(
        db.execute(
            select(Task.status, func.count()).where(or_(Task.tenant_id == user.tenant_id, Task.tenant_id.is_(None))).group_by(Task.status)
        ).all()
    )
    return {"items": [task_out(t, labels.get(t.id, "")) for t in rows], "total": total, "counts": counts, "types": TYPE_LABELS}


def retry(db: Session, user: User, task_id: str) -> Task:
    task = db.get(Task, task_id)
    if task is None or task.tenant_id not in (user.tenant_id, None):
        raise not_found("找不到這個任務", "task_not_found")
    if task.status != "failed":
        raise conflict("只有失敗的任務可以重試", "task_not_failed")
    payload = task.payload or {}
    # 對應的資料一起改回「處理中」狀態，畫面才會顯示進度
    if task.type == "asset.analyze" and (asset := db.get(Asset, payload.get("asset_id"))) is not None:
        asset.status, asset.stage, asset.error = "uploaded", "等待分析", ""
    elif task.type == "video.render" and (video := db.get(Video, payload.get("video_id"))) is not None:
        video.status, video.stage, video.error = "queued", "排隊中", ""
    elif task.type == "script.generate":
        for script in db.scalars(select(Script).where(Script.id.in_(payload.get("script_ids", [])))).all():
            script.status, script.error = "generating", ""
    task.status = "queued"
    task.attempts = 0
    task.error = ""
    task.run_after = utcnow()
    task.finished_at = None
    db.commit()
    return task
