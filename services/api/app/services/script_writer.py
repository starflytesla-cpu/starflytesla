"""AI 寫文案（worker 執行）：依帳號檔案與模板的鏡頭，一次產生多個彼此不同的版本。

每個版本包含：標題、開場鉤子、每個鏡頭的配音稿與畫面字幕、發佈用的貼文說明與 hashtag。
呼叫預設的「文字」模型（DeepSeek），經 ai_provider 記錄成本。
"""

import json
import logging
import re

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.errors import AppError, bad_request, conflict
from app.models import BrandProfile, Script, Task, Template, User, new_id
from app.services import ai_provider, tasks
from app.services.profiles import LANGUAGES
from app.services.tasks import will_retry
from app.services.template_library import STRATEGIES

log = logging.getLogger("starfly.script_writer")

TASK_TYPE = "script.generate"
MAX_VARIANTS = 5
# 不使用空格分詞的語言，用「字數」而不是「單字數」控制長度
CHAR_LANGUAGES = {"ja", "ko", "zh-TW", "th"}

SYSTEM_PROMPT = """You are a senior short-form video copywriter for factories and physical stores \
selling to overseas buyers on TikTok, Instagram Reels, YouTube Shorts and Facebook Reels.
Write natural, spoken, native-sounding copy in the requested language. Respond with ONE JSON object only, no markdown.

Rules:
- Follow the shot list exactly: one voiceover line and one on-screen caption per shot, same order and count.
- Keep each voiceover within its length limit so it fits the shot duration when spoken at a natural pace.
- The first shot must be a scroll-stopping hook (curiosity, bold claim backed by the profile facts, or a question).
- On-screen captions are short punchy phrases (max 6 words / 12 characters for CJK), not a copy of the voiceover.
- Only use facts from the brand profile. Never invent certifications, numbers, prices, awards or client names.
- Never use any banned word.
- End the last shot with the brand's call to action.
- Each variant must use a clearly different angle, hook and wording from the other variants and from the "avoid" list.
- post_caption: 1-3 sentences for the social post, in the target language; hashtags: 3-8 relevant tags starting with #.
"""


def _limit(seconds: float, language: str) -> str:
    if language in CHAR_LANGUAGES:
        return f"max {max(6, round(seconds * 4.5))} characters"
    return f"max {max(4, round(seconds * 2.5))} words"


def build_messages(
    profile: BrandProfile, template_meta: dict, shots: list[dict], count: int, avoid: list[str]
) -> list[dict]:
    language = profile.target_language
    brief = {
        "brand_profile": {
            "name": profile.name,
            "industry": profile.industry,
            "audience": profile.audience,
            "selling_points": profile.selling_points,
            "product_details": profile.product_details,
            "tone": profile.tone,
            "call_to_action": profile.call_to_action,
            "preferred_hashtags": profile.hashtags,
            "banned_words": profile.banned_words,
        },
        "template": {
            "name": template_meta.get("name", ""),
            "strategy": STRATEGIES.get(template_meta.get("strategy", ""), ""),
            "description": template_meta.get("description", ""),
        },
        "shots": [
            {
                "index": i + 1,
                "what_to_show_and_say": shot.get("brief", ""),
                "seconds": shot.get("seconds", 4),
                "voiceover_limit": _limit(float(shot.get("seconds") or 4), language),
            }
            for i, shot in enumerate(shots)
        ],
        "target_language": f"{language} ({LANGUAGES.get(language, language)})",
        "variants_needed": count,
        "avoid_these_existing_hooks": avoid,
    }
    output = {
        "variants": [
            {
                "title": "internal title in the target language",
                "hook": "the opening line",
                "shots": [{"voiceover": "...", "caption": "..."}],
                "post_caption": "...",
                "hashtags": ["#..."],
            }
        ]
    }
    user = (
        "Brief (the shot notes may be written in Chinese; write the output in the target language):\n"
        + json.dumps(brief, ensure_ascii=False, indent=1)
        + "\n\nReturn JSON exactly in this shape with "
        + str(count)
        + " variants:\n"
        + json.dumps(output, ensure_ascii=False)
    )
    return [{"role": "system", "content": SYSTEM_PROMPT}, {"role": "user", "content": user}]


def _text(value, limit: int) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip()[:limit]


def parse_variants(content: str, count: int, shot_count: int) -> list[dict]:
    """解析模型回覆；格式不對（或版本 / 鏡頭數量不足）時丟 ValueError，讓任務重試。"""
    match = re.search(r"\{.*\}", content, re.S)
    if not match:
        raise ValueError("回覆中沒有 JSON")
    data = json.loads(match.group(0))
    variants = data.get("variants") if isinstance(data, dict) else None
    if not isinstance(variants, list) or len(variants) < count:
        raise ValueError("版本數量不足")
    result = []
    for variant in variants[:count]:
        shots = variant.get("shots") if isinstance(variant, dict) else None
        if not isinstance(shots, list) or len(shots) < shot_count:
            raise ValueError("鏡頭數量和模板不符")
        tags = variant.get("hashtags") or []
        if isinstance(tags, str):
            tags = tags.split()
        hashtags: list[str] = []
        for tag in tags:
            tag = "#" + re.sub(r"\s+", "", str(tag)).lstrip("#")
            if len(tag) > 1 and tag not in hashtags:
                hashtags.append(tag[:50])
        result.append(
            {
                "title": _text(variant.get("title"), 200),
                "hook": _text(variant.get("hook"), 300),
                "shots": [
                    {"voiceover": _text(s.get("voiceover"), 600), "caption": _text(s.get("caption"), 120)}
                    if isinstance(s, dict)
                    else {"voiceover": _text(s, 600), "caption": ""}
                    for s in shots[:shot_count]
                ],
                "post_caption": _text(variant.get("post_caption"), 2000),
                "hashtags": hashtags[:10],
            }
        )
    return result


def banned_hits(script: Script, banned: list[str]) -> list[str]:
    text = " ".join([script.title, script.hook, script.post_caption] + [s.get("voiceover", "") + " " + s.get("caption", "") for s in script.shots]).lower()
    return [w for w in banned if w and w.lower() in text]


# ---------------------------------------------------------------- 排入任務
def start_generation(db: Session, user: User, template: Template, profile: BrandProfile, variants: int) -> list[Script]:
    if not 1 <= variants <= MAX_VARIANTS:
        raise bad_request(f"一次可以產生 1～{MAX_VARIANTS} 個版本", "invalid_variants")
    if not template.shots:
        raise bad_request("這個模板沒有任何鏡頭", "empty_template")
    ai_provider.default_model(db, user.tenant_id, "text")  # 沒有文字模型時立即提示，不排入任務
    batch_id = new_id()
    scripts = [
        Script(
            id=new_id(),
            tenant_id=user.tenant_id,
            template_id=template.id,
            profile_id=profile.id,
            template_name=template.name,
            profile_name=profile.name,
            batch_id=batch_id,
            variant=i + 1,
            language=profile.target_language,
            status="generating",
            shots=[{**shot, "voiceover": "", "caption": ""} for shot in template.shots],
            created_by=user.id,
        )
        for i in range(variants)
    ]
    db.add_all(scripts)
    tasks.enqueue(
        db,
        TASK_TYPE,
        {"script_ids": [s.id for s in scripts], "template": _template_meta(template)},
        tenant_id=user.tenant_id,
    )
    db.commit()
    return scripts


def regenerate(db: Session, script: Script) -> None:
    if script.status == "generating":
        raise conflict("這份文案正在產生中", "script_busy")
    if script.profile_id is None:
        raise conflict("原本的帳號檔案已刪除，無法重新產生", "profile_deleted")
    template = db.get(Template, script.template_id) if script.template_id else None
    meta = _template_meta(template) if template else {"name": script.template_name}
    script.status = "generating"
    script.error = ""
    tasks.enqueue(db, TASK_TYPE, {"script_ids": [script.id], "template": meta}, tenant_id=script.tenant_id)
    db.commit()


def _template_meta(template: Template) -> dict:
    return {"name": template.name, "strategy": template.strategy, "description": template.description}


# ---------------------------------------------------------------- worker
def _avoid_hooks(db: Session, scripts: list[Script]) -> list[str]:
    first = scripts[0]
    ids = [s.id for s in scripts]
    hooks = db.scalars(
        select(Script.hook)
        .where(
            Script.tenant_id == first.tenant_id,
            Script.profile_id == first.profile_id,
            Script.template_name == first.template_name,
            Script.id.not_in(ids),
            Script.hook != "",
        )
        .order_by(Script.created_at.desc())
        .limit(10)
    ).all()
    return list(hooks)


def _write(db: Session, task: Task, scripts: list[Script]) -> dict:
    first = scripts[0]
    profile = db.get(BrandProfile, first.profile_id) if first.profile_id else None
    if profile is None:
        raise AppError(400, "profile_deleted", "帳號檔案已刪除")
    model = ai_provider.default_model(db, first.tenant_id, "text")
    shots = first.shots
    messages = build_messages(profile, task.payload.get("template") or {}, shots, len(scripts), _avoid_hooks(db, scripts))
    creator = db.get(User, first.created_by) if first.created_by else None
    result = ai_provider.chat(
        db, model, messages, source="script_generate", user=creator, max_tokens=min(8000, 700 * len(scripts) + 600)
    )
    variants = parse_variants(result.content, len(scripts), len(shots))
    for script, variant in zip(scripts, variants):
        script.title = variant["title"]
        script.hook = variant["hook"]
        script.shots = [{**shot, **written} for shot, written in zip(script.shots, variant["shots"])]
        script.post_caption = variant["post_caption"]
        script.hashtags = variant["hashtags"]
        script.language = profile.target_language
        hits = banned_hits(script, profile.banned_words)
        script.error = f"包含禁用詞：{'、'.join(hits)}，請修改" if hits else ""
        script.status = "draft"
    db.commit()
    return {"scripts": len(scripts)}


class ScriptError(Exception):
    def __init__(self, message: str, *, retryable: bool):
        super().__init__(message)
        self.retryable = retryable


def generate_task(db: Session, task: Task) -> dict:
    ids = task.payload.get("script_ids") or []
    scripts = db.scalars(select(Script).where(Script.id.in_(ids)).order_by(Script.variant)).all()
    if not scripts:
        return {"skipped": "scripts_deleted"}
    for script in scripts:
        script.status, script.error = "generating", ""
    db.commit()
    try:
        return _write(db, task, scripts)
    except Exception as exc:
        db.rollback()
        if isinstance(exc, AppError):
            # 上游暫時錯誤可重試；設定問題（沒有模型、沒有 Key、帳號檔案已刪）重試也沒用
            retryable = exc.status >= 500
            message = exc.message
        elif isinstance(exc, ValueError):
            retryable, message = True, f"AI 回覆格式不正確（{exc}）"
        else:
            log.exception("文案產生失敗")
            retryable, message = True, "產生文案時發生未預期的錯誤"
        retrying = retryable and will_retry(task)
        for script in db.scalars(select(Script).where(Script.id.in_(ids))).all():
            script.status = "generating" if retrying else "failed"
            script.error = (f"{message}，稍後自動重試" if retrying else message)[:500]
        db.commit()
        raise ScriptError(message, retryable=retryable) from exc
