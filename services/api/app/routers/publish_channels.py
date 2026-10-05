from fastapi import APIRouter
from sqlalchemy import select

from app.deps import DB, AdminUser
from app.errors import bad_request, not_found
from app.models import PublishChannel, User
from app.schemas import PublishChannelCreateIn, PublishChannelUpdateIn, ok, publish_channel_out
from app.security import encrypt_secret
from app.services import publishing

router = APIRouter(prefix="/api/publish-channels", tags=["publish-channels"])


def get_channel(db, admin: User, channel_id: str) -> PublishChannel:
    channel = db.get(PublishChannel, channel_id)
    if not channel or channel.tenant_id != admin.tenant_id:
        raise not_found("找不到這個發佈渠道")
    return channel


def set_key(channel: PublishChannel, key: str) -> None:
    channel.api_key_encrypted = encrypt_secret(key)
    channel.api_key_last4 = key[-4:] if key else ""


@router.get("")
def list_channels(admin: AdminUser, db: DB):
    channels = db.scalars(select(PublishChannel).where(
        PublishChannel.tenant_id == admin.tenant_id
    ).order_by(PublishChannel.created_at)).all()
    return ok([publish_channel_out(channel) for channel in channels])


@router.post("")
def create_channel(body: PublishChannelCreateIn, admin: AdminUser, db: DB):
    channel = PublishChannel(
        tenant_id=admin.tenant_id,
        name=body.name,
        base_url=publishing.validate_base_url(body.base_url),
        enabled=body.enabled,
    )
    set_key(channel, body.api_key)
    db.add(channel)
    db.commit()
    return ok(publish_channel_out(channel), "發佈渠道已新增")


@router.patch("/{channel_id}")
def update_channel(channel_id: str, body: PublishChannelUpdateIn, admin: AdminUser, db: DB):
    channel = get_channel(db, admin, channel_id)
    if body.clear_api_key and body.api_key:
        raise bad_request("不能同時清除及更換 API Key")
    changed = False
    if body.name is not None:
        channel.name = body.name
    if body.base_url is not None:
        url = publishing.validate_base_url(body.base_url)
        changed = url != channel.base_url
        channel.base_url = url
    if body.clear_api_key or body.api_key:
        set_key(channel, "" if body.clear_api_key else body.api_key)
        changed = True
    if body.enabled is not None:
        channel.enabled = body.enabled
    if changed:
        channel.check_status = "untested"
        channel.check_error = channel.plan = ""
        channel.checked_at = None
    db.commit()
    return ok(publish_channel_out(channel), "發佈渠道已更新")


@router.post("/{channel_id}/test")
def test_channel(channel_id: str, admin: AdminUser, db: DB):
    return ok(publishing.test_channel(db, get_channel(db, admin, channel_id), admin), "連線檢查通過")
