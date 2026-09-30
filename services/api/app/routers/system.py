from fastapi import APIRouter
from sqlalchemy import func, select, text

from app.deps import DB, CurrentUser
from app.errors import AppError
from app.models import ChannelModel, ModelChannel, User
from app.routers.usage import month_summary
from app.schemas import ok

router = APIRouter(prefix="/api", tags=["system"])


@router.get("/health")
def health(db: DB):
    try:
        db.execute(text("SELECT 1"))
    except Exception:
        raise AppError(503, "database_unavailable", "資料庫無法連線") from None
    return ok({"status": "ok"})


@router.get("/dashboard")
def dashboard(user: CurrentUser, db: DB):
    tenant_id = user.tenant_id
    capabilities = db.scalars(
        select(ChannelModel.capability)
        .join(ModelChannel)
        .where(
            ModelChannel.tenant_id == tenant_id,
            ModelChannel.enabled.is_(True),
            ModelChannel.api_key_encrypted != "",
            ChannelModel.enabled.is_(True),
        )
        .distinct()
    ).all()
    data = {
        "users": db.scalar(
            select(func.count()).select_from(User).where(User.tenant_id == tenant_id)
        ),
        "channels": db.scalar(
            select(func.count()).select_from(ModelChannel).where(ModelChannel.tenant_id == tenant_id)
        ),
        "ready_capabilities": sorted(capabilities),
        "month": month_summary(db, tenant_id) if user.role == "admin" else None,
    }
    return ok(data)
