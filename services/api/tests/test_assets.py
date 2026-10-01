import base64
import json
import os
import subprocess
from datetime import timedelta
from pathlib import Path

import httpx
import pytest
import respx
from sqlalchemy import select

from app.models import Asset, Clip, Task, Upload, UsageLedger, utcnow
from app.services import asset_analyzer, media, tasks
from app.worker import Worker, cleanup

VISION_URL = "https://ark.ap-southeast.bytepluses.com/api/v3/chat/completions"
TUS = {"Tus-Resumable": "1.0.0"}


# ---------------------------------------------------------------- 測試素材
def _ffmpeg(*args: str) -> None:
    subprocess.run(["ffmpeg", "-nostdin", "-hide_banner", "-loglevel", "error", "-y", *args], check=True)


@pytest.fixture(scope="session")
def samples(tmp_path_factory) -> dict[str, bytes]:
    """兩個鏡頭（彩色測試畫面 → 彩條）的直式短片、同畫面但重新編碼的版本、一張照片。"""
    d = tmp_path_factory.mktemp("samples")
    src = [
        "-f", "lavfi", "-i", "testsrc2=size=360x640:rate=30:duration=2",
        "-f", "lavfi", "-i", "smptebars=size=360x640:rate=30:duration=2",
        "-f", "lavfi", "-i", "sine=frequency=440:duration=4",
        "-filter_complex", "[0:v][1:v]concat=n=2:v=1:a=0[v]", "-map", "[v]", "-map", "2:a",
        "-c:v", "libx264", "-preset", "ultrafast", "-c:a", "aac", "-shortest",
    ]
    _ffmpeg(*src, "-crf", "23", str(d / "cut.mp4"))
    _ffmpeg(*src, "-crf", "30", str(d / "cut2.mp4"))
    _ffmpeg("-f", "lavfi", "-i", "testsrc2=size=800x600", "-frames:v", "1", str(d / "photo.jpg"))
    return {name: (d / name).read_bytes() for name in ("cut.mp4", "cut2.mp4", "photo.jpg")}


def _b64(text: str) -> str:
    return base64.b64encode(text.encode()).decode()


def tus_create(client, size: int, filename: str):
    return client.post(
        "/api/uploads",
        headers={**TUS, "Upload-Length": str(size), "Upload-Metadata": f"filename {_b64(filename)},filetype {_b64('video/mp4')}"},
    )


def tus_patch(client, location: str, offset: int, data: bytes):
    return client.patch(
        location,
        content=data,
        headers={**TUS, "Upload-Offset": str(offset), "Content-Type": "application/offset+octet-stream"},
    )


def upload(client, data: bytes, filename: str = "工廠.mp4", chunk: int = 64 * 1024) -> str:
    r = tus_create(client, len(data), filename)
    assert r.status_code == 201, r.text
    location = r.headers["location"]
    offset = 0
    while offset < len(data):
        r = tus_patch(client, location, offset, data[offset : offset + chunk])
        assert r.status_code == 204, r.text
        offset = int(r.headers["upload-offset"])
    return r.headers["starfly-asset-id"]


def add_vision_channel(admin):
    r = admin.post("/api/channels", json={"provider": "byteplus", "api_key": "test-vision-key"})
    assert r.status_code == 200, r.text
    model = r.json()["data"]["models"][0]
    admin.patch(f"/api/channel-models/{model['id']}", json={"input_price_per_m": 0.1, "output_price_per_m": 0.4})


def vision_reply(scene: str, quality: str = "good") -> httpx.Response:
    content = json.dumps(
        {"scene": scene, "subjects": ["機台"], "tags": ["金屬", "加工", "金屬"], "description": "車床加工零件", "quality": quality},
        ensure_ascii=False,
    )
    return httpx.Response(
        200,
        json={"choices": [{"message": {"content": f"```json\n{content}\n```"}}], "usage": {"prompt_tokens": 900, "completion_tokens": 60}},
    )


def run_worker(db) -> bool:
    return Worker(1).run_one(db)


def create_shooter(admin, email="shooter@example.com"):
    r = admin.post(
        "/api/users",
        json={"email": email, "display_name": "拍攝員", "password": "shooter-password", "role": "shooter"},
    )
    assert r.status_code == 200, r.text


# ---------------------------------------------------------------- tus 上傳
def test_upload_requires_login(client):
    assert tus_create(client, 10, "a.mp4").status_code == 401


def test_options_advertises_tus(admin):
    r = admin.options("/api/uploads")
    assert r.status_code == 204
    assert r.headers["tus-version"] == "1.0.0"
    assert "creation" in r.headers["tus-extension"]


def test_rejects_unsupported_type_and_oversize(admin):
    r = tus_create(admin, 10, "malware.exe")
    assert r.status_code == 415
    assert r.json()["reason"] == "unsupported_type"
    r = tus_create(admin, 3 * 1024**3, "big.mp4")
    assert r.status_code == 413


def test_resumable_upload_flow(admin, db, samples):
    data = samples["cut.mp4"]
    r = tus_create(admin, len(data), "../../etc/車間.MP4")
    location = r.headers["location"]
    assert location.startswith("/api/uploads/")

    # 傳一半後「斷線」，用 HEAD 查進度再續傳
    half = len(data) // 2
    assert tus_patch(admin, location, 0, data[:half]).status_code == 204
    head = admin.head(location, headers=TUS)
    assert head.headers["upload-offset"] == str(half)
    assert head.headers["upload-length"] == str(len(data))
    assert head.headers["cache-control"] == "no-store"

    # 進度不一致會被拒絕
    assert tus_patch(admin, location, 0, data).status_code == 409

    r = tus_patch(admin, location, half, data[half:])
    assert r.status_code == 204
    asset_id = r.headers["starfly-asset-id"]

    asset = db.get(Asset, asset_id)
    assert asset.status == "uploaded"
    assert asset.original_filename == "車間.MP4"
    assert asset.kind == "video"
    original = Path(media.media_root(), asset.storage_key)
    assert original.read_bytes() == data
    assert original.name == "original.mp4"
    assert not list(media.uploads_dir().glob("*.part"))
    task = db.scalars(select(Task)).one()
    assert task.type == "asset.analyze" and task.payload == {"asset_id": asset_id}

    # 已完成的上傳不能再寫入
    assert tus_patch(admin, location, len(data), b"x").status_code == 409


def test_upload_rejects_extra_bytes(admin):
    location = tus_create(admin, 4, "a.mp4").headers["location"]
    assert tus_patch(admin, location, 0, b"123456").status_code == 400
    assert admin.head(location, headers=TUS).headers["upload-offset"] == "0"


def test_other_users_cannot_touch_upload(admin, client):
    location = tus_create(admin, 100, "a.mp4").headers["location"]
    create_shooter(admin)
    admin.post("/api/auth/logout")
    client.post("/api/auth/login", json={"email": "shooter@example.com", "password": "shooter-password"})
    assert client.head(location, headers=TUS).status_code == 404
    assert tus_patch(client, location, 0, b"x").status_code == 404


def test_terminate_upload(admin, db):
    location = tus_create(admin, 100, "a.mp4").headers["location"]
    assert tus_patch(admin, location, 0, b"x" * 10).status_code == 204
    assert admin.delete(location, headers=TUS).status_code == 204
    assert db.scalars(select(Upload)).all() == []
    assert not list(media.uploads_dir().glob("*.part"))


def test_cleanup_removes_abandoned_uploads(admin, db):
    location = tus_create(admin, 100, "a.mp4").headers["location"]
    upload_row = db.scalars(select(Upload)).one()
    upload_row.updated_at = utcnow() - timedelta(days=4)
    db.commit()
    cleanup(db)
    assert db.scalars(select(Upload)).all() == []
    assert admin.head(location, headers=TUS).status_code == 404


# ---------------------------------------------------------------- 分析流程
def test_analyze_video_with_vision(admin, db, samples):
    add_vision_channel(admin)
    asset_id = upload(admin, samples["cut.mp4"])
    replies = iter([vision_reply("workshop"), vision_reply("product_closeup", "ok")])
    with respx.mock:
        route = respx.post(VISION_URL).mock(side_effect=lambda request: next(replies))
        assert run_worker(db) is True
    assert route.call_count == 2
    sent = json.loads(route.calls[0].request.content)
    assert sent["messages"][1]["content"][1]["image_url"]["url"].startswith("data:image/jpeg;base64,")

    data = admin.get(f"/api/assets/{asset_id}").json()["data"]
    assert data["status"] == "ready", data
    assert data["stage"] == ""
    assert data["width"] == 360 and data["height"] == 640
    assert 3.9 < data["duration"] < 4.2
    assert data["has_audio"] is True
    assert [c["scene"] for c in data["clips"]] == ["workshop", "product_closeup"]
    first = data["clips"][0]
    assert first["tags"] == ["金屬", "加工"]
    assert first["quality"] == "good" and first["tagged_by"] == "ai"
    assert 1.8 < data["clips"][1]["start"] < 2.3
    assert data["category"] in ("workshop", "product_closeup")
    assert data["proxy_url"].startswith(f"/media/{db.get(Asset, asset_id).tenant_id}/assets/{asset_id}/proxy.mp4?v=")

    directory = Path(media.media_root(), db.get(Asset, asset_id).storage_key).parent
    assert (directory / "proxy.mp4").stat().st_size > 0
    assert (directory / "poster.jpg").exists()
    assert sorted(p.name for p in (directory / "clips").iterdir()) == ["000.jpg", "001.jpg"]

    ledger = db.scalars(select(UsageLedger).where(UsageLedger.source == "asset_analyze")).all()
    assert len(ledger) == 2 and all(e.status == "succeeded" for e in ledger)
    assert ledger[0].cost_micros == 900 * 0.1 + 60 * 0.4
    assert db.scalars(select(Task)).one().status == "succeeded"
    assert run_worker(db) is False


def test_analyze_without_vision_model_still_ready(admin, db, samples):
    asset_id = upload(admin, samples["cut.mp4"])
    run_worker(db)
    data = admin.get(f"/api/assets/{asset_id}").json()["data"]
    assert data["status"] == "ready"
    assert "尚未設定看圖模型" in data["stage"]
    assert len(data["clips"]) == 2
    assert all(c["scene"] == "" for c in data["clips"])


def test_vision_failures_are_recorded_but_asset_is_ready(admin, db, samples):
    add_vision_channel(admin)
    asset_id = upload(admin, samples["cut.mp4"])
    with respx.mock:
        respx.post(VISION_URL).mock(return_value=httpx.Response(500, json={"error": {"message": "boom"}}))
        run_worker(db)
    data = admin.get(f"/api/assets/{asset_id}").json()["data"]
    assert data["status"] == "ready"
    assert "2 個鏡頭 AI 標註失敗" in data["stage"]
    failed = db.scalars(select(UsageLedger).where(UsageLedger.status == "failed")).all()
    assert len(failed) == 2


def test_analyze_photo(admin, db, samples):
    asset_id = upload(admin, samples["photo.jpg"], "門店.jpg")
    run_worker(db)
    data = admin.get(f"/api/assets/{asset_id}").json()["data"]
    assert data["status"] == "ready", data
    assert data["kind"] == "image"
    assert (data["width"], data["height"]) == (800, 600)
    assert data["proxy_url"] is None and data["poster_url"]
    assert len(data["clips"]) == 1


def test_identical_file_is_marked_duplicate(admin, db, samples):
    first = upload(admin, samples["cut.mp4"])
    run_worker(db)
    second = upload(admin, samples["cut.mp4"], "again.mp4")
    run_worker(db)
    data = admin.get(f"/api/assets/{second}").json()["data"]
    assert data["status"] == "duplicate"
    assert data["duplicate_of"] == first
    assert data["duplicate_of_filename"] == "工廠.mp4"
    assert data["original_url"] is None
    assert not media.asset_dir(db.get(Asset, second).tenant_id, second).exists()


def test_near_duplicate_clips_are_flagged(admin, db, samples):
    first = upload(admin, samples["cut.mp4"])
    run_worker(db)
    second = upload(admin, samples["cut2.mp4"], "重新匯出.mp4")
    run_worker(db)
    data = admin.get(f"/api/assets/{second}").json()["data"]
    assert data["status"] == "ready"
    dups = [c["duplicate_of"] for c in data["clips"]]
    assert all(d and d["asset_id"] == first for d in dups), dups
    assert [d["index"] for d in dups] == [0, 1]
    # 先上傳的素材不會反過來被標成重複
    assert all(c["duplicate_of"] is None for c in admin.get(f"/api/assets/{first}").json()["data"]["clips"])


def test_corrupt_file_fails_without_retry(admin, db):
    asset_id = upload(admin, os.urandom(4096), "broken.mp4")
    run_worker(db)
    data = admin.get(f"/api/assets/{asset_id}").json()["data"]
    assert data["status"] == "failed"
    assert data["error"]
    task = db.scalars(select(Task)).one()
    assert task.status == "failed" and task.attempts == 1


def test_interrupted_task_is_released(admin, db, samples, monkeypatch):
    asset_id = upload(admin, samples["cut.mp4"])

    def interrupted(*_args, **_kwargs):
        raise media.Interrupted()

    monkeypatch.setattr(media, "make_proxy", interrupted)
    run_worker(db)
    task = db.scalars(select(Task)).one()
    db.refresh(task)
    assert task.status == "queued" and task.attempts == 0
    assert db.get(Asset, asset_id).status == "uploaded"


# ---------------------------------------------------------------- 素材庫 API
def test_asset_library_api(admin, db, samples):
    asset_id = upload(admin, samples["cut.mp4"])
    run_worker(db)

    listing = admin.get("/api/assets").json()["data"]
    assert listing["total"] == 1
    item = listing["items"][0]
    assert item["clip_count"] == 2 and item["uploaded_by_name"]
    assert admin.get("/api/assets", params={"status": "failed"}).json()["data"]["total"] == 0
    assert admin.get("/api/assets", params={"q": "工廠"}).json()["data"]["total"] == 1
    assert admin.get("/api/assets", params={"q": "%"}).json()["data"]["total"] == 0

    stats = admin.get("/api/assets/stats").json()["data"]
    assert stats["total"] == 1 and stats["by_status"]["ready"] == 1 and stats["clips"] == 2

    r = admin.patch(f"/api/assets/{asset_id}", json={"category": "packing", "note": " 出貨區 "})
    assert r.json()["data"]["category"] == "packing" and r.json()["data"]["note"] == "出貨區"
    assert admin.patch(f"/api/assets/{asset_id}", json={"category": "nope"}).status_code == 400

    clips = r.json()["data"]["clips"]
    r = admin.patch(
        f"/api/clips/{clips[0]['id']}",
        json={"scene": "warehouse", "tags": ["棧板"], "description": "倉庫", "quality": "poor"},
    )
    assert r.status_code == 200, r.text
    edited = r.json()["data"]["clips"][0]
    assert edited["tagged_by"] == "manual" and edited["tags"] == ["棧板"]
    assert r.json()["data"]["category"] == "warehouse"
    r = admin.patch(f"/api/clips/{clips[1]['id']}", json={"is_disabled": True})
    assert r.json()["data"]["clips"][1]["is_disabled"] is True
    assert r.json()["data"]["clips"][1]["tagged_by"] == ""

    r = admin.post(f"/api/assets/{asset_id}/reanalyze")
    assert r.json()["data"]["status"] == "uploaded"
    assert admin.post(f"/api/assets/{asset_id}/reanalyze").status_code == 409
    run_worker(db)
    assert admin.get(f"/api/assets/{asset_id}").json()["data"]["status"] == "ready"

    directory = Path(media.media_root(), db.get(Asset, asset_id).storage_key).parent
    assert admin.delete(f"/api/assets/{asset_id}").status_code == 200
    assert not directory.exists()
    assert db.scalars(select(Clip)).all() == []
    assert admin.get(f"/api/assets/{asset_id}").status_code == 404


def test_shooter_permissions(admin, client, db, samples):
    admin_asset = upload(admin, samples["photo.jpg"], "a.jpg")
    create_shooter(admin)
    admin.post("/api/auth/logout")
    client.post("/api/auth/login", json={"email": "shooter@example.com", "password": "shooter-password"})

    own = upload(client, samples["cut.mp4"], "mine.mp4")
    assert client.get("/api/assets").json()["data"]["total"] == 2
    assert client.get("/api/assets", params={"mine": True}).json()["data"]["total"] == 1
    assert client.patch(f"/api/assets/{own}", json={"note": "x"}).status_code == 403
    assert client.post(f"/api/assets/{own}/reanalyze").status_code == 403
    assert client.delete(f"/api/assets/{admin_asset}").status_code == 403
    assert client.delete(f"/api/assets/{own}").status_code == 200


# ---------------------------------------------------------------- 素材檔案權限
def test_media_auth(admin, db, samples):
    asset_id = upload(admin, samples["photo.jpg"], "a.jpg")
    tenant = db.get(Asset, asset_id).tenant_id
    ok_uri = f"/media/{tenant}/assets/{asset_id}/poster.jpg?v=1"

    def check(uri, client=admin):
        return client.get("/api/media/auth", headers={"X-Forwarded-Uri": uri}).status_code

    assert check(ok_uri) == 200
    assert check(f"/media/{tenant}/assets/{asset_id}/clips/000.jpg") == 200
    other = "00000000-0000-0000-0000-000000000000"
    assert check(f"/media/{other}/assets/{asset_id}/poster.jpg") == 403
    assert check(f"/media/{tenant}/assets/{asset_id}/../../../{other}/assets/x/poster.jpg") == 403
    assert check(f"/media/{tenant}/assets/{asset_id}/%2e%2e/poster.jpg") == 403
    assert check("/media/_uploads/x.part") == 403
    assert check("") == 403
    admin.post("/api/auth/logout")
    assert check(ok_uri) == 401


# ---------------------------------------------------------------- 任務佇列與工具函式
def test_task_lease_and_retry(db):
    task = tasks.enqueue(db, "noop", {})
    db.commit()
    claimed = tasks.claim(db, "w1")
    assert claimed.id == task.id and claimed.attempts == 1
    assert tasks.claim(db, "w2") is None

    # worker 當機：租約過期後會被其他 worker 領取
    claimed.lease_expires_at = utcnow() - timedelta(seconds=1)
    db.commit()
    again = tasks.claim(db, "w2")
    assert again.id == task.id and again.attempts == 2 and again.locked_by == "w2"

    assert tasks.fail(db, again, "boom") is True
    assert again.status == "queued" and again.run_after > utcnow()
    again.run_after = utcnow()
    db.commit()
    third = tasks.claim(db, "w3")
    assert tasks.fail(db, third, "boom") is False
    assert third.status == "failed"


def test_unknown_task_type_fails(db):
    tasks.enqueue(db, "mystery", {})
    db.commit()
    assert run_worker(db) is True
    assert db.scalars(select(Task)).one().status == "failed"


def test_build_segments():
    assert media.build_segments([], 4.0) == [(0.0, 4.0)]
    assert media.build_segments([2.0], 4.0) == [(0.0, 2.0), (2.0, 4.0)]
    # 太短的鏡頭併入前一段
    assert media.build_segments([0.3, 2.0, 2.4], 4.0) == [(0.0, 2.4), (2.4, 4.0)]
    # 太長的鏡頭平均切開
    assert media.build_segments([], 40.0) == [(0.0, 13.333), (13.333, 26.667), (26.667, 40.0)]


def test_parse_tags():
    tags = asset_analyzer.parse_tags('好的：{"scene":"alien","subjects":"機台，工人","tags":["a","a",""],"quality":"GOOD"}')
    assert tags["scene"] == "other"
    assert tags["subjects"] == ["機台", "工人"]
    assert tags["tags"] == ["a"]
    assert tags["quality"] == "good"
    with pytest.raises(ValueError):
        asset_analyzer.parse_tags("沒有 JSON")
