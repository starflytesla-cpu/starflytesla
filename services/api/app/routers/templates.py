from fastapi import APIRouter

from app.deps import DB, AdminUser
from app.schemas import TemplateIn, ok
from app.services import templates
from app.services.template_library import STRATEGIES

router = APIRouter(prefix="/api/templates", tags=["templates"])


@router.get("")
def list_templates(admin: AdminUser, db: DB):
    return ok({"items": templates.list_templates(db, admin), "strategies": STRATEGIES})


@router.post("")
def create_template(body: TemplateIn, admin: AdminUser, db: DB):
    return ok(templates.template_out(templates.create_template(db, admin, body), 0), "模板已建立")


@router.post("/{template_id}/copy")
def copy_template(template_id: str, admin: AdminUser, db: DB):
    source = templates.get_template(db, admin, template_id)
    return ok(templates.template_out(templates.copy_template(db, admin, source), 0), "已複製為自訂模板")


@router.patch("/{template_id}")
def update_template(template_id: str, body: TemplateIn, admin: AdminUser, db: DB):
    template = templates.get_template(db, admin, template_id)
    templates.update_template(db, template, body)
    return ok(templates.template_out(template), "已儲存")


@router.delete("/{template_id}")
def delete_template(template_id: str, admin: AdminUser, db: DB):
    templates.delete_template(db, templates.get_template(db, admin, template_id))
    return ok(None, "模板已刪除（已產生的文案會保留）")
