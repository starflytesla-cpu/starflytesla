from fastapi import APIRouter, Query

from app.deps import DB, AdminUser
from app.schemas import ok
from app.services import task_center

router = APIRouter(prefix="/api/tasks", tags=["tasks"])


@router.get("")
def list_tasks(
    admin: AdminUser,
    db: DB,
    status: str | None = Query(None, pattern="^(queued|running|succeeded|failed)$"),
    type: str | None = Query(None, max_length=48),
    limit: int = Query(30, ge=1, le=100),
    offset: int = Query(0, ge=0),
):
    return ok(task_center.list_tasks(db, admin, status=status, task_type=type, limit=limit, offset=offset))


@router.post("/{task_id}/retry")
def retry(task_id: str, admin: AdminUser, db: DB):
    return ok(task_center.task_out(task_center.retry(db, admin, task_id)), "已重新排入佇列")
