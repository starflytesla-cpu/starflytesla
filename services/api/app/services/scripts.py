"""文案：查詢、人工修改、核准、刪除、整段配音試聽。"""

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.errors import bad_request, conflict, not_found
from app.models import BrandProfile, Script, User
from app.schemas import ScriptUpdateIn
from app.services import speech
from app.services.voices import VOICES_BY_ID


def script_out(script: Script) -> dict:
    return {
        "id": script.id,
        "batch_id": script.batch_id,
        "variant": script.variant,
        "template_id": script.template_id,
        "template_name": script.template_name,
        "profile_id": script.profile_id,
        "profile_name": script.profile_name,
        "language": script.language,
        "status": script.status,
        "title": script.title,
        "hook": script.hook,
        "shots": script.shots,
        "post_caption": script.post_caption,
        "hashtags": script.hashtags,
        "error": script.error,
        "total_seconds": round(sum(float(s.get("seconds") or 0) for s in script.shots), 1),
        "created_at": script.created_at.isoformat(),
        "updated_at": script.updated_at.isoformat(),
    }


def list_scripts(
    db: Session,
    user: User,
    *,
    template_id: str | None,
    profile_id: str | None,
    status: str | None,
    limit: int,
    offset: int,
) -> dict:
    where = [Script.tenant_id == user.tenant_id]
    if template_id:
        where.append(Script.template_id == template_id)
    if profile_id:
        where.append(Script.profile_id == profile_id)
    if status:
        where.append(Script.status == status)
    total = db.scalar(select(func.count()).select_from(Script).where(*where))
    rows = db.scalars(
        select(Script).where(*where).order_by(Script.created_at.desc(), Script.variant).limit(limit).offset(offset)
    ).all()
    return {"items": [script_out(s) for s in rows], "total": total}


def get_script(db: Session, user: User, script_id: str) -> Script:
    script = db.get(Script, script_id)
    if script is None or script.tenant_id != user.tenant_id:
        raise not_found("找不到這份文案", "script_not_found")
    return script


def update_script(db: Session, script: Script, body: ScriptUpdateIn) -> None:
    if script.status == "generating":
        raise conflict("文案還在產生中，請稍候", "script_busy")
    if body.shots is not None:
        if len(body.shots) != len(script.shots):
            raise bad_request("鏡頭數量和原本不同", "shot_count_mismatch")
        script.shots = [
            {**old, "voiceover": new.voiceover.strip(), "caption": new.caption.strip()}
            for old, new in zip(script.shots, body.shots)
        ]
    for key in ("title", "hook", "post_caption"):
        value = getattr(body, key)
        if value is not None:
            setattr(script, key, value.strip())
    if body.hashtags is not None:
        script.hashtags = [("#" + t.strip().lstrip("#")).replace(" ", "") for t in body.hashtags if t.strip("# ")][:10]
    if body.status is not None:
        if body.status == "approved" and script.status == "failed":
            raise conflict("產生失敗的文案不能核准，請重新產生", "script_failed")
        if body.status == "approved" and not any(s.get("voiceover") for s in script.shots):
            raise bad_request("文案是空的，不能核准", "script_empty")
        script.status = body.status
    if body.shots is not None or body.title is not None or body.hook is not None:
        # 人工改過後，原本的禁用詞提醒可能已不適用
        script.error = ""
    db.commit()


def delete_script(db: Session, script: Script) -> None:
    if script.status == "generating":
        raise conflict("文案還在產生中，請稍候再刪除", "script_busy")
    db.delete(script)
    db.commit()


def preview_audio(db: Session, user: User, script: Script) -> dict:
    """用帳號檔案綁定的音色，把整份文案的配音稿念一遍（會扣 kie.ai 點數）。"""
    text = " ".join(s.get("voiceover", "").strip() for s in script.shots if s.get("voiceover"))
    if not text:
        raise bad_request("文案還沒有配音稿", "script_empty")
    profile = db.get(BrandProfile, script.profile_id) if script.profile_id else None
    voice_id = profile.voice_id if profile and profile.voice_id in VOICES_BY_ID else speech.default_voice_id()
    speed = profile.voice_speed if profile else 1.0
    return speech.synthesize(db, user, text, voice_id, speed=speed, source="script_preview")
