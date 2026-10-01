"""模板：內建模板唯讀（可複製），自訂模板可修改與刪除。"""

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.errors import bad_request, forbidden, not_found
from app.models import Script, Template, User
from app.schemas import TemplateIn
from app.services.asset_analyzer import SCENES


def template_out(template: Template, script_count: int | None = None) -> dict:
    return {
        "id": template.id,
        "builtin": template.tenant_id is None,
        "name": template.name,
        "strategy": template.strategy,
        "description": template.description,
        "shots": template.shots,
        "total_seconds": round(sum(float(s.get("seconds") or 0) for s in template.shots), 1),
        "is_active": template.is_active,
        "script_count": script_count,
        "updated_at": template.updated_at.isoformat(),
    }


def visible(tenant_id: str):
    return or_(Template.tenant_id == tenant_id, Template.tenant_id.is_(None))


def list_templates(db: Session, user: User) -> list[dict]:
    counts = dict(
        db.execute(
            select(Script.template_id, func.count())
            .where(Script.tenant_id == user.tenant_id, Script.template_id.is_not(None))
            .group_by(Script.template_id)
        ).all()
    )
    rows = db.scalars(
        select(Template)
        .where(visible(user.tenant_id), or_(Template.tenant_id.is_not(None), Template.is_active.is_(True)))
        .order_by(Template.tenant_id.is_(None), Template.created_at)
    ).all()
    return [template_out(t, counts.get(t.id, 0)) for t in rows]


def get_template(db: Session, user: User, template_id: str) -> Template:
    template = db.get(Template, template_id)
    if template is None or template.tenant_id not in (None, user.tenant_id):
        raise not_found("找不到這個模板", "template_not_found")
    return template


def _shots(body: TemplateIn) -> list[dict]:
    shots = []
    for shot in body.shots or []:
        if shot.scene and shot.scene not in SCENES:
            raise bad_request("鏡頭的畫面類型不正確", "invalid_scene")
        shots.append({"brief": shot.brief.strip(), "scene": shot.scene, "seconds": shot.seconds})
    return shots


def copy_template(db: Session, user: User, source: Template) -> Template:
    template = Template(
        tenant_id=user.tenant_id,
        name=f"{source.name}（自訂）"[:80],
        strategy=source.strategy,
        description=source.description,
        shots=[dict(s) for s in source.shots],
    )
    db.add(template)
    db.commit()
    return template


def create_template(db: Session, user: User, body: TemplateIn) -> Template:
    if not body.name or not body.strategy or not body.shots:
        raise bad_request("請填寫名稱、類型，並至少加入一個鏡頭", "template_incomplete")
    template = Template(
        tenant_id=user.tenant_id,
        name=body.name.strip(),
        strategy=body.strategy,
        description=(body.description or "").strip(),
        shots=_shots(body),
    )
    db.add(template)
    db.commit()
    return template


def update_template(db: Session, template: Template, body: TemplateIn) -> None:
    if template.tenant_id is None:
        raise forbidden("內建模板不能修改，請先「複製為自訂模板」", "builtin_template")
    if body.name is not None:
        template.name = body.name.strip()
    if body.strategy is not None:
        template.strategy = body.strategy
    if body.description is not None:
        template.description = body.description.strip()
    if body.shots is not None:
        template.shots = _shots(body)
    if body.is_active is not None:
        template.is_active = body.is_active
    db.commit()


def delete_template(db: Session, template: Template) -> None:
    if template.tenant_id is None:
        raise forbidden("內建模板不能刪除", "builtin_template")
    db.delete(template)
    db.commit()
