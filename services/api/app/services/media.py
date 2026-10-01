"""素材檔案的存放路徑與 FFmpeg / FFprobe 呼叫。

檔案放在 MEDIA_ROOT（容器內 /media，資料碟上的 Docker volume）：
  _uploads/{upload_id}.part              上傳中的暫存檔
  {tenant}/assets/{asset_id}/original.*  原始檔
  {tenant}/assets/{asset_id}/proxy.mp4   720p 預覽檔
  {tenant}/assets/{asset_id}/poster.jpg  封面
  {tenant}/assets/{asset_id}/clips/NNN.jpg  每個鏡頭的關鍵畫面
網頁透過 Caddy 的 /media/... 讀取，由 /api/media/auth 檢查登入與租戶。
"""

import json
import shutil
import subprocess
import threading
import time
from dataclasses import dataclass
from pathlib import Path

from app.config import get_settings

# worker 收到停止訊號時設定，正在執行的 FFmpeg 會被中止、任務放回佇列
SHUTDOWN = threading.Event()

VIDEO_EXTENSIONS = {".mp4", ".mov", ".m4v", ".webm", ".mkv", ".avi", ".3gp", ".mts"}
IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp"}


class Interrupted(Exception):
    """worker 正在停止，任務中斷（不算失敗，會重新排入佇列）。"""


class MediaError(Exception):
    """檔案無法處理（損毀、格式不支援等），訊息可以直接顯示給使用者。"""


def media_root() -> Path:
    return Path(get_settings().media_root)


def uploads_dir() -> Path:
    return media_root() / "_uploads"


def asset_dir(tenant_id: str, asset_id: str) -> Path:
    return media_root() / tenant_id / "assets" / asset_id


def asset_url(tenant_id: str, asset_id: str, name: str, version: str = "") -> str:
    url = f"/media/{tenant_id}/assets/{asset_id}/{name}"
    return f"{url}?v={version}" if version else url


def kind_for_extension(ext: str) -> str | None:
    ext = ext.lower()
    if ext in VIDEO_EXTENSIONS:
        return "video"
    if ext in IMAGE_EXTENSIONS:
        return "image"
    return None


def free_bytes() -> int:
    root = media_root()
    root.mkdir(parents=True, exist_ok=True)
    return shutil.disk_usage(root).free


def run(cmd: list[str], *, timeout: float = 3600) -> tuple[bytes, str]:
    """執行外部指令，回傳 (stdout, stderr)。worker 停止時中止並丟出 Interrupted。"""
    proc = subprocess.Popen(cmd, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    deadline = time.monotonic() + timeout
    while True:
        try:
            stdout, stderr = proc.communicate(timeout=1)
            break
        except subprocess.TimeoutExpired:
            if SHUTDOWN.is_set() or time.monotonic() > deadline:
                proc.kill()
                proc.communicate()
                if SHUTDOWN.is_set():
                    raise Interrupted() from None
                raise MediaError(f"{Path(cmd[0]).name} 執行逾時") from None
    err = stderr.decode("utf-8", "replace")
    if proc.returncode != 0:
        last = err.strip().splitlines()[-1:] or [""]
        raise MediaError(f"{Path(cmd[0]).name} 處理失敗：{last[0][:200]}")
    return stdout, err


FFMPEG = ["ffmpeg", "-nostdin", "-hide_banner", "-loglevel", "error", "-y"]


@dataclass
class ProbeInfo:
    kind: str
    duration: float | None
    width: int | None
    height: int | None
    fps: float | None
    has_audio: bool


def _fraction(value: str | None) -> float | None:
    if not value or value in ("0/0", "0"):
        return None
    try:
        if "/" in value:
            num, den = value.split("/", 1)
            return float(num) / float(den) if float(den) else None
        return float(value)
    except ValueError:
        return None


def _rotation(stream: dict) -> int:
    for item in stream.get("side_data_list") or []:
        if "rotation" in item:
            return int(float(item["rotation"]))
    rotate = (stream.get("tags") or {}).get("rotate")
    return int(float(rotate)) if rotate else 0


def probe(path: Path, kind: str) -> ProbeInfo:
    out, _ = run(
        ["ffprobe", "-v", "error", "-print_format", "json", "-show_format", "-show_streams", str(path)],
        timeout=120,
    )
    try:
        data = json.loads(out)
    except ValueError:
        raise MediaError("無法讀取檔案資訊") from None
    streams = data.get("streams") or []
    video = next((s for s in streams if s.get("codec_type") == "video"), None)
    if not video:
        raise MediaError("檔案裡沒有影像，可能已損毀或不是影片 / 照片")
    width, height = video.get("width"), video.get("height")
    if width and height and abs(_rotation(video)) % 180 == 90:
        width, height = height, width
    if kind == "image":
        return ProbeInfo("image", None, width, height, None, False)
    duration = _fraction((data.get("format") or {}).get("duration")) or _fraction(video.get("duration"))
    if not duration or duration <= 0:
        raise MediaError("無法取得影片長度，檔案可能不完整")
    fps = _fraction(video.get("avg_frame_rate")) or _fraction(video.get("r_frame_rate"))
    return ProbeInfo(
        kind="video",
        duration=round(duration, 3),
        width=width,
        height=height,
        fps=round(fps, 3) if fps else None,
        has_audio=any(s.get("codec_type") == "audio" for s in streams),
    )


def _fit(short_side: int) -> str:
    """把短邊縮到不超過 short_side（不放大），長邊等比例且為偶數。"""
    s = short_side
    return (
        f"scale='if(gt(iw,ih),-2,trunc(min({s},iw)/2)*2)'"
        f":'if(gt(iw,ih),trunc(min({s},ih)/2)*2,-2)'"
    )


def _fit_long(long_side: int) -> str:
    """把長邊縮到不超過 long_side（不放大）。"""
    s = long_side
    return (
        f"scale='if(gt(iw,ih),trunc(min({s},iw)/2)*2,-2)'"
        f":'if(gt(iw,ih),-2,trunc(min({s},ih)/2)*2)'"
    )


def make_proxy(src: Path, dest: Path) -> None:
    """720p H.264 預覽檔（最高 30fps，faststart 讓手機邊下載邊播放）。"""
    tmp = dest.with_suffix(".tmp.mp4")
    run(
        [
            *FFMPEG, "-i", str(src),
            "-map", "0:v:0", "-map", "0:a:0?",
            "-vf", _fit(720), "-fpsmax", "30",
            "-c:v", "libx264", "-preset", "veryfast", "-crf", "26", "-pix_fmt", "yuv420p",
            "-c:a", "aac", "-b:a", "128k", "-ac", "2",
            "-movflags", "+faststart", str(tmp),
        ]
    )
    tmp.replace(dest)


def extract_frame(src: Path, dest: Path, *, at: float | None, long_side: int) -> None:
    seek = ["-ss", f"{at:.3f}"] if at is not None else []
    run([*FFMPEG, *seek, "-i", str(src), "-frames:v", "1", "-vf", _fit_long(long_side), "-q:v", "4", str(dest)], timeout=120)
    if not dest.exists():
        # 指定時間點超過實際長度時 FFmpeg 不會輸出畫面，改取第一格
        run([*FFMPEG, "-i", str(src), "-frames:v", "1", "-vf", _fit_long(long_side), "-q:v", "4", str(dest)], timeout=120)
    if not dest.exists():
        raise MediaError("無法擷取畫面")


def detect_scene_cuts(src: Path, threshold: float = 0.35) -> list[float]:
    """回傳畫面切換的時間點（秒）。"""
    _, err = run(
        [
            "ffmpeg", "-nostdin", "-hide_banner", "-loglevel", "info", "-i", str(src), "-an",
            "-vf", f"scale=320:-2,select='gt(scene,{threshold})',showinfo", "-f", "null", "-",
        ]
    )
    cuts = []
    for line in err.splitlines():
        if "showinfo" not in line or "pts_time:" not in line:
            continue
        try:
            cuts.append(float(line.split("pts_time:", 1)[1].split()[0]))
        except (ValueError, IndexError):
            continue
    return sorted(set(cuts))


def build_segments(
    cuts: list[float], duration: float, *, min_len: float = 1.0, max_len: float = 15.0
) -> list[tuple[float, float]]:
    """依切換點切成鏡頭：太短（< min_len）的併入前一段，太長（> max_len）的平均切開。"""
    points = [0.0, *sorted(c for c in cuts if 0 < c < duration), duration]
    segments: list[list[float]] = []
    for start, end in zip(points, points[1:]):
        if end - start <= 0:
            continue
        if segments and (end - start < min_len or segments[-1][1] - segments[-1][0] < min_len):
            segments[-1][1] = end
        else:
            segments.append([start, end])
    result: list[tuple[float, float]] = []
    for start, end in segments:
        parts = max(1, int(-(-(end - start) // max_len)))
        step = (end - start) / parts
        for i in range(parts):
            result.append((round(start + i * step, 3), round(end if i == parts - 1 else start + (i + 1) * step, 3)))
    return result


def frame_signature(image: Path) -> tuple[int, float]:
    """回傳 (dHash, 平均亮度 0~255)。dHash 是 64-bit 帶號整數，方便存進 BIGINT。"""
    out, _ = run(
        [*FFMPEG, "-i", str(image), "-vf", "scale=9:8:flags=area,format=gray", "-f", "rawvideo", "-"],
        timeout=60,
    )
    if len(out) < 72:
        raise MediaError("無法計算畫面特徵")
    pixels = out[:72]
    value = 0
    for row in range(8):
        for col in range(8):
            value = (value << 1) | (pixels[row * 9 + col] > pixels[row * 9 + col + 1])
    if value >= 1 << 63:
        value -= 1 << 64
    return value, sum(pixels) / 72


def hamming(a: int, b: int) -> int:
    return ((a ^ b) & ((1 << 64) - 1)).bit_count()


# ---------------------------------------------------------------- 成片渲染（Phase 3）
# 所有長度都以「影格數」計算（30fps），影像與聲音分開產生、最後一次合成，避免片段接縫的時間誤差累積造成卡頓與音畫不同步。
OUT_W, OUT_H, OUT_FPS = 1080, 1920, 30
AUDIO_RATE = 48000
SAMPLES_PER_FRAME = AUDIO_RATE // OUT_FPS  # 1600，影格與音訊取樣剛好整除


def frames(seconds: float) -> int:
    return max(1, round(seconds * OUT_FPS))


def audio_duration(path: Path) -> float:
    out, _ = run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "default=nw=1:nk=1", str(path)],
        timeout=60,
    )
    value = _fraction(out.decode().strip())
    if not value:
        raise MediaError("無法讀取音檔長度")
    return value


def _even(value: float) -> int:
    return int(round(value / 2)) * 2


def render_segment(
    src: Path,
    dest: Path,
    *,
    kind: str,
    start: float,
    frame_count: int,
    src_duration: float | None = None,
    zoom: float = 1.0,
) -> None:
    """輸出剛好 frame_count 格、1080x1920、30fps 的純影像片段。

    src_duration 是要從素材讀取的秒數；比輸出長度短時會等比例放慢（setpts），不會停格。
    照片：緩慢推近（Ken Burns）。
    """
    out_dur = frame_count / OUT_FPS
    common = ["-an", "-frames:v", str(frame_count), "-c:v", "libx264", "-preset", "veryfast", "-crf", "17",
              "-pix_fmt", "yuv420p", "-r", str(OUT_FPS), str(dest)]
    if kind == "image":
        graph = (
            f"scale={OUT_W}:{OUT_H}:force_original_aspect_ratio=increase,crop={OUT_W}:{OUT_H},"
            f"zoompan=z='min(1+0.08*on/{frame_count},1.08)':x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)'"
            f":d=1:s={OUT_W}x{OUT_H}:fps={OUT_FPS},setsar=1,format=yuv420p"
        )
        run([*FFMPEG, "-loop", "1", "-framerate", str(OUT_FPS), "-t", f"{out_dur + 1:.3f}", "-i", str(src),
             "-vf", graph, *common])
        return
    read = src_duration or out_dur
    factor = out_dur / read  # > 1 代表放慢
    w, h = _even(OUT_W * zoom), _even(OUT_H * zoom)
    graph = (
        f"scale={w}:{h}:force_original_aspect_ratio=increase,crop={OUT_W}:{OUT_H},setsar=1,"
        f"setpts={factor:.5f}*(PTS-STARTPTS),fps={OUT_FPS},"
        # 素材實際比預期短一點點時（例如結尾少幾格），用最後一格補，確保格數正確
        "tpad=stop_mode=clone:stop_duration=1,format=yuv420p"
    )
    run([*FFMPEG, "-ss", f"{start:.3f}", "-t", f"{read + 0.5:.3f}", "-i", str(src), "-vf", graph, *common])


def render_segment_audio(
    src: Path | None, dest: Path, *, start: float, frame_count: int, src_duration: float | None = None
) -> None:
    """片段的現場原聲（無損 WAV），取樣數剛好等於影格數 × 1600；src 為 None 時輸出靜音。"""
    samples = frame_count * SAMPLES_PER_FRAME
    fmt = f"aresample={AUDIO_RATE},aformat=sample_fmts=s16:channel_layouts=stereo"
    if src is None:
        cmd = [*FFMPEG, "-f", "lavfi", "-i", f"anullsrc=r={AUDIO_RATE}:cl=stereo", "-af", f"{fmt},atrim=end_sample={samples}"]
    else:
        out_dur = frame_count / OUT_FPS
        read = src_duration or out_dur
        tempo = read / out_dur
        chain = [fmt] + ([f"atempo={max(tempo, 0.5):.5f}"] if abs(tempo - 1) > 0.001 else [])
        chain += ["apad", f"atrim=end_sample={samples}"]
        cmd = [*FFMPEG, "-ss", f"{start:.3f}", "-t", f"{read + 0.5:.3f}", "-i", str(src), "-vn", "-af", ",".join(chain)]
    run([*cmd, "-c:a", "pcm_s16le", str(dest)])


def concat_audio(parts: list[Path], dest: Path) -> None:
    """串接無損 WAV（取樣精確，不會有 AAC 接縫的空隙）。"""
    listing = dest.with_suffix(".txt")
    listing.write_text("".join(f"file '{p.as_posix()}'\n" for p in parts))
    run([*FFMPEG, "-f", "concat", "-safe", "0", "-i", str(listing), "-c", "copy", str(dest)])


def clean_voice(src: Path, dest: Path) -> None:
    """配音整理：去掉頭尾靜音、統一音量（各鏡頭分開產生的配音音量一致）、轉成 48kHz 立體聲 WAV。"""
    trim = "silenceremove=start_periods=1:start_threshold=-45dB:start_silence=0.04"
    graph = f"{trim},areverse,{trim},areverse,loudnorm=I=-16:TP=-1.5:LRA=11,aresample={AUDIO_RATE},aformat=sample_fmts=s16:channel_layouts=stereo"
    tmp = dest.with_name(dest.name + ".tmp.wav")
    run([*FFMPEG, "-i", str(src), "-af", graph, "-c:a", "pcm_s16le", str(tmp)])
    if audio_duration(tmp) < 0.1:
        # 整段被判定為靜音（例如很小聲）：保留原音，不去靜音
        run([*FFMPEG, "-i", str(src), "-af", f"aresample={AUDIO_RATE},aformat=sample_fmts=s16:channel_layouts=stereo",
             "-c:a", "pcm_s16le", str(tmp)])
    tmp.replace(dest)


def build_voice_track(shots: list[tuple[Path | None, int]], dest: Path) -> None:
    """依鏡頭順序把配音接起來，每段補靜音到該鏡頭的影格長度（取樣精確）。"""
    parts = []
    for i, (path, frame_count) in enumerate(shots):
        part = dest.with_name(f"{dest.stem}_{i:03d}.wav")
        samples = frame_count * SAMPLES_PER_FRAME
        if path is None:
            cmd = [*FFMPEG, "-f", "lavfi", "-i", f"anullsrc=r={AUDIO_RATE}:cl=stereo"]
        else:
            cmd = [*FFMPEG, "-i", str(path)]
        run([*cmd, "-af", f"aresample={AUDIO_RATE},aformat=sample_fmts=s16:channel_layouts=stereo,apad,atrim=end_sample={samples}",
             "-c:a", "pcm_s16le", str(part)])
        parts.append(part)
    concat_audio(parts, dest)


def _filter_path(path: Path) -> str:
    return str(path).replace("\\", "\\\\").replace(":", "\\:").replace("'", "\\'")


def compose_final(
    segments: list[Path],
    voice: Path,
    subtitles: Path,
    dest: Path,
    *,
    total_frames: int,
    ambience: Path | None = None,
    ambience_volume: float = 0.0,
    bgm: Path | None = None,
    bgm_volume: float = 0.0,
) -> None:
    """一次合成：串接影像片段 → 燒入字幕；配音 + 背景音樂（配音時自動壓低）+ 現場原聲 混音。"""
    total = total_frames / OUT_FPS
    samples = total_frames * SAMPLES_PER_FRAME
    inputs: list[str] = []
    for seg in segments:
        inputs += ["-i", str(seg)]
    n = len(segments)
    inputs += ["-i", str(voice)]
    voice_idx = n
    graph = [
        "".join(f"[{i}:v]" for i in range(n)) + f"concat=n={n}:v=1:a=0[body]",
        f"[body]ass=filename='{_filter_path(subtitles)}'[v]",
    ]
    mix = ["[vo]"]
    if bgm is not None and bgm_volume > 0:
        inputs += ["-stream_loop", "-1", "-i", str(bgm)]
        bgm_idx = voice_idx + 1
        fade_out = max(total - 1.5, 0)
        graph += [
            f"[{voice_idx}:a]asplit=2[vo][sc]",
            f"[{bgm_idx}:a]aresample={AUDIO_RATE},aformat=sample_fmts=fltp:channel_layouts=stereo,"
            f"atrim=0:{total:.3f},volume={bgm_volume:.3f},afade=t=in:d=0.6,afade=t=out:st={fade_out:.3f}:d=1.5[bgmraw]",
            # 有人聲時把背景音樂壓低（sidechain ducking），沒有人聲時恢復
            "[bgmraw][sc]sidechaincompress=threshold=0.02:ratio=6:attack=15:release=400[bgm]",
        ]
        mix.append("[bgm]")
    else:
        graph.append(f"[{voice_idx}:a]anull[vo]")
    if ambience is not None and ambience_volume > 0:
        inputs += ["-i", str(ambience)]
        amb_idx = voice_idx + (2 if "[bgm]" in mix else 1)
        graph.append(f"[{amb_idx}:a]volume={ambience_volume:.3f}[amb]")
        mix.append("[amb]")
    if len(mix) > 1:
        graph.append("".join(mix) + f"amix=inputs={len(mix)}:duration=first:normalize=0,alimiter=limit=0.95,atrim=end_sample={samples}[a]")
    else:
        graph.append(f"[vo]alimiter=limit=0.95,atrim=end_sample={samples}[a]")
    tmp = dest.with_suffix(".tmp.mp4")
    run(
        [
            *FFMPEG, *inputs,
            "-filter_complex", ";".join(graph), "-map", "[v]", "-map", "[a]",
            "-frames:v", str(total_frames),
            "-c:v", "libx264", "-preset", "veryfast", "-crf", "20", "-pix_fmt", "yuv420p",
            "-profile:v", "high", "-r", str(OUT_FPS),
            "-c:a", "aac", "-b:a", "192k", "-ar", str(AUDIO_RATE),
            "-movflags", "+faststart", str(tmp),
        ]
    )
    tmp.replace(dest)
