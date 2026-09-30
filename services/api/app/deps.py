from typing import Annotated

from fastapi import Depends, Request
from sqlalchemy.orm import Session

from app.db import get_db
from app.errors import forbidden, unauthorized
from app.models import User
from app.security import SESSION_COOKIE, decode_session_token

DB = Annotated[Session, Depends(get_db)]


def current_user(request: Request, db: DB) -> User:
    token = request.cookies.get(SESSION_COOKIE)
    payload = decode_session_token(token) if token else None
    if not payload:
        raise unauthorized()
    user = db.get(User, payload.get("sub"))
    if not user or not user.is_active or user.token_version != payload.get("ver"):
        raise unauthorized("登入已失效，請重新登入", "session_expired")
    return user


def require_admin(user: Annotated[User, Depends(current_user)]) -> User:
    if user.role != "admin":
        raise forbidden()
    return user


CurrentUser = Annotated[User, Depends(current_user)]
AdminUser = Annotated[User, Depends(require_admin)]
