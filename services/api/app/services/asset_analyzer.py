"""素材分析（worker 執行）：指紋 → 讀取資訊 → 預覽檔與封面 → 切鏡頭 → 關鍵畫面與重複偵測 → AI 標註 → 分類。"""

import base64
import hashlib
import json
import logging
import re
import shutil
from collections import Counter
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.errors import AppError
from app.models import Asset, Clip, Task, utcnow
from app.services import ai_provider, media
from app.services.tasks import will_retry

log = logging.getLogger("starfly.analyzer")

TASK_TYPE = "asset.analyze"

# 場景分類（代碼 → 顯示名稱）。前端 src/api/index.ts 的 SCENE_LABELS 要同步。
SCENES = {
    "workshop": "工廠車間",
    "production": "生產過程",
    "product_closeup": "產品特寫",
    "packing": "包裝出貨",
    "warehouse": "倉庫庫存",
    "talking_head": "人物口播",
    "storefront": "門店環境",
    "team": "團隊人物",
    "outdoor": "戶外環境",
    "other": "其他",
}
QUALITIES = {"good", "ok", "poor"}
# dHash 漢明距離不超過這個值，就視為畫面幾乎相同
NEAR_DUPLICATE_DISTANCE = 6
DARK_LUMA = 40

SYSTEM_PROMPT = (
    "你是工廠與實體門店短影片的素材分類助手。看一張影片關鍵畫面，只輸出一個 JSON 物件，不要其他文字。\n"
    "欄位：\n"
    f'- scene：從 {json.dumps(list(SCENES), ensure_ascii=False)} 擇一，'
    f"對應 {json.dumps(SCENES, ensure_ascii=False)}\n"
    "- subjects：畫面主體（例如 產品、機台、工人、貨架），最多 5 個繁體中文詞\n"
    "- tags：適合用來搜尋與混剪挑選的標籤（材質、動作、顏色、氛圍等），最多 8 個繁體中文詞\n"
    "- description：一句繁體中文描述畫面內容，30 字以內\n"
    '- quality：畫面品質 "good"（清楚可用）、"ok"（普通）、"poor"（模糊、過暗、嚴重晃動或被遮擋）'
)


class AnalyzeError(Exception):
    def __init__(self, message: str, *, retryable: bool = True):
        super().__init__(message)
        self.retryable = retryable


def _set_stage(db: Session, asset: Asset, stage: str) -> None:
    asset.stage = stage
    db.commit()


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as f:
        while chunk := f.read(4 * 1024 * 1024):
            if media.SHUTDOWN.is_set():
                raise media.Interrupted()
            digest.update(chunk)
    return digest.hexdigest()


def _clear_derived(directory: Path) -> None:
    for name in ("proxy.mp4", "proxy.tmp.mp4", "poster.jpg"):
        (directory / name).unlink(missing_ok=True)
    shutil.rmtree(directory / "clips", ignore_errors=True)


def parse_tags(text: str) -> dict:
    """解析看圖模型的回覆；格式不對時丟 ValueError。"""
    match = re.search(r"\{.*\}", text, re.S)
    if not match:
        raise ValueError("回覆中沒有 JSON")
    data = json.loads(match.group(0))
    if not isinstance(data, dict):
        raise ValueError("回覆不是 JSON 物件")

    def words(value, limit: int) -> list[str]:
        if isinstance(value, str):
            value = re.split(r"[,，、]", value)
        if not isinstance(value, list):
            return []
        out: list[str] = []
        for item in value:
            item = str(item).strip()[:20]
            if item and item not in out:
                out.append(item)
        return out[:limit]

    scene = str(data.get("scene", "")).strip()
    quality = str(data.get("quality", "")).strip().lower()
    return {
        "scene": scene if scene in SCENES else "other",
        "subjects": words(data.get("subjects"), 5),
        "tags": words(data.get("tags"), 8),
        "description": str(data.get("description", "")).strip()[:200],
        "quality": quality if quality in QUALITIES else "",
    }


def _tag_clips(db: Session, asset: Asset, clips: list[Clip], directory: Path) -> str:
    """呼叫看圖模型標註鏡頭，回傳提醒文字（全部成功時為空字串）。"""
    try:
        model = ai_provider.default_model(db, asset.tenant_id, "vision")
    except AppError:
        return "尚未設定看圖模型，略過 AI 標籤（到「模型渠道」新增豆包等看圖模型後可重新分析）"

    limit = get_settings().vision_max_clips
    targets = [c for c in clips if not c.is_dark][:limit]
    hint = f"素材檔名：{asset.original_filename}" + (f"；備註：{asset.note}" if asset.note else "")
    failed = consecutive = 0
    last_error = ""
    for n, clip in enumerate(targets, 1):
        if media.SHUTDOWN.is_set():
            raise media.Interrupted()
        _set_stage(db, asset, f"AI 標註鏡頭 {n}/{len(targets)}")
        image = base64.b64encode((directory / "clips" / f"{clip.index:03d}.jpg").read_bytes()).decode()
        messages = [
            {"role": "system", "content": SYSTEM_PROMPT},
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": hint},
                    {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{image}"}},
                ],
            },
        ]
        try:
            result = ai_provider.chat(db, model, messages, source="asset_analyze", user=None, max_tokens=400)
            tags = parse_tags(result.content)
        except AppError as exc:
            failed += 1
            consecutive += 1
            last_error = exc.message
            if exc.reason in ("missing_api_key", "model_disabled", "unsupported_capability"):
                return f"看圖模型無法使用：{exc.message}"
            if consecutive >= 3:
                return f"AI 標註連續失敗，已停止：{last_error}"
            continue
        except ValueError:
            failed += 1
            consecutive += 1
            last_error = "模型回覆格式不正確"
            if consecutive >= 3:
                return f"AI 標註連續失敗，已停止：{last_error}"
            continue
        consecutive = 0
        clip.scene = tags["scene"]
        clip.subjects = tags["subjects"]
        clip.tags = tags["tags"]
        clip.description = tags["description"]
        clip.quality = tags["quality"]
        clip.tagged_by = "ai"
        db.commit()

    notes = []
    if failed:
        notes.append(f"{failed} 個鏡頭 AI 標註失敗（{last_error}）")
    skipped = len([c for c in clips if not c.is_dark]) - len(targets)
    if skipped > 0:
        notes.append(f"鏡頭較多，只標註前 {limit} 個")
    return "；".join(notes)


def dominant_scene(clips: list[Clip]) -> str:
    weights: Counter[str] = Counter()
    for clip in clips:
        if clip.scene:
            weights[clip.scene] += max(clip.end - clip.start, 0.5)
    return weights.most_common(1)[0][0] if weights else ""


def _mark_near_duplicates(db: Session, asset: Asset, clips: list[Clip]) -> None:
    candidates = [c for c in clips if c.dhash and not c.is_dark]
    if not candidates:
        return
    existing = db.execute(
        select(Clip.id, Clip.dhash)
        .join(Asset, Asset.id == Clip.asset_id)
        .where(
            Clip.tenant_id == asset.tenant_id,
            Clip.asset_id != asset.id,
            Clip.dhash.is_not(None),
            Clip.dhash != 0,
            Clip.is_dark.is_(False),
            Asset.created_at < asset.created_at,
        )
        .order_by(Asset.created_at, Clip.index)
    ).all()
    for clip in candidates:
        for other_id, other_hash in existing:
            if media.hamming(clip.dhash, other_hash) <= NEAR_DUPLICATE_DISTANCE:
                clip.duplicate_of_clip_id = other_id
                break


def _analyze(db: Session, asset: Asset) -> dict:
    directory = media.asset_dir(asset.tenant_id, asset.id)
    original = media.media_root() / asset.storage_key
    if not original.exists():
        raise AnalyzeError("找不到原始檔，請重新上傳", retryable=False)

    asset.status = "processing"
    asset.error = ""
    _set_stage(db, asset, "計算檔案指紋")
    asset.sha256 = _sha256(original)
    asset.size_bytes = original.stat().st_size
    same = db.scalars(
        select(Asset)
        .where(
            Asset.tenant_id == asset.tenant_id,
            Asset.sha256 == asset.sha256,
            Asset.id != asset.id,
            Asset.status.in_(("uploaded", "processing", "ready", "failed")),
            Asset.created_at < asset.created_at,
        )
        .order_by(Asset.created_at)
    ).first()
    if same:
        # 完全相同的檔案：不保留第二份，節省磁碟空間
        asset.status = "duplicate"
        asset.duplicate_of = same.id
        asset.stage = ""
        asset.analyzed_at = utcnow()
        shutil.rmtree(directory, ignore_errors=True)
        db.commit()
        return {"duplicate_of": same.id}

    _set_stage(db, asset, "讀取檔案資訊")
    try:
        info = media.probe(original, asset.kind)
    except media.MediaError as exc:
        raise AnalyzeError(str(exc), retryable=False) from None
    asset.duration, asset.width, asset.height = info.duration, info.width, info.height
    asset.fps, asset.has_audio = info.fps, info.has_audio

    _clear_derived(directory)
    asset.has_proxy = asset.has_poster = False
    asset.clips.clear()
    db.flush()
    (directory / "clips").mkdir(parents=True, exist_ok=True)

    if asset.kind == "video":
        _set_stage(db, asset, "產生預覽檔")
        proxy = directory / "proxy.mp4"
        media.make_proxy(original, proxy)
        asset.has_proxy = True
        media.extract_frame(proxy, directory / "poster.jpg", at=min(1.0, info.duration / 2), long_side=1280)
        asset.has_poster = True
        _set_stage(db, asset, "切分鏡頭")
        segments = media.build_segments(media.detect_scene_cuts(proxy), info.duration)
        source = proxy
    else:
        media.extract_frame(original, directory / "poster.jpg", at=None, long_side=1280)
        asset.has_poster = True
        segments = [(0.0, 0.0)]
        source = directory / "poster.jpg"

    _set_stage(db, asset, f"擷取 {len(segments)} 個鏡頭的關鍵畫面")
    clips: list[Clip] = []
    for index, (start, end) in enumerate(segments):
        thumb = directory / "clips" / f"{index:03d}.jpg"
        at = None if asset.kind == "image" else start + (end - start) / 2
        media.extract_frame(source, thumb, at=at, long_side=512)
        dhash, luma = media.frame_signature(thumb)
        clip = Clip(
            tenant_id=asset.tenant_id,
            index=index,
            start=start,
            end=end,
            dhash=dhash,
            is_dark=luma < DARK_LUMA,
        )
        asset.clips.append(clip)
        clips.append(clip)
    db.flush()
    _mark_near_duplicates(db, asset, clips)
    db.commit()

    warning = _tag_clips(db, asset, clips, directory)
    asset.category = dominant_scene(clips)
    asset.status = "ready"
    asset.stage = warning
    asset.analyzed_at = utcnow()
    db.commit()
    return {"clips": len(clips), "warning": warning}


def analyze_task(db: Session, task: Task) -> dict:
    asset = db.get(Asset, task.payload.get("asset_id"))
    if asset is None:
        return {"skipped": "asset_deleted"}
    try:
        return _analyze(db, asset)
    except media.Interrupted:
        db.rollback()
        if (asset := db.get(Asset, asset.id)) is not None:
            asset.status, asset.stage = "uploaded", "等待重新處理"
            db.commit()
        raise
    except Exception as exc:
        db.rollback()
        asset = db.get(Asset, asset.id)
        if asset is None:  # 分析途中素材被刪除
            return {"skipped": "asset_deleted"}
        if isinstance(exc, AnalyzeError):
            message, retryable = str(exc), exc.retryable
        elif isinstance(exc, media.MediaError):
            message, retryable = str(exc), True
        else:
            log.exception("素材 %s 分析失敗", asset.id)
            message, retryable = "分析時發生未預期的錯誤", True
        retrying = retryable and will_retry(task)
        asset.status = "failed"
        asset.stage = "稍後自動重試" if retrying else ""
        asset.error = message[:500]
        db.commit()
        raise AnalyzeError(message, retryable=retryable) from exc
