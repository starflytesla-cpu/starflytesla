from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.errors import conflict, not_found
from app.models import BrandProfile, PublishChannel, SocialAccount, User, utcnow
from app.services.upload_post import UploadPost


def owned(db: Session, model, tenant_id: str, object_id: str, *, lock=False):
    stmt = select(model).where(model.id == object_id, model.tenant_id == tenant_id).execution_options(populate_existing=True)
    if lock:
        stmt = stmt.with_for_update().execution_options(populate_existing=True)
    item = db.scalars(stmt).first()
    if item is None:
        raise not_found("找不到資料", "not_found")
    return item


def out(account: SocialAccount) -> dict:
    return {"id": account.id, "channel_id": account.channel_id, "profile_id": account.profile_id,
            "remote_profile": account.remote_profile, "platform": account.platform,
            "external_account_id": account.external_account_id, "display_name": account.display_name,
            "handle": account.handle, "enabled": account.enabled, "auth_status": account.auth_status,
            "capabilities": account.capabilities, "auto_suggest_enabled": account.auto_suggest_enabled,
            "checked_at": account.checked_at.isoformat() if account.checked_at else None}


def bind(db: Session, user: User, channel_id: str, profile_id: str, remote_profile: str, platforms: list[str]) -> list[SocialAccount]:
    channel = owned(db, PublishChannel, user.tenant_id, channel_id, lock=True)
    owned(db, BrandProfile, user.tenant_id, profile_id)
    remote = next((p for p in UploadPost(channel).profiles() if p["username"] == remote_profile), None)
    if remote is None or any(p not in remote["accounts"] for p in platforms):
        raise conflict("選取的平台尚未綁定或缺少目的帳號識別碼，請先在 Upload-Post 完成綁定", "account_not_connected")
    result = []
    for platform in set(platforms):
        details = remote["accounts"][platform]
        account = db.scalars(select(SocialAccount).where(SocialAccount.channel_id == channel_id,
            SocialAccount.tenant_id == user.tenant_id, SocialAccount.remote_profile == remote_profile,
            SocialAccount.platform == platform).with_for_update()).first()
        if account and (account.profile_id != profile_id or account.external_account_id != details["external_account_id"]):
            raise conflict("既有綁定的帳號檔案或目的帳號已不同，請先核對，不能覆蓋原綁定", "destination_changed")
        if account is None:
            account = SocialAccount(tenant_id=user.tenant_id, channel_id=channel_id, profile_id=profile_id,
                remote_profile=remote_profile, platform=platform, **details)
            db.add(account)
        else:
            for key, value in details.items():
                setattr(account, key, value)
        account.checked_at = utcnow()
        result.append(account)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise conflict("此帳號已由另一個請求綁定，請重新整理", "account_exists") from None
    return result


def check(db: Session, account: SocialAccount, provider: UploadPost | None = None) -> None:
    channel = owned(db, PublishChannel, account.tenant_id, account.channel_id)
    provider = provider or UploadPost(channel)
    remote = next((p for p in provider.profiles() if p["username"] == account.remote_profile), None)
    details = (remote or {}).get("accounts", {}).get(account.platform)
    if details is None:
        account.auth_status = "disconnected"
    elif details["external_account_id"] != account.external_account_id:
        account.auth_status = "destination_changed"
    else:
        account.auth_status = details["auth_status"]
        account.display_name, account.handle = details["display_name"], details["handle"]
        account.capabilities = details["capabilities"]
    account.checked_at = utcnow()
    # 呼叫端決定交易邊界；發佈前檢查會連同 submitting 狀態持久化。


def destination(account: SocialAccount, channel: PublishChannel) -> dict:
    return {"channel_id": channel.id, "base_url": channel.base_url, "remote_profile": account.remote_profile,
            "platform": account.platform, "external_account_id": account.external_account_id, "profile_id": account.profile_id}
