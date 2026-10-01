"""素材檔案的存取檢查：Caddy 收到 /media/... 時先用 forward_auth 呼叫這裡，200 才回傳檔案。"""

import re
from urllib.parse import unquote, urlsplit

from fastapi import APIRouter, Request

from app.deps import CurrentUser
from app.errors import forbidden
from app.schemas import ok

router = APIRouter(prefix="/api/media", tags=["media"])

# 允許的位置：素材 assets/{asset_id}/…、成片 videos/{video_id}/…、配音試聽 tts/…（不含 tts-cache）
_SAFE_PATH = re.compile(r"^/media/([0-9a-f-]{36})/(?:assets/[0-9a-f-]{36}|videos/[0-9a-f-]{36}|tts)/[A-Za-z0-9._/-]+$")


def allowed(uri: str, tenant_id: str) -> bool:
    path = unquote(urlsplit(uri).path)
    if ".." in path or "//" in path or "\\" in path:
        return False
    match = _SAFE_PATH.match(path)
    return bool(match) and match.group(1) == tenant_id


@router.get("/auth")
def media_auth(request: Request, user: CurrentUser):
    if not allowed(request.headers.get("x-forwarded-uri", ""), user.tenant_id):
        raise forbidden("沒有權限讀取這個檔案")
    return ok()
