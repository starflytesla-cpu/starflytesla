import logging

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.models import Tenant, User
from app.security import hash_password

log = logging.getLogger(__name__)


def ensure_initial_admin(db: Session) -> None:
    """資料庫沒有任何使用者時，用 ADMIN_EMAIL / ADMIN_PASSWORD 建立預設租戶與管理員。"""
    if db.scalar(select(func.count()).select_from(User)):
        return
    settings = get_settings()
    if not settings.admin_email or not settings.admin_password:
        log.warning("尚無任何使用者，且未設定 ADMIN_EMAIL / ADMIN_PASSWORD，無法建立管理員")
        return
    tenant = db.scalars(select(Tenant).order_by(Tenant.created_at)).first()
    if not tenant:
        tenant = Tenant(name="預設")
        db.add(tenant)
        db.flush()
    db.add(
        User(
            tenant_id=tenant.id,
            email=settings.admin_email.lower(),
            display_name="管理員",
            password_hash=hash_password(settings.admin_password),
            role="admin",
        )
    )
    db.commit()
    log.info("已建立初始管理員 %s", settings.admin_email)
