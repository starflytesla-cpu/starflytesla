"""混剪渲染（worker 任務 video.render）：已核准文案 → 時間軸 → 1080x1920 成片。

1. 每個鏡頭的配音稿用帳號檔案的音色產生配音（speech.cached_tts：相同文字 + 音色會重用快取，不重複扣點數）
2. 鏡頭長度 = 配音長度 + 0.35 秒；沒有配音稿時用模板建議秒數
3. 依期望畫面類型、標籤、畫面品質、近期使用次數與隨機數為每個鏡頭挑素材片段（不夠長就接下一段）
4. 每段素材正規化 → 串接 → 燒入 ASS 字幕（上方大字幕 + 下方逐句字幕）→ 與配音、壓低的環境音混音

同一份文案產生多支成片時，每支用不同的隨機種子：挑到的素材、片段起點、放大比例、字幕樣式都不同（矩陣號差異化）。
"""

import logging
import random
import re
import shutil
import time
from collections import Counter
from datetime import timedelta
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.errors import AppError
from app.models import Asset, BrandProfile, Clip, Script, Task, UsageLedger, User, Video, utcnow
from app.services import ai_provider, media, music, speech
from app.services.tasks import will_retry

log = logging.getLogger("starfly.renderer")

TASK_TYPE = "video.render"
VOICE_PAD = 0.35
MIN_SHOT = 1.5
MAX_SEGMENTS_PER_SHOT = 4
USAGE_WINDOW = timedelta(days=30)

# 字幕樣式（ASS 顏色格式 &HAABBGGRR）。random 會隨機挑一個。
STYLES: dict[str, dict] = {
    "classic": {"label": "經典白字黑邊", "sub": "&H00FFFFFF", "sub_outline": "&H00000000", "sub_box": False,
                "cap": "&H00FFFFFF", "cap_back": "&H99000000", "cap_box": True},
    "highlight": {"label": "黃字醒目", "sub": "&H0000E5FF", "sub_outline": "&H00000000", "sub_box": False,
                  "cap": "&H00FFFFFF", "cap_back": "&H00000000", "cap_box": False},
    "box": {"label": "黑底字卡", "sub": "&H00FFFFFF", "sub_outline": "&H80000000", "sub_box": True,
            "cap": "&H0000E5FF", "cap_back": "&H00000000", "cap_box": False},
    "pop": {"label": "藍邊活潑", "sub": "&H00FFFFFF", "sub_outline": "&H00FF6B2F", "sub_box": False,
            "cap": "&H00FFFFFF", "cap_back": "&HB0FF6B2F", "cap_box": True},
}
FONTS = {
    "ja": "Noto Sans CJK JP",
    "ko": "Noto Sans CJK KR",
    "zh-TW": "Noto Sans CJK TC",
    "ar": "Noto Sans Arabic",
    "th": "Noto Sans Thai",
}
CHAR_LANGUAGES = {"ja", "ko", "zh-TW", "th"}


class RenderError(Exception):
    def __init__(self, message: str, *, retryable: bool = True):
        super().__init__(message)
        self.retryable = retryable


def video_dir(tenant_id: str, video_id: str) -> Path:
    return media.media_root() / tenant_id / "videos" / video_id


def _set_stage(db: Session, video: Video, stage: str) -> None:
    video.stage = stage
    db.commit()


# ---------------------------------------------------------------- 挑素材
def load_pool(db: Session, tenant_id: str) -> list[dict]:
    rows = db.execute(
        select(Clip, Asset)
        .join(Asset, Asset.id == Clip.asset_id)
        .where(
            Clip.tenant_id == tenant_id,
            Asset.status == "ready",
            Asset.is_disabled.is_(False),
            Clip.is_disabled.is_(False),
            Clip.is_dark.is_(False),
        )
    ).all()
    return [
        {
            "clip_id": clip.id,
            "asset_id": asset.id,
            "kind": asset.kind,
            "source": asset.storage_key,
            "has_audio": asset.has_audio,
            "start": clip.start,
            "end": clip.end,
            "length": (clip.end - clip.start) if asset.kind == "video" else None,
            "scene": clip.scene,
            "words": {w.lower() for w in (clip.tags or []) + (clip.subjects or [])},
            "quality": clip.quality,
            "duplicate": bool(clip.duplicate_of_clip_id),
            "index": clip.index,
        }
        for clip, asset in rows
    ]


def usage_counts(db: Session, tenant_id: str, exclude_video: str | None = None) -> Counter:
    counts: Counter = Counter()
    timelines = db.scalars(
        select(Video.timeline).where(
            Video.tenant_id == tenant_id,
            Video.created_at >= utcnow() - USAGE_WINDOW,
            Video.timeline.is_not(None),
            Video.id != (exclude_video or ""),
        )
    ).all()
    for timeline in timelines:
        for shot in (timeline or {}).get("shots", []):
            for seg in shot.get("segments", []):
                counts[seg.get("clip_id")] += 1
    return counts


def _keywords(shot: dict) -> set[str]:
    text = f"{shot.get('brief', '')} {shot.get('voiceover', '')} {shot.get('caption', '')}".lower()
    return {w for w in re.findall(r"\w+", text) if len(w) > 2}


def _score(clip: dict, scene: str, keywords: set[str], usage: Counter, rng: random.Random) -> float:
    score = 0.0
    if scene and clip["scene"] == scene:
        score += 3
    if clip["quality"] == "good":
        score += 1
    elif clip["quality"] == "poor":
        score -= 1.5
    if clip["duplicate"]:
        score -= 2
    score -= 0.6 * min(usage[clip["clip_id"]], 4)
    score += 0.5 * min(len(clip["words"] & keywords), 3)
    return score + rng.random() * 1.5


# 素材比需要的短一點（例如差 20% 以內）時放慢播放補足，不要停格；再短就接下一段素材
MAX_SLOWDOWN = 1.25
MIN_SEGMENT_FRAMES = 9  # 0.3 秒以下的片段不用（太短看起來像閃爍）


def _segment(clip: dict, frame_count: int, start: float, src_duration: float, zoom: float) -> dict:
    return {
        "clip_id": clip["clip_id"],
        "asset_id": clip["asset_id"],
        "kind": clip["kind"],
        "source": clip["source"],
        "has_audio": clip["has_audio"],
        "start": round(start, 3),
        "frames": frame_count,
        "duration": round(frame_count / media.OUT_FPS, 3),
        "src_duration": round(src_duration, 3),
        "zoom": zoom,
    }


def choose_segments(
    pool: list[dict], shot: dict, need_frames: int, used: set[str], usage: Counter, rng: random.Random,
    *, first: dict | None = None,
) -> list[dict]:
    """為一個鏡頭挑素材片段，總格數剛好 = need_frames。

    優先挑沒用過、場景相符、品質好的片段；素材稍短就放慢，太短就接下一段；
    素材都用過了才重複使用（不同起點），任何情況都不會停格補時間。first：人工指定的第一段素材。
    """
    scene = shot.get("scene", "")
    keywords = _keywords(shot)
    in_shot: set[str] = set()
    segments: list[dict] = []
    remaining = need_frames
    while remaining > 0 and len(segments) < MAX_SEGMENTS_PER_SHOT + 2:
        if first is not None and not segments:
            clip = first
        else:
            candidates = [c for c in pool if c["clip_id"] not in used and c["clip_id"] not in in_shot]
            if not candidates:
                # 全部素材都用過：允許重複使用，但不在同一個鏡頭內重複
                candidates = [c for c in pool if c["clip_id"] not in in_shot] or list(pool)
            clip = max(candidates, key=lambda c: _score(c, scene, keywords, usage, rng))
        used.add(clip["clip_id"])
        in_shot.add(clip["clip_id"])
        zoom = round(rng.uniform(1.0, 1.06), 3)
        if clip["kind"] == "image" or clip["length"] is None:
            segments.append(_segment(clip, remaining, 0.0, remaining / media.OUT_FPS, zoom))
            break
        available = int(clip["length"] * media.OUT_FPS)
        last_chance = len(segments) >= MAX_SEGMENTS_PER_SHOT - 1
        if available >= remaining:
            slack = clip["length"] - remaining / media.OUT_FPS
            start = clip["start"] + (rng.uniform(0, slack) if slack > 0.1 else 0.0)
            segments.append(_segment(clip, remaining, start, remaining / media.OUT_FPS, zoom))
            break
        if available * MAX_SLOWDOWN >= remaining or (last_chance and available >= MIN_SEGMENT_FRAMES):
            # 稍短（或已經接了很多段）：整段放慢補足
            segments.append(_segment(clip, remaining, clip["start"], clip["length"], zoom))
            break
        if available < MIN_SEGMENT_FRAMES:
            continue
        segments.append(_segment(clip, available, clip["start"], available / media.OUT_FPS, zoom))
        remaining -= available
    return segments


def segment_for_clip(
    db: Session, tenant_id: str, clip_id: str, shot: dict, need_frames: int, rng: random.Random | None = None
) -> list[dict]:
    """人工換素材：指定的鏡頭排第一段，太短時自動接其他素材補足（不停格）。"""
    pool = load_pool(db, tenant_id)
    chosen = next((c for c in pool if c["clip_id"] == clip_id), None)
    if chosen is None:
        raise AppError(400, "clip_unavailable", "這個素材鏡頭無法使用（可能已停用或刪除）")
    return choose_segments(pool, shot, need_frames, set(), Counter(), rng or random.Random(), first=chosen)


def plan_timeline(db: Session, video: Video, script: Script, profile: BrandProfile | None) -> dict:
    options = video.options or {}
    rng = random.Random(options.get("seed") or video.id)
    style = options.get("style") or "random"
    if style not in STYLES:
        style = rng.choice(sorted(STYLES))
    creator = db.get(User, video.created_by) if video.created_by else None

    pool = load_pool(db, video.tenant_id)
    if not pool:
        raise RenderError("素材庫沒有可用的鏡頭，請先上傳並分析素材", retryable=False)
    tts_model = ai_provider.default_model(db, video.tenant_id, "tts")
    voice_id, speed, voice_style = speech.profile_voice(tts_model, profile)
    usage = usage_counts(db, video.tenant_id, exclude_video=video.id)

    shots = []
    for i, shot in enumerate(script.shots):
        text = (shot.get("voiceover") or "").strip()
        audio, voice_len = None, 0.0
        if text:
            _set_stage(db, video, f"產生配音 {i + 1}/{len(script.shots)}")
            audio, voice_len = speech.cached_tts(
                db, creator, tts_model, video.tenant_id, text, voice_id, speed, voice_style, source="video_render"
            )
        seconds = max(voice_len + VOICE_PAD, MIN_SHOT) if text else float(shot.get("seconds") or 3)
        frame_count = media.frames(seconds)
        shots.append(
            {
                "index": i,
                "brief": shot.get("brief", ""),
                "scene": shot.get("scene", ""),
                "caption": (shot.get("caption") or "").strip(),
                "voiceover": text,
                "audio": audio,
                "voice_duration": round(voice_len, 3),
                "frames": frame_count,
                "duration": round(frame_count / media.OUT_FPS, 3),
            }
        )

    _set_stage(db, video, "挑選素材")
    used: set[str] = set()
    for shot in shots:
        shot["segments"] = choose_segments(pool, shot, shot["frames"], used, usage, rng)
    return {
        "width": media.OUT_W,
        "height": media.OUT_H,
        "fps": media.OUT_FPS,
        "language": script.language,
        "tts_model": tts_model.model_key,
        "voice_id": voice_id,
        "voice_speed": speed,
        "style": style,
        "ambience": float(options.get("ambience", 0.0)),
        "bgm": music.pick_for_video(db, video.tenant_id, options, rng),
        "shots": shots,
    }


# ---------------------------------------------------------------- 字幕
def _ass_time(seconds: float) -> str:
    cs = max(0, int(round(seconds * 100)))
    return f"{cs // 360000}:{cs // 6000 % 60:02d}:{cs // 100 % 60:02d}.{cs % 100:02d}"


def _ass_text(text: str) -> str:
    return text.replace("\\", "\\\\").replace("{", "(").replace("}", ")").replace("\n", " ")


def split_subtitle(text: str, language: str) -> list[str]:
    """把配音稿切成一句句短字幕（每句一到兩行）。"""
    if language in CHAR_LANGUAGES:
        parts = [p for p in re.split(r"(?<=[。！？，、!?,])", text) if p.strip()]
        chunks: list[str] = []
        for part in parts:
            # 超出不多（20 字內）就不切，避免最後一兩個字單獨成一句
            while len(part) > 20:
                chunks.append(part[:16])
                part = part[16:]
            if part.strip():
                chunks.append(part.strip())
        return chunks
    words = text.split()
    chunks, current = [], []
    for word in words:
        if current and (len(" ".join(current + [word])) > 32 or len(current) >= 7):
            chunks.append(" ".join(current))
            current = []
        current.append(word)
        if word[-1:] in ".!?" and len(current) >= 3:
            chunks.append(" ".join(current))
            current = []
    if current:
        chunks.append(" ".join(current))
    return chunks


def build_ass(timeline: dict) -> str:
    style = STYLES.get(timeline.get("style"), STYLES["classic"])
    font = FONTS.get(timeline.get("language", "en"), "Noto Sans")
    sub_border = 3 if style["sub_box"] else 1
    cap_border = 3 if style["cap_box"] else 1
    lines = [
        "[Script Info]",
        "ScriptType: v4.00+",
        f"PlayResX: {media.OUT_W}",
        f"PlayResY: {media.OUT_H}",
        "WrapStyle: 0",
        "ScaledBorderAndShadow: yes",
        "",
        "[V4+ Styles]",
        "Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, "
        "Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, "
        "MarginR, MarginV, Encoding",
        f"Style: Caption,{font},84,{style['cap']},&H000000FF,&H00000000,{style['cap_back']},-1,0,0,0,100,100,0,0,"
        f"{cap_border},{12 if style['cap_box'] else 6},0,8,70,70,250,1",
        f"Style: Sub,{font},66,{style['sub']},&H000000FF,{style['sub_outline']},&H80000000,-1,0,0,0,100,100,0,0,"
        f"{sub_border},{10 if style['sub_box'] else 5},1,2,80,80,430,1",
        "",
        "[Events]",
        "Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text",
    ]
    t = 0.0
    language = timeline.get("language", "en")
    for shot in timeline["shots"]:
        start, end = t, t + shot["duration"]
        if shot.get("caption"):
            pop = "{\\fad(120,120)\\fscx85\\fscy85\\t(0,180,\\fscx100\\fscy100)}"
            lines.append(f"Dialogue: 1,{_ass_time(start)},{_ass_time(end)},Caption,,0,0,0,,{pop}{_ass_text(shot['caption'])}")
        chunks = split_subtitle(shot.get("voiceover", ""), language)
        speak = shot.get("voice_duration") or max(shot["duration"] - VOICE_PAD, 0.5)
        total = sum(len(c) for c in chunks) or 1
        cursor = start + 0.05
        for chunk in chunks:
            length = speak * len(chunk) / total
            lines.append(
                f"Dialogue: 0,{_ass_time(cursor)},{_ass_time(min(cursor + length, end))},Sub,,0,0,0,,{_ass_text(chunk)}"
            )
            cursor += length
        t = end
    return "\n".join(lines) + "\n"


# ---------------------------------------------------------------- 渲染
def _shot_frames(shot: dict) -> int:
    return shot.get("frames") or media.frames(shot["duration"])


def _seg_frames(seg: dict) -> int:
    return seg.get("frames") or media.frames(seg["duration"])


def render_timeline(db: Session, video: Video, timeline: dict) -> float:
    """依時間軸輸出 final.mp4 與 poster.jpg，回傳成片秒數。

    每段素材輸出純影像（格數精確）＋需要時的無損原聲，最後一次合成，避免接縫誤差造成卡頓。
    """
    root = media.media_root()
    out_dir = video_dir(video.tenant_id, video.id)
    work = out_dir / "work"
    shutil.rmtree(work, ignore_errors=True)
    work.mkdir(parents=True)
    try:
        ambience_volume = float(timeline.get("ambience", 0.0))
        parts: list[Path] = []
        sounds: list[Path] = []
        for shot in timeline["shots"]:
            # 舊版時間軸沒有格數時，最後一段補齊到鏡頭長度
            segs = shot["segments"]
            counts = [_seg_frames(seg) for seg in segs]
            if segs:
                counts[-1] = max(1, _shot_frames(shot) - sum(counts[:-1]))
            for seg, count in zip(segs, counts):
                n = len(parts) + 1
                _set_stage(db, video, f"處理素材片段 {n}")
                src = root / seg["source"]
                if not src.exists():
                    raise RenderError("有素材的原始檔已被刪除，請按「重新挑素材」", retryable=False)
                src_duration = seg.get("src_duration") or seg["duration"]
                part = work / f"seg_{n:03d}.mp4"
                media.render_segment(
                    src, part, kind=seg["kind"], start=seg["start"], frame_count=count,
                    src_duration=src_duration, zoom=seg.get("zoom", 1.0),
                )
                parts.append(part)
                if ambience_volume > 0:
                    sound = work / f"amb_{n:03d}.wav"
                    has_audio = seg.get("has_audio") and seg["kind"] == "video"
                    media.render_segment_audio(
                        src if has_audio else None, sound, start=seg["start"], frame_count=count, src_duration=src_duration
                    )
                    sounds.append(sound)

        _set_stage(db, video, "合成字幕、配音與背景音樂")
        total_frames = sum(_shot_frames(s) for s in timeline["shots"])
        voice = work / "voice.wav"
        media.build_voice_track(
            [((root / s["audio"]) if s.get("audio") else None, _shot_frames(s)) for s in timeline["shots"]], voice
        )
        ambience = None
        if sounds:
            ambience = work / "ambience.wav"
            media.concat_audio(sounds, ambience)
        bgm = timeline.get("bgm") or {}
        bgm_path = root / bgm["source"] if bgm.get("source") else None
        if bgm_path is not None and not bgm_path.exists():
            bgm_path = None  # 背景音樂已被刪除：不加音樂，不讓整支失敗
        subtitles = work / "subtitles.ass"
        subtitles.write_text(build_ass(timeline), encoding="utf-8")
        final = out_dir / "final.mp4"
        media.compose_final(
            parts, voice, subtitles, final, total_frames=total_frames,
            ambience=ambience, ambience_volume=ambience_volume,
            bgm=bgm_path, bgm_volume=float(bgm.get("volume", 0.0)),
        )
        media.extract_frame(final, out_dir / "poster.jpg", at=min(1.0, timeline["shots"][0]["duration"] / 2), long_side=1280)
        return round(total_frames / media.OUT_FPS, 3)
    finally:
        shutil.rmtree(work, ignore_errors=True)


def _record_render(db: Session, video: Video, status: str, seconds: float, error: str = "") -> None:
    db.add(
        UsageLedger(
            tenant_id=video.tenant_id,
            user_id=video.created_by,
            action="render.video",
            source="video_render",
            provider="local",
            model_key="ffmpeg",
            status=status,
            duration_ms=int(seconds * 1000),
            # 渲染用自己的伺服器，沒有額外費用；記錄耗時供日後訂積分價格
            cost_micros=0,
            error=error[:500],
        )
    )
    db.commit()


def _render(db: Session, video: Video, mode: str) -> dict:
    started = time.monotonic()
    video.status, video.error = "rendering", ""
    _set_stage(db, video, "準備中")
    if mode != "rerender" or not video.timeline:
        script = db.get(Script, video.script_id) if video.script_id else None
        if script is None:
            raise RenderError("文案已被刪除，無法重新挑素材", retryable=False)
        profile = db.get(BrandProfile, video.profile_id) if video.profile_id else None
        video.timeline = plan_timeline(db, video, script, profile)
        db.commit()
    duration = render_timeline(db, video, video.timeline)
    elapsed = time.monotonic() - started
    video.duration = duration
    video.has_output = True
    video.render_seconds = round(elapsed, 1)
    video.rendered_at = utcnow()
    video.status = "pending_review"
    video.stage = ""
    video.review_note = ""
    video.reviewed_at = None
    video.reviewed_by = None
    db.commit()
    _record_render(db, video, "succeeded", elapsed)
    return {"duration": duration, "seconds": round(elapsed, 1)}


def render_task(db: Session, task: Task) -> dict:
    video = db.get(Video, task.payload.get("video_id"))
    if video is None:
        return {"skipped": "video_deleted"}
    started = time.monotonic()
    try:
        return _render(db, video, task.payload.get("mode", "plan"))
    except media.Interrupted:
        db.rollback()
        if (video := db.get(Video, video.id)) is not None:
            video.status, video.stage = "queued", "等待重新處理"
            db.commit()
        raise
    except Exception as exc:
        db.rollback()
        video = db.get(Video, video.id)
        if video is None:
            return {"skipped": "video_deleted"}
        if isinstance(exc, RenderError):
            message, retryable = str(exc), exc.retryable
        elif isinstance(exc, AppError):
            # 上游（配音）暫時錯誤可重試；沒有設定配音模型等設定問題重試也沒用
            message, retryable = exc.message, exc.status >= 500
        elif isinstance(exc, media.MediaError):
            message, retryable = str(exc), True
        else:
            log.exception("成片 %s 渲染失敗", video.id)
            message, retryable = "渲染時發生未預期的錯誤", True
        retrying = retryable and will_retry(task)
        video.status = "queued" if retrying else "failed"
        video.stage = "稍後自動重試" if retrying else ""
        video.error = message[:500]
        db.commit()
        _record_render(db, video, "failed", time.monotonic() - started, message)
        raise RenderError(message, retryable=retryable) from exc
