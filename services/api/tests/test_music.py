import base64
import json
import subprocess

import httpx
import pytest
import respx
from sqlalchemy import select

from app.models import MusicTrack, UsageLedger, Video
from tests.test_assets import TUS, samples, tus_patch  # noqa: F401（samples 是 fixture）
from tests.test_phase2 import KIE, add_kie, run_worker
from tests.test_videos import mock_tts, studio, voice_mp3  # noqa: F401（fixture）


@pytest.fixture(scope="session")
def song(tmp_path_factory) -> bytes:
    path = tmp_path_factory.mktemp("music") / "song.mp3"
    subprocess.run(
        ["ffmpeg", "-nostdin", "-loglevel", "error", "-y", "-f", "lavfi", "-i", "sine=frequency=220:duration=6", "-c:a", "libmp3lame", str(path)],
        check=True,
    )
    return path.read_bytes()


def _b64(text: str) -> str:
    return base64.b64encode(text.encode()).decode()


def upload_music(client, data: bytes, filename="Factory Beat.mp3"):
    r = client.post(
        "/api/uploads",
        headers={**TUS, "Upload-Length": str(len(data)), "Upload-Metadata": f"filename {_b64(filename)},purpose {_b64('music')}"},
    )
    if r.status_code != 201:
        return r
    return tus_patch(client, r.headers["location"], 0, data)


def test_upload_music_and_manage(admin, db, song):
    r = upload_music(admin, song)
    assert r.status_code == 204, r.text
    items = admin.get("/api/music").json()["data"]["items"]
    assert len(items) == 1
    track = items[0]
    assert track["title"] == "Factory Beat" and track["status"] == "ready" and 5.5 < track["duration"] < 6.5
    assert track["audio_url"].startswith("/media/") and "/music/" in track["audio_url"]
    assert admin.get("/api/media/auth", headers={"X-Forwarded-Uri": track["audio_url"]}).status_code == 200
    # 素材庫不會多出東西
    assert admin.get("/api/assets").json()["data"]["total"] == 0

    r = admin.patch(f"/api/music/{track['id']}", json={"title": "主打背景", "is_active": False})
    assert r.json()["data"]["title"] == "主打背景" and r.json()["data"]["is_active"] is False
    assert admin.delete(f"/api/music/{track['id']}").status_code == 200
    assert admin.get("/api/music").json()["data"]["items"] == []


def test_music_upload_validation(admin, client, song):
    assert upload_music(admin, song, "virus.exe").status_code == 415
    assert upload_music(admin, b"not audio at all" * 10, "fake.mp3").status_code == 400
    admin.post("/api/users", json={"email": "s@example.com", "display_name": "拍攝員", "password": "shooter-password", "role": "shooter"})
    admin.post("/api/auth/logout")
    client.post("/api/auth/login", json={"email": "s@example.com", "password": "shooter-password"})
    assert upload_music(client, song).status_code == 403


def test_generate_music_with_suno(admin, db, song, monkeypatch):
    monkeypatch.setattr("app.services.ai_provider.TTS_POLL_SECONDS", 0)
    assert admin.post("/api/music/generate", json={"preset": "corporate"}).json()["reason"] == "no_model"
    add_kie(admin)
    assert admin.post("/api/music/generate", json={"preset": "metal"}).status_code == 400
    r = admin.post("/api/music/generate", json={"preset": "industrial", "extra": "120 bpm", "title": "Steel Beat"})
    assert r.status_code == 200 and r.json()["data"]["status"] == "generating"

    with respx.mock:
        create = respx.post(f"{KIE}/api/v1/jobs/createTask").mock(
            return_value=httpx.Response(200, json={"code": 200, "data": {"taskId": "m1"}})
        )
        result = {"data": [{"audio_url": "https://cdn.example.com/1.mp3"}, {"audio_url": "https://cdn.example.com/2.mp3"}]}
        respx.get(f"{KIE}/api/v1/jobs/recordInfo").mock(
            return_value=httpx.Response(200, json={"code": 200, "data": {"state": "success", "creditsConsumed": 12, "resultJson": json.dumps(result)}})
        )
        respx.get(url__regex=r"https://cdn\.example\.com/\d\.mp3").mock(return_value=httpx.Response(200, content=song))
        assert run_worker(db) is True
    sent = json.loads(create.calls[0].request.content)
    assert sent["model"] == "ai-music-api/generate"
    assert sent["input"]["instrumental"] is True and sent["input"]["model"] == "V6_MINI"
    assert "industrial" in sent["input"]["style"] and "120 bpm" in sent["input"]["style"]

    tracks = admin.get("/api/music").json()["data"]["items"]
    assert sorted(t["title"] for t in tracks) == ["Steel Beat", "Steel Beat (2)"]
    assert all(t["status"] == "ready" and t["source"] == "ai" and t["duration"] for t in tracks)
    ledger = db.scalars(select(UsageLedger).where(UsageLedger.action == "ai.music")).one()
    assert ledger.status == "succeeded" and ledger.cost_micros == 60000


def test_render_with_background_music(admin, db, studio, voice_mp3, song):  # noqa: F811
    upload_music(admin, song, "Brand Theme.mp3")
    script = studio["script"]
    r = admin.post("/api/videos/generate", json={"script_ids": [script["id"]], "per_script": 1, "bgm": "auto", "bgm_volume": 0.3})
    video_id = r.json()["data"][0]["id"]
    with respx.mock:
        mock_tts(voice_mp3)
        run_worker(db)
    detail = admin.get(f"/api/videos/{video_id}").json()["data"]
    assert detail["status"] == "pending_review", detail
    assert detail["bgm_title"] == "Brand Theme"
    video = db.get(Video, video_id)
    assert video.timeline["bgm"]["volume"] == 0.3 and video.timeline["ambience"] == 0.0

    # 指定不用背景音樂
    r = admin.post("/api/videos/generate", json={"script_ids": [script["id"]], "bgm": "none"})
    with respx.mock:
        mock_tts(voice_mp3)
        run_worker(db)
    assert db.get(Video, r.json()["data"][0]["id"]).timeline["bgm"] is None
    # 指定不存在的音樂
    assert admin.post("/api/videos/generate", json={"script_ids": [script["id"]], "bgm": "x" * 36}).status_code == 404
    assert db.scalars(select(MusicTrack)).one().title == "Brand Theme"
