from datetime import UTC, datetime

from fastapi import APIRouter, Query
from sqlalchemy import func, select

from app.deps import DB, AdminUser
from app.models import ModelChannel, PublishChannel, UsageLedger, User
from app.schemas import micros_to_usd, ok

router = APIRouter(prefix="/api", tags=["usage"])


def month_start() -> datetime:
    now = datetime.now(UTC)
    return now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)


def month_summary(db, tenant_id: str) -> dict:
    row = db.execute(
        select(
            func.count(),
            func.coalesce(func.sum(UsageLedger.cost_micros), 0),
            func.count().filter(UsageLedger.status == "failed"),
            func.count().filter(
                UsageLedger.status.in_(("succeeded", "pending", "uncertain")), UsageLedger.cost_micros.is_(None)
            ),
        ).where(UsageLedger.tenant_id == tenant_id, UsageLedger.created_at >= month_start())
    ).one()
    return {
        "calls": row[0],
        "cost_usd": micros_to_usd(row[1]),
        "failed": row[2],
        "unpriced": row[3],
    }


@router.get("/usage")
def list_usage(
    admin: AdminUser,
    db: DB,
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    status: str | None = Query(None, pattern="^(succeeded|failed|pending|uncertain)$"),
):
    where = [UsageLedger.tenant_id == admin.tenant_id]
    if status:
        where.append(UsageLedger.status == status)
    total = db.scalar(select(func.count()).select_from(UsageLedger).where(*where))
    rows = db.execute(
        select(UsageLedger, func.coalesce(ModelChannel.name, PublishChannel.name), User.display_name)
        .outerjoin(ModelChannel, ModelChannel.id == UsageLedger.channel_id)
        .outerjoin(PublishChannel, PublishChannel.id == UsageLedger.publish_channel_id)
        .outerjoin(User, User.id == UsageLedger.user_id)
        .where(*where)
        .order_by(UsageLedger.created_at.desc())
        .limit(limit)
        .offset(offset)
    ).all()
    items = [
        {
            "id": entry.id,
            "created_at": entry.created_at.isoformat(),
            "action": entry.action,
            "post_id": entry.post_id,
            "comment_id": entry.comment_id,
            "source": entry.source,
            "channel_name": channel_name or "（已刪除）",
            "provider": entry.provider,
            "model_key": entry.model_key,
            "status": entry.status,
            "input_tokens": entry.input_tokens,
            "output_tokens": entry.output_tokens,
            "duration_ms": entry.duration_ms,
            "cost_usd": micros_to_usd(entry.cost_micros),
            "error": entry.error,
            "user_name": user_name or "系統",
        }
        for entry, channel_name, user_name in rows
    ]
    return ok({"items": items, "total": total})


@router.get("/usage/summary")
def usage_summary(admin: AdminUser, db: DB):
    by_model = db.execute(
        select(
            UsageLedger.provider,
            UsageLedger.model_key,
            func.count(),
            func.sum(UsageLedger.input_tokens),
            func.sum(UsageLedger.output_tokens),
            func.coalesce(func.sum(UsageLedger.cost_micros), 0),
        )
        .where(UsageLedger.tenant_id == admin.tenant_id, UsageLedger.created_at >= month_start())
        .group_by(UsageLedger.provider, UsageLedger.model_key)
        .order_by(func.coalesce(func.sum(UsageLedger.cost_micros), 0).desc())
    ).all()
    return ok(
        {
            "month": month_summary(db, admin.tenant_id),
            "by_model": [
                {
                    "provider": provider,
                    "model_key": model_key,
                    "calls": calls,
                    "input_tokens": int(inp or 0),
                    "output_tokens": int(out or 0),
                    "cost_usd": micros_to_usd(cost),
                }
                for provider, model_key, calls, inp, out, cost in by_model
            ],
        }
    )
