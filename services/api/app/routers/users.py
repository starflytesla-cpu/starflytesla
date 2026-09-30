from fastapi import APIRouter
from sqlalchemy import func, select

from app.deps import DB, AdminUser
from app.errors import bad_request, conflict, not_found
from app.models import User
from app.schemas import UserCreateIn, UserUpdateIn, ok, user_out
from app.security import hash_password, validate_new_password

router = APIRouter(prefix="/api/users", tags=["users"])


def _get_user(db, admin: User, user_id: str) -> User:
    user = db.get(User, user_id)
    if not user or user.tenant_id != admin.tenant_id:
        raise not_found("找不到這個帳號")
    return user


def _active_admin_count(db, tenant_id: str) -> int:
    return db.scalar(
        select(func.count())
        .select_from(User)
        .where(User.tenant_id == tenant_id, User.role == "admin", User.is_active.is_(True))
    )


@router.get("")
def list_users(admin: AdminUser, db: DB):
    users = db.scalars(
        select(User).where(User.tenant_id == admin.tenant_id).order_by(User.created_at)
    ).all()
    return ok([user_out(u) for u in users])


@router.post("")
def create_user(body: UserCreateIn, admin: AdminUser, db: DB):
    email = body.email.lower()
    if db.scalars(select(User).where(func.lower(User.email) == email)).first():
        raise conflict("這個 Email 已經被使用", "email_taken")
    validate_new_password(body.password)
    user = User(
        tenant_id=admin.tenant_id,
        email=email,
        display_name=body.display_name.strip(),
        password_hash=hash_password(body.password),
        role=body.role,
    )
    db.add(user)
    db.commit()
    return ok(user_out(user), "帳號已建立")


@router.patch("/{user_id}")
def update_user(user_id: str, body: UserUpdateIn, admin: AdminUser, db: DB):
    user = _get_user(db, admin, user_id)
    losing_admin = (body.role not in (None, "admin") or body.is_active is False) and (
        user.role == "admin" and user.is_active
    )
    if losing_admin and _active_admin_count(db, admin.tenant_id) <= 1:
        raise bad_request("至少要保留一個啟用中的管理員", "last_admin")
    if body.display_name is not None:
        user.display_name = body.display_name.strip()
    if body.role is not None:
        user.role = body.role
    if body.is_active is not None and body.is_active != user.is_active:
        user.is_active = body.is_active
        user.token_version += 1
    if body.password:
        validate_new_password(body.password)
        user.password_hash = hash_password(body.password)
        user.token_version += 1
    db.commit()
    return ok(user_out(user), "已更新")
