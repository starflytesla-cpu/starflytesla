"""tus 斷點續傳端點。前端用 tus-js-client 上傳，成功回應沒有 JSON 內容（依 tus 協定）。"""

from fastapi import APIRouter, Request, Response

from app.config import get_settings
from app.deps import DB, CurrentUser
from app.errors import AppError, bad_request
from app.services import uploads

router = APIRouter(prefix="/api/uploads", tags=["uploads"])

TUS_VERSION = "1.0.0"


def _tus_headers(**extra: str) -> dict[str, str]:
    return {"Tus-Resumable": TUS_VERSION, "Cache-Control": "no-store", **extra}


def _check_version(request: Request) -> None:
    version = request.headers.get("tus-resumable")
    if version and version != TUS_VERSION:
        raise AppError(412, "tus_version", "上傳協定版本不支援，請重新整理頁面")


def _int_header(request: Request, name: str) -> int:
    try:
        value = int(request.headers.get(name, ""))
    except ValueError:
        raise bad_request(f"缺少或無效的 {name}", "invalid_header") from None
    if value < 0:
        raise bad_request(f"無效的 {name}", "invalid_header")
    return value


@router.options("")
@router.options("/{upload_id}")
def options():
    return Response(
        status_code=204,
        headers=_tus_headers(
            **{
                "Tus-Version": TUS_VERSION,
                "Tus-Extension": "creation,termination",
                "Tus-Max-Size": str(get_settings().max_upload_bytes),
            }
        ),
    )


@router.post("")
def create(request: Request, user: CurrentUser, db: DB):
    _check_version(request)
    length = _int_header(request, "upload-length")
    metadata = uploads.parse_metadata(request.headers.get("upload-metadata", ""))
    upload = uploads.create_upload(db, user, length, metadata)
    return Response(
        status_code=201,
        headers=_tus_headers(Location=f"/api/uploads/{upload.id}", **{"Upload-Offset": "0"}),
    )


@router.head("/{upload_id}")
def status(upload_id: str, request: Request, user: CurrentUser, db: DB):
    _check_version(request)
    upload = uploads.get_upload(db, user, upload_id)
    offset = upload.size_bytes if upload.completed else uploads.current_offset(upload)
    return Response(
        status_code=200,
        headers=_tus_headers(**{"Upload-Offset": str(offset), "Upload-Length": str(upload.size_bytes)}),
    )


@router.patch("/{upload_id}")
async def append(upload_id: str, request: Request, user: CurrentUser, db: DB):
    _check_version(request)
    if request.headers.get("content-type") != "application/offset+octet-stream":
        raise AppError(415, "invalid_content_type", "上傳格式不正確")
    offset = _int_header(request, "upload-offset")
    upload = uploads.get_upload(db, user, upload_id)
    # 傳輸可能要幾十秒，先結束交易把資料庫連線還回連線池（commit 不會讓已載入的資料失效）
    db.commit()
    new_offset = await uploads.append(upload, offset, request.stream())
    asset = uploads.finalize(db, upload, new_offset)
    headers = _tus_headers(**{"Upload-Offset": str(new_offset)})
    if asset is not None:
        headers["Starfly-Asset-Id"] = asset.id
    return Response(status_code=204, headers=headers)


@router.delete("/{upload_id}")
def terminate(upload_id: str, request: Request, user: CurrentUser, db: DB):
    _check_version(request)
    uploads.cancel(db, uploads.get_upload(db, user, upload_id))
    return Response(status_code=204, headers=_tus_headers())
