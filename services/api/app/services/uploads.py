"""tus 1.0 斷點續傳上傳（https://tus.io/protocols/resumable-upload）。

手機網路不穩時，上傳中斷後可以從已上傳的位置繼續，不必整支影片重傳。
暫存檔的實際大小就是目前進度（不信任資料庫裡的數字），寫入時用檔案鎖避免同一個上傳被同時寫入。
"""

import base64
import binascii
import fcntl
import os
import re
from collections.abc import AsyncIterator
from pathlib import Path

import anyio
from sqlalchemy.orm import Session
from starlette.requests import ClientDisconnect

from app.config import get_settings
from app.errors import AppError, bad_request, conflict, not_found
from app.models import Asset, Upload, User, new_id
from app.services import asset_analyzer, media, tasks


def parse_metadata(header: str) -> dict[str, str]:
    result: dict[str, str] = {}
    for pair in filter(None, (p.strip() for p in header.split(","))):
        key, _, value = pair.partition(" ")
        try:
            result[key] = base64.b64decode(value, validate=True).decode("utf-8") if value else ""
        except (binascii.Error, UnicodeDecodeError):
            raise bad_request("上傳資訊格式不正確", "invalid_metadata") from None
    return result


def clean_filename(name: str) -> str:
    name = os.path.basename(name.replace("\\", "/"))
    name = re.sub(r"[\x00-\x1f\x7f]", "", name).strip()
    if len(name) > 200:
        stem, ext = os.path.splitext(name)
        name = stem[: 200 - len(ext)] + ext
    return name or "未命名"


def part_path(upload_id: str) -> Path:
    return media.uploads_dir() / f"{upload_id}.part"


def current_offset(upload: Upload) -> int:
    path = part_path(upload.id)
    return path.stat().st_size if path.exists() else 0


def create_upload(db: Session, user: User, length: int, metadata: dict[str, str]) -> Upload:
    settings = get_settings()
    filename = clean_filename(metadata.get("filename") or metadata.get("name") or "")
    ext = os.path.splitext(filename)[1].lower()
    if media.kind_for_extension(ext) is None:
        raise AppError(415, "unsupported_type", f"不支援這種檔案格式（{ext or '無副檔名'}），請上傳影片或照片")
    if length <= 0:
        raise bad_request("檔案是空的", "empty_file")
    if length > settings.max_upload_bytes:
        limit_gb = settings.max_upload_bytes / 1024**3
        raise AppError(413, "too_large", f"檔案太大，單一檔案上限 {limit_gb:g} GB")
    if media.free_bytes() - length < settings.min_free_bytes:
        raise AppError(507, "storage_full", "伺服器儲存空間不足，請聯絡管理員")

    upload = Upload(
        id=new_id(),
        tenant_id=user.tenant_id,
        user_id=user.id,
        filename=filename,
        content_type=(metadata.get("filetype") or "")[:100],
        size_bytes=length,
    )
    media.uploads_dir().mkdir(parents=True, exist_ok=True)
    part_path(upload.id).touch()
    db.add(upload)
    db.commit()
    return upload


def get_upload(db: Session, user: User, upload_id: str) -> Upload:
    upload = db.get(Upload, upload_id)
    if upload is None or upload.user_id != user.id:
        raise not_found("找不到這個上傳，請重新選擇檔案", "upload_not_found")
    return upload


async def append(upload: Upload, offset: int, chunks: AsyncIterator[bytes]) -> int:
    """把請求內容接在暫存檔後面，回傳新的進度。連線中斷時保留已收到的部分。"""
    if upload.completed:
        raise conflict("這個檔案已經上傳完成", "upload_completed")
    path = part_path(upload.id)
    if not path.exists():
        raise not_found("上傳暫存檔已過期，請重新上傳", "upload_expired")
    with path.open("ab") as f:
        try:
            fcntl.flock(f, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            raise AppError(423, "upload_locked", "這個檔案正在另一個連線上傳中") from None
        size = f.seek(0, os.SEEK_END)
        if size != offset:
            raise conflict(f"上傳進度不一致（伺服器 {size}，請求 {offset}）", "offset_mismatch")
        written = size
        try:
            async for chunk in chunks:
                if not chunk:
                    continue
                if written + len(chunk) > upload.size_bytes:
                    raise bad_request("上傳的內容超過宣告的檔案大小", "size_exceeded")
                await anyio.to_thread.run_sync(f.write, chunk)
                written += len(chunk)
        except ClientDisconnect:
            pass  # 已寫入的部分保留，客戶端之後用 HEAD 查詢進度再續傳
        finally:
            f.flush()
    return written


def finalize(db: Session, upload: Upload, offset: int) -> Asset | None:
    """記錄進度；檔案傳完時搬到素材目錄、建立 Asset 並排入分析任務。"""
    upload.offset_bytes = offset
    if offset < upload.size_bytes:
        db.commit()
        return None
    ext = os.path.splitext(upload.filename)[1].lower()
    asset_id = new_id()
    directory = media.asset_dir(upload.tenant_id, asset_id)
    directory.mkdir(parents=True, exist_ok=True)
    original = directory / f"original{ext}"
    part_path(upload.id).replace(original)
    asset = Asset(
        id=asset_id,
        tenant_id=upload.tenant_id,
        uploaded_by=upload.user_id,
        original_filename=upload.filename,
        storage_key=str(original.relative_to(media.media_root())),
        kind=media.kind_for_extension(ext) or "video",
        size_bytes=upload.size_bytes,
        stage="等待分析",
    )
    db.add(asset)
    upload.completed = True
    upload.asset_id = asset_id
    tasks.enqueue(db, asset_analyzer.TASK_TYPE, {"asset_id": asset_id}, tenant_id=upload.tenant_id)
    db.commit()
    return asset


def cancel(db: Session, upload: Upload) -> None:
    if upload.completed:
        raise conflict("檔案已經上傳完成，請到素材庫刪除", "upload_completed")
    part_path(upload.id).unlink(missing_ok=True)
    db.delete(upload)
    db.commit()
