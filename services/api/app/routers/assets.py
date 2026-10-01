from fastapi import APIRouter, Query

from app.deps import DB, AdminUser, CurrentUser
from app.schemas import AssetUpdateIn, ClipUpdateIn, ok
from app.services import assets

router = APIRouter(prefix="/api", tags=["assets"])


@router.get("/assets")
def list_assets(
    user: CurrentUser,
    db: DB,
    status: str | None = Query(None, pattern="^(uploaded|processing|ready|failed|duplicate)$"),
    category: str | None = Query(None, max_length=32),
    kind: str | None = Query(None, pattern="^(video|image)$"),
    q: str | None = Query(None, max_length=100),
    mine: bool = False,
    limit: int = Query(24, ge=1, le=100),
    offset: int = Query(0, ge=0),
):
    return ok(
        assets.list_assets(
            db, user, status=status, category=category, kind=kind, q=q, mine=mine, limit=limit, offset=offset
        )
    )


@router.get("/assets/stats")
def asset_stats(user: CurrentUser, db: DB):
    return ok(assets.stats(db, user.tenant_id))


@router.get("/assets/{asset_id}")
def get_asset(asset_id: str, user: CurrentUser, db: DB):
    return ok(assets.asset_detail(db, assets.get_asset(db, user, asset_id)))


@router.patch("/assets/{asset_id}")
def update_asset(asset_id: str, body: AssetUpdateIn, admin: AdminUser, db: DB):
    asset = assets.get_asset(db, admin, asset_id)
    assets.update_asset(db, asset, body)
    return ok(assets.asset_detail(db, asset), "已更新")


@router.delete("/assets/{asset_id}")
def delete_asset(asset_id: str, user: CurrentUser, db: DB):
    assets.delete_asset(db, user, assets.get_asset(db, user, asset_id))
    return ok(None, "已刪除")


@router.post("/assets/{asset_id}/reanalyze")
def reanalyze(asset_id: str, admin: AdminUser, db: DB):
    asset = assets.get_asset(db, admin, asset_id)
    assets.reanalyze(db, asset)
    return ok(assets.asset_detail(db, asset), "已排入重新分析")


@router.patch("/clips/{clip_id}")
def update_clip(clip_id: str, body: ClipUpdateIn, admin: AdminUser, db: DB):
    clip = assets.get_clip(db, admin, clip_id)
    assets.update_clip(db, clip, body)
    return ok(assets.asset_detail(db, clip.asset), "已更新")
