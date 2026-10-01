from fastapi import APIRouter

from app.deps import DB, AdminUser
from app.models import BrandProfile
from app.schemas import ProfileIn, ok
from app.services import profiles

router = APIRouter(prefix="/api/profiles", tags=["profiles"])


@router.get("")
def list_profiles(admin: AdminUser, db: DB):
    return ok({"items": profiles.list_profiles(db, admin.tenant_id), "languages": profiles.LANGUAGES})


@router.post("")
def create_profile(body: ProfileIn, admin: AdminUser, db: DB):
    profile = BrandProfile(tenant_id=admin.tenant_id, name="")
    profiles.apply_changes(profile, body.model_dump(exclude_unset=True))
    db.add(profile)
    db.commit()
    return ok(profiles.profile_out(profile, 0), "帳號檔案已建立")


@router.patch("/{profile_id}")
def update_profile(profile_id: str, body: ProfileIn, admin: AdminUser, db: DB):
    profile = profiles.get_profile(db, admin, profile_id)
    profiles.apply_changes(profile, body.model_dump(exclude_unset=True))
    db.commit()
    return ok(profiles.profile_out(profile), "已儲存")


@router.delete("/{profile_id}")
def delete_profile(profile_id: str, admin: AdminUser, db: DB):
    db.delete(profiles.get_profile(db, admin, profile_id))
    db.commit()
    return ok(None, "已刪除（已產生的文案會保留）")
