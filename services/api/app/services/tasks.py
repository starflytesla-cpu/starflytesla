"""背景任務佇列：API 用 enqueue 排入，worker（app/worker.py）用 claim 領取。

用 PostgreSQL 的 SELECT … FOR UPDATE SKIP LOCKED，多個 worker 同時領取也不會拿到同一個任務。
執行中的任務每 30 秒延長一次租約；worker 當機時租約在 2 分鐘內過期，任務會被重新領取。
"""

from datetime import timedelta

from sqlalchemy import and_, or_, select, update
from sqlalchemy.orm import Session

from app.models import Task, utcnow

LEASE = timedelta(minutes=2)


def enqueue(
    db: Session,
    task_type: str,
    payload: dict,
    *,
    tenant_id: str | None = None,
    max_attempts: int = 3,
) -> Task:
    """排入任務；由呼叫端 commit，讓任務與相關資料在同一個交易內寫入。"""
    task = Task(type=task_type, payload=payload, tenant_id=tenant_id, max_attempts=max_attempts)
    db.add(task)
    return task


def claim(db: Session, worker_id: str) -> Task | None:
    while True:
        now = utcnow()
        task = db.scalars(
            select(Task)
            .where(
                or_(
                    and_(Task.status == "queued", Task.run_after <= now),
                    and_(Task.status == "running", Task.lease_expires_at < now),
                )
            )
            .order_by(Task.run_after)
            .limit(1)
            .with_for_update(skip_locked=True)
        ).first()
        if task is None:
            db.rollback()
            return None
        if task.status == "running" and task.attempts >= task.max_attempts:
            # 執行到一半 worker 當機、且已經沒有重試次數
            task.status = "failed"
            task.error = (task.error or "處理中斷次數過多，已停止重試")[:1000]
            task.finished_at = now
            task.locked_by = ""
            task.lease_expires_at = None
            db.commit()
            continue
        task.status = "running"
        task.attempts += 1
        task.locked_by = worker_id
        task.lease_expires_at = now + LEASE
        task.started_at = now
        db.commit()
        return task


def heartbeat(db: Session, worker_id: str, task_ids: list[str]) -> None:
    if not task_ids:
        return
    db.execute(
        update(Task)
        .where(Task.id.in_(task_ids), Task.locked_by == worker_id, Task.status == "running")
        .values(lease_expires_at=utcnow() + LEASE)
    )
    db.commit()


def complete(db: Session, task: Task, result: dict | None = None) -> None:
    task.status = "succeeded"
    task.result = result or {}
    task.error = ""
    task.finished_at = utcnow()
    task.locked_by = ""
    task.lease_expires_at = None
    db.commit()


def fail(db: Session, task: Task, error: str, *, retryable: bool = True) -> bool:
    """記錄失敗；還有重試次數時排回佇列並回傳 True。"""
    task.error = error[:1000]
    task.locked_by = ""
    task.lease_expires_at = None
    if retryable and task.attempts < task.max_attempts:
        task.status = "queued"
        task.run_after = utcnow() + timedelta(seconds=30 * 2 ** (task.attempts - 1))
        db.commit()
        return True
    task.status = "failed"
    task.finished_at = utcnow()
    db.commit()
    return False


def release(db: Session, task: Task) -> None:
    """worker 停止時把任務放回佇列，這次不算一次嘗試。"""
    task.status = "queued"
    task.attempts = max(0, task.attempts - 1)
    task.locked_by = ""
    task.lease_expires_at = None
    task.run_after = utcnow()
    db.commit()


def will_retry(task: Task) -> bool:
    return task.attempts < task.max_attempts
