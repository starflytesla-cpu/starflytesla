import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.db import get_sessionmaker
from app.errors import AppError
from app.routers import (
    assets,
    auth,
    channels,
    media,
    music,
    profiles,
    publish_channels,
    publishing,
    scripts,
    system,
    tasks,
    templates,
    uploads,
    usage,
    users,
    videos,
    voices,
)
from app.services.bootstrap import ensure_initial_admin
from app.services.template_library import sync_builtin_templates

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
log = logging.getLogger("starfly")


@asynccontextmanager
async def lifespan(_app: FastAPI):
    with get_sessionmaker()() as db:
        ensure_initial_admin(db)
        sync_builtin_templates(db)
    yield


app = FastAPI(title="Starfly API", lifespan=lifespan, docs_url="/api/docs", openapi_url="/api/openapi.json")


def _error(status: int, reason: str, message: str) -> JSONResponse:
    return JSONResponse(
        status_code=status, content={"code": status, "data": None, "msg": message, "reason": reason}
    )


@app.exception_handler(AppError)
async def app_error_handler(_request: Request, exc: AppError):
    return _error(exc.status, exc.reason, exc.message)


@app.exception_handler(RequestValidationError)
async def validation_error_handler(_request: Request, exc: RequestValidationError):
    first = exc.errors()[0] if exc.errors() else {}
    field = ".".join(str(p) for p in first.get("loc", [])[1:])
    message = f"欄位 {field} 格式不正確" if field else "請求格式不正確"
    return _error(422, "validation_error", message)


@app.exception_handler(StarletteHTTPException)
async def http_error_handler(_request: Request, exc: StarletteHTTPException):
    messages = {404: "找不到這個 API", 405: "不支援這個請求方法"}
    return _error(exc.status_code, "http_error", messages.get(exc.status_code, str(exc.detail)))


@app.exception_handler(Exception)
async def unhandled_error_handler(request: Request, exc: Exception):
    # 未分類錯誤只記錄在伺服器日誌，回應中不帶任何內部細節。
    log.exception("未處理的錯誤：%s %s", request.method, request.url.path)
    return _error(500, "internal_error", "系統處理失敗，請稍後再試")


for module in (system, auth, users, channels, publish_channels, publishing, usage, uploads, assets, media, profiles, templates, scripts, voices, videos, tasks, music):
    app.include_router(module.router)
