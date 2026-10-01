from fastapi import APIRouter, Query

from app.deps import DB, AdminUser
from app.schemas import GenerateScriptsIn, ScriptUpdateIn, micros_to_usd, ok
from app.services import profiles, script_writer, scripts, templates

router = APIRouter(prefix="/api/scripts", tags=["scripts"])


@router.get("")
def list_scripts(
    admin: AdminUser,
    db: DB,
    template_id: str | None = Query(None, max_length=36),
    profile_id: str | None = Query(None, max_length=36),
    status: str | None = Query(None, pattern="^(generating|draft|approved|failed)$"),
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
):
    return ok(
        scripts.list_scripts(
            db, admin, template_id=template_id, profile_id=profile_id, status=status, limit=limit, offset=offset
        )
    )


@router.post("/generate")
def generate(body: GenerateScriptsIn, admin: AdminUser, db: DB):
    template = templates.get_template(db, admin, body.template_id)
    profile = profiles.get_profile(db, admin, body.profile_id)
    created = script_writer.start_generation(db, admin, template, profile, body.variants)
    return ok([scripts.script_out(s) for s in created], f"已開始產生 {len(created)} 個版本，約 30 秒～1 分鐘")


@router.get("/{script_id}")
def get_script(script_id: str, admin: AdminUser, db: DB):
    return ok(scripts.script_out(scripts.get_script(db, admin, script_id)))


@router.patch("/{script_id}")
def update_script(script_id: str, body: ScriptUpdateIn, admin: AdminUser, db: DB):
    script = scripts.get_script(db, admin, script_id)
    scripts.update_script(db, script, body)
    return ok(scripts.script_out(script), "已核准" if body.status == "approved" else "已儲存")


@router.post("/{script_id}/regenerate")
def regenerate(script_id: str, admin: AdminUser, db: DB):
    script = scripts.get_script(db, admin, script_id)
    script_writer.regenerate(db, script)
    return ok(scripts.script_out(script), "已重新排入產生")


@router.post("/{script_id}/preview-audio")
def preview_audio(script_id: str, admin: AdminUser, db: DB):
    audio = scripts.preview_audio(db, admin, scripts.get_script(db, admin, script_id))
    return ok({"audio_url": audio["audio_url"], "cost_usd": micros_to_usd(audio["cost_micros"])}, "配音完成")


@router.delete("/{script_id}")
def delete_script(script_id: str, admin: AdminUser, db: DB):
    scripts.delete_script(db, scripts.get_script(db, admin, script_id))
    return ok(None, "已刪除")
