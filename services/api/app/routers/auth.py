from fastapi import APIRouter, Request, Response
from sqlalchemy import func, select

from app.config import get_settings
from app.deps import DB, CurrentUser
from app.errors import AppError, bad_request, unauthorized
from app.models import User, utcnow
from app.schemas import ChangePasswordIn, LoginIn, ok, user_out
from app.security import (
    SESSION_COOKIE,
    create_session_token,
    hash_password,
    login_limiter,
    validate_new_password,
    verify_password,
)

router = APIRouter(prefix="/api/auth", tags=["auth"])

# 帳號不存在時也做一次雜湊比對，讓回應時間與「密碼錯誤」一致，避免被探測帳號是否存在。
_DUMMY_HASH = hash_password("starfly-dummy-password")


def _is_https(request: Request) -> bool:
    return request.headers.get("x-forwarded-proto", request.url.scheme) == "https"


def _set_session_cookie(request: Request, response: Response, user: User) -> None:
    response.set_cookie(
        SESSION_COOKIE,
        create_session_token(user.id, user.token_version),
        max_age=get_settings().session_days * 86400,
        httponly=True,
        samesite="lax",
        secure=_is_https(request),
        path="/",
    )


@router.post("/login")
def login(body: LoginIn, request: Request, response: Response, db: DB):
    email = body.email.lower()
    limiter_key = f"{request.client.host if request.client else '-'}|{email}"
    login_limiter.check(limiter_key)
    user = db.scalars(select(User).where(func.lower(User.email) == email)).first()
    valid = verify_password(body.password, user.password_hash if user else _DUMMY_HASH)
    if not user or not valid:
        login_limiter.record_failure(limiter_key)
        raise unauthorized("帳號或密碼錯誤", "invalid_credentials")
    if not user.is_active:
        raise AppError(403, "user_disabled", "這個帳號已被停用，請聯絡管理員")
    login_limiter.reset(limiter_key)
    user.last_login_at = utcnow()
    db.commit()
    _set_session_cookie(request, response, user)
    return ok(user_out(user))


@router.post("/logout")
def logout(response: Response):
    response.delete_cookie(SESSION_COOKIE, path="/")
    return ok()


@router.get("/me")
def me(user: CurrentUser):
    return ok(user_out(user))


@router.post("/password")
def change_password(
    body: ChangePasswordIn, request: Request, response: Response, user: CurrentUser, db: DB
):
    if not verify_password(body.old_password, user.password_hash):
        raise bad_request("目前的密碼不正確", "invalid_credentials")
    validate_new_password(body.new_password)
    user.password_hash = hash_password(body.new_password)
    user.token_version += 1  # 其他裝置上的登入立即失效
    db.commit()
    _set_session_cookie(request, response, user)
    return ok(msg="密碼已更新")
