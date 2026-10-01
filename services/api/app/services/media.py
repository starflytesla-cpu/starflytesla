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
