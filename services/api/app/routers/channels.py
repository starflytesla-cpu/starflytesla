from fastapi import APIRouter
from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, selectinload

from app.deps import DB, AdminUser
from app.errors import bad_request, conflict, not_found
from app.models import ChannelModel, ModelChannel, User
from app.presets import CAPABILITIES, PRESETS
from app.schemas import (
    ChannelCreateIn,
    ChannelModelIn,
    ChannelModelUpdateIn,
    ChannelTestIn,
    ChannelUpdateIn,
    channel_model_out,
    channel_out,
    micros_to_usd,
    ok,
)
from app.security import encrypt_secret, validate_upstream_url
from app.services import ai_provider

router = APIRouter(prefix="/api", tags=["channels"])


def _get_channel(db: Session, admin: User, channel_id: str) -> ModelChannel:
    channel = db.get(ModelChannel, channel_id)
    if not channel or channel.tenant_id != admin.tenant_id:
        raise not_found("找不到這個渠道")
    return channel


def _get_model(db: Session, admin: User, model_id: str) -> ChannelModel:
    model = db.get(ChannelModel, model_id)
    if not model or model.channel.tenant_id != admin.tenant_id:
        raise not_found("找不到這個模型")
    return model


def _set_api_key(channel: ModelChannel, api_key: str) -> None:
    api_key = api_key.strip()
    channel.api_key_encrypted = encrypt_secret(api_key)
    channel.api_key_last4 = api_key[-4:] if api_key else ""


def _make_default(db: Session, model: ChannelModel) -> None:
    """同一租戶、同一種 capability 只能有一個預設模型。"""
    tenant_channel_ids = select(ModelChannel.id).where(
        ModelChannel.tenant_id == model.channel.tenant_id
    )
    db.execute(
        update(ChannelModel)
        .where(
            ChannelModel.capability == model.capability,
            ChannelModel.channel_id.in_(tenant_channel_ids),
            ChannelModel.id != model.id,
        )
        .values(is_default=False)
    )
    model.is_default = True


@router.get("/channel-presets")
def list_presets(admin: AdminUser):
    presets = [
        {
            "provider": key,
            "name": p["name"],
            "base_url": p["base_url"],
            "api_key_help": p["api_key_help"],
            "models": [m["model_key"] for m in p["models"]],
        }
        for key, p in PRESETS.items()
    ]
    return ok({"presets": presets, "capabilities": CAPABILITIES})


@router.get("/channels")
def list_channels(admin: AdminUser, db: DB):
    channels = db.scalars(
        select(ModelChannel)
        .where(ModelChannel.tenant_id == admin.tenant_id)
        .options(selectinload(ModelChannel.models))
        .order_by(ModelChannel.created_at)
    ).all()
    return ok([channel_out(c) for c in channels])


@router.post("/channels")
def create_channel(body: ChannelCreateIn, admin: AdminUser, db: DB):
    preset = PRESETS[body.provider]
    base_url = (body.base_url or preset["base_url"]).strip()
    if not base_url:
        raise bad_request("請填寫 Base URL", "missing_base_url")
    channel = ModelChannel(
        tenant_id=admin.tenant_id,
        name=(body.name or preset["name"]).strip(),
        provider=body.provider,
        base_url=validate_upstream_url(base_url),
    )
    _set_api_key(channel, body.api_key)
    db.add(channel)
    db.flush()
    for spec in preset["models"]:
        model = ChannelModel(channel_id=channel.id, **{**spec, "is_default": False})
        channel.models.append(model)
        db.flush()
        # 預設模型只在該 capability 還沒有預設時才接手，避免覆蓋管理員的選擇。
        if spec.get("is_default") and not _has_default(db, admin.tenant_id, model):
            model.is_default = True
    db.commit()
    return ok(channel_out(channel), "渠道已新增")


def _has_default(db: Session, tenant_id: str, model: ChannelModel) -> bool:
    return (
        db.scalars(
            select(ChannelModel.id)
            .join(ModelChannel)
            .where(
                ModelChannel.tenant_id == tenant_id,
                ChannelModel.capability == model.capability,
                ChannelModel.is_default.is_(True),
                ChannelModel.id != model.id,
            )
        ).first()
        is not None
    )


@router.patch("/channels/{channel_id}")
def update_channel(channel_id: str, body: ChannelUpdateIn, admin: AdminUser, db: DB):
    channel = _get_channel(db, admin, channel_id)
    if body.name is not None:
        channel.name = body.name.strip()
    if body.base_url is not None:
        channel.base_url = validate_upstream_url(body.base_url)
    if body.api_key:
        _set_api_key(channel, body.api_key)
    if body.enabled is not None:
        channel.enabled = body.enabled
    db.commit()
    return ok(channel_out(channel), "已更新")


@router.delete("/channels/{channel_id}")
def delete_channel(channel_id: str, admin: AdminUser, db: DB):
    channel = _get_channel(db, admin, channel_id)
    db.delete(channel)
    db.commit()
    return ok(msg="渠道已刪除")


@router.post("/channels/{channel_id}/models")
def add_model(channel_id: str, body: ChannelModelIn, admin: AdminUser, db: DB):
    channel = _get_channel(db, admin, channel_id)
    data = body.model_dump()
    make_default = data.pop("is_default")
    model = ChannelModel(channel_id=channel.id, **data)
    model.display_name = model.display_name.strip() or model.model_key
    channel.models.append(model)
    try:
        db.flush()
    except IntegrityError:
        db.rollback()
        raise conflict("這個渠道已經有同名模型", "model_exists") from None
    if make_default or not _has_default(db, admin.tenant_id, model):
        _make_default(db, model)
    db.commit()
    return ok(channel_model_out(model), "模型已新增")


@router.patch("/channel-models/{model_id}")
def update_model(model_id: str, body: ChannelModelUpdateIn, admin: AdminUser, db: DB):
    model = _get_model(db, admin, model_id)
    changes = body.model_dump(exclude_unset=True)
    make_default = changes.pop("is_default", None)
    for field, value in changes.items():
        setattr(model, field, value)
    if make_default:
        _make_default(db, model)
    elif make_default is False:
        model.is_default = False
    db.commit()
    return ok(channel_model_out(model), "已更新")


@router.delete("/channel-models/{model_id}")
def delete_model(model_id: str, admin: AdminUser, db: DB):
    model = _get_model(db, admin, model_id)
    db.delete(model)
    db.commit()
    return ok(msg="模型已刪除")


@router.post("/channel-models/{model_id}/test")
def test_model(model_id: str, body: ChannelTestIn, admin: AdminUser, db: DB):
    model = _get_model(db, admin, model_id)
    result = ai_provider.chat(
        db,
        model,
        [{"role": "user", "content": body.prompt}],
        source="channel_test",
        user=admin,
        max_tokens=200,
    )
    return ok(
        {
            "reply": result.content,
            "input_tokens": result.input_tokens,
            "output_tokens": result.output_tokens,
            "duration_ms": result.duration_ms,
            "cost_usd": micros_to_usd(result.cost_micros),
        },
        "測試成功",
    )
