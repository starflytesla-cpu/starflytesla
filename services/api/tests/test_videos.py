import json
import subprocess
from pathlib import Path

import httpx
import pytest
import respx
from sqlalchemy import select

from app.models import Task, UsageLedger, Video
from app.services import media, renderer
from tests.test_assets import VISION_URL, add_vision_channel, samples, upload, vision_reply  # noqa: F401（samples 是 fixture）
from tests.test_phase2 import DEEPSEEK, KIE, add_deepseek, builtin, create_profile, run_worker, variants_reply


@pytest.fixture(scope="session")
def voice_mp3(tmp_path_factory) -> bytes:
    path = tmp_path_factory.mktemp("voice") / "v.mp3"
    subprocess.run(
        ["ffmpeg", "-nostdin", "-loglevel", "error", "-y", "-f", "lavfi", "-i", "sine=frequency=300:duration=1.2", "-c:a", "libmp3lame", str(path)],
        check=True,
    )
    return path.read_bytes()


def mock_tts(voice_mp3: bytes):
    """kie 配音：每次建立任務都立即完成，回傳同一段 1.2 秒音檔。"""
    create = respx.post(f"{KIE}/api/v1/jobs/createTask").mock(
        return_value=httpx.Response(200, json={"code": 200, "data": {"taskId": "t1"}})
    )
    respx.get(f"{KIE}/api/v1/jobs/recordInfo").mock(
        return_value=httpx.Response(
            200,
            json={"code": 200, "data": {"state": "success", "creditsConsumed": 3, "resultJson": json.dumps({"resultUrls": ["https://tempfile.aiquickdraw.com/v.mp3"]})}},
        )
    )
    respx.get("https://tempfile.aiquickdraw.com/v.mp3").mock(return_value=httpx.Response(200, content=voice_mp3))
    return create


@pytest.fixture
def studio(admin, db, samples, monkeypatch):
    """準備好素材（已分析）、模型渠道、帳號檔案與一份已核准文案。"""
    monkeypatch.setattr("app.services.ai_provider.TTS_POLL_SECONDS", 0)
    add_vision_channel(admin)  # 豆包看圖（也會建立 kie 以外的渠道）
    add_deepseek(admin)
    admin.post("/api/channels", json={"provider": "kie", "api_key": "kie-test-key"})
    # 讓 kie 的看圖模型不是預設，素材分析走豆包
    with respx.mock:
        respx.post(VISION_URL).mock(side_effect=[vision_reply("workshop"), vision_reply("product_closeup"), vision_reply("storefront")])
        upload(admin, samples["cut.mp4"])
        run_worker(db)
        upload(admin, samples["photo.jpg"], "store.jpg")
        run_worker(db)
    profile = create_profile(admin)
    template = builtin(admin, "product_closeup")
    admin.post("/api/scripts/generate", json={"template_id": template["id"], "profile_id": profile["id"], "variants": 1})
    with respx.mock:
        respx.post(DEEPSEEK).mock(return_value=variants_reply(1, len(template["shots"])))
        run_worker(db)
    script = admin.get("/api/scripts").json()["data"]["items"][0]
    assert admin.patch(f"/api/scripts/{script['id']}", json={"status": "approved"}).status_code == 200
    return {"script": script, "template": template}


def test_render_requires_approved_script_and_tts(admin, studio):
    script = studio["script"]
    admin.patch(f"/api/scripts/{script['id']}", json={"status": "draft"})
    r = admin.post("/api/videos/generate", json={"script_ids": [script["id"]]})
    assert r.status_code == 409 and r.json()["reason"] == "script_not_approved"
    assert admin.post("/api/videos/generate", json={"script_ids": ["x" * 36]}).status_code == 404


def test_render_end_to_end(admin, db, studio, voice_mp3):
    script = studio["script"]
    cov = admin.post("/api/videos/coverage", json={"script_ids": [script["id"]]}).json()["data"]
    assert cov["tts_ready"] and cov["total_clips"] == 3
    assert len(cov["scripts"][0]["shots"]) == len(studio["template"]["shots"])

    r = admin.post("/api/videos/generate", json={"script_ids": [script["id"]], "per_script": 2, "style": "random"})
    assert r.status_code == 200, r.text
    first, second = r.json()["data"]
    assert first["status"] == "queued"

    with respx.mock:
        create = mock_tts(voice_mp3)
        assert run_worker(db) is True
        calls_first = create.call_count
        assert run_worker(db) is True
        calls_second = create.call_count - calls_first
    shots = len(studio["template"]["shots"])
    # 每個鏡頭一段配音；第二支用同樣的文案與音色，全部重用快取
    assert calls_first == shots and calls_second == 0

    detail = admin.get(f"/api/videos/{first['id']}").json()["data"]
    assert detail["status"] == "pending_review", detail
    assert detail["video_url"].startswith(f"/media/") and detail["poster_url"]
    assert len(detail["shots"]) == shots
    # 配音（1.2 秒的音）去掉頭尾靜音後 + 停頓，再取整到影格
    expected = sum(max(1.2 + renderer.VOICE_PAD, renderer.MIN_SHOT) for _ in range(shots))
    assert abs(detail["duration"] - expected) < 0.3
    assert all(seg["thumb_url"] for shot in detail["shots"] for seg in shot["segments"])

    video = db.get(Video, first["id"])
    final = renderer.video_dir(video.tenant_id, video.id) / "final.mp4"
    info = media.probe(final, "video")
    assert (info.width, info.height) == (1080, 1920) and info.has_audio
    # 影像與聲音長度完全一致（不會越來越不同步）
    streams = json.loads(
        subprocess.run(
            ["ffprobe", "-v", "error", "-show_entries", "stream=codec_type,nb_frames,duration", "-of", "json", str(final)],
            capture_output=True, check=True,
        ).stdout
    )["streams"]
    v = next(x for x in streams if x["codec_type"] == "video")
    a = next(x for x in streams if x["codec_type"] == "audio")
    assert int(v["nb_frames"]) == round(detail["duration"] * 30)
    assert abs(float(a["duration"]) - float(v["duration"])) < 0.03
    assert all(seg.get("frames") for shot in db.get(Video, first["id"]).timeline["shots"] for seg in shot["segments"])
    assert not (final.parent / "work").exists()
    assert admin.get("/api/media/auth", headers={"X-Forwarded-Uri": detail["video_url"]}).status_code == 200

    ledger = db.scalars(select(UsageLedger).where(UsageLedger.action == "render.video")).all()
    assert len(ledger) == 2 and all(e.status == "succeeded" for e in ledger)
    tts = db.scalars(select(UsageLedger).where(UsageLedger.action == "ai.tts")).all()
    assert len(tts) == shots and all(e.source == "video_render" for e in tts)

    # 審核
    assert admin.post(f"/api/videos/{first['id']}/review", json={"action": "reject"}).status_code == 400
    r = admin.post(f"/api/videos/{first['id']}/review", json={"action": "reject", "note": "第二個鏡頭太暗"})
    assert r.json()["data"]["status"] == "rejected" and r.json()["data"]["review_note"] == "第二個鏡頭太暗"

    # 換素材 → 依時間軸重新渲染（不重新產生配音）
    cands = admin.get(f"/api/videos/{first['id']}/candidates", params={"shot": 1}).json()["data"]
    assert cands and all(c["thumb_url"] for c in cands)
    r = admin.post(f"/api/videos/{first['id']}/replace", json={"shot_index": 1, "clip_id": cands[0]["clip_id"]})
    assert r.json()["data"]["status"] == "queued"
    assert admin.post(f"/api/videos/{first['id']}/rerender", json={}).status_code == 409
    with respx.mock:
        create = mock_tts(voice_mp3)
        run_worker(db)
        assert create.call_count == 0
    detail = admin.get(f"/api/videos/{first['id']}").json()["data"]
    assert detail["status"] == "pending_review"
    assert detail["shots"][1]["segments"][0]["clip_id"] == cands[0]["clip_id"]

    # 重新挑素材
    admin.post(f"/api/videos/{first['id']}/rerender", json={"reshuffle": True})
    with respx.mock:
        mock_tts(voice_mp3)
        run_worker(db)
    assert admin.post(f"/api/videos/{first['id']}/review", json={"action": "approve"}).json()["data"]["status"] == "approved"

    stats = admin.get("/api/videos/stats").json()["data"]
    assert stats["approved"] == 1 and stats["pending_review"] == 1
    listing = admin.get("/api/videos", params={"status": "approved"}).json()["data"]
    assert listing["total"] == 1

    directory = renderer.video_dir(video.tenant_id, second["id"])
    assert admin.delete(f"/api/videos/{second['id']}").status_code == 200
    assert not directory.exists()


def test_render_without_tts_model_fails_fast(admin, db, samples):
    with respx.mock:
        respx.post(VISION_URL).mock(return_value=vision_reply("workshop"))
        add_vision_channel(admin)
        upload(admin, samples["photo.jpg"], "a.jpg")
        run_worker(db)
    assert admin.post("/api/videos/coverage", json={"script_ids": []}).json()["data"]["tts_ready"] is False


def test_render_failure_and_task_center_retry(admin, db, studio, voice_mp3):
    script = studio["script"]
    video_id = admin.post("/api/videos/generate", json={"script_ids": [script["id"]]}).json()["data"][0]["id"]
    with respx.mock:
        respx.post(f"{KIE}/api/v1/jobs/createTask").mock(return_value=httpx.Response(200, json={"code": 402, "msg": "Insufficient Credits"}))
        run_worker(db)  # 上游錯誤先自動重試一次
        assert admin.get(f"/api/videos/{video_id}").json()["data"]["stage"] == "稍後自動重試"
        task = db.scalars(select(Task).where(Task.type == "video.render")).one()
        db.refresh(task)
        task.run_after = task.created_at
        db.commit()
        run_worker(db)
    video = admin.get(f"/api/videos/{video_id}").json()["data"]
    assert video["status"] == "failed" and "Insufficient Credits" in video["error"]
    assert [e.status for e in db.scalars(select(UsageLedger).where(UsageLedger.action == "render.video"))] == ["failed", "failed"]

    tasks = admin.get("/api/tasks", params={"status": "failed"}).json()["data"]
    item = next(t for t in tasks["items"] if t["type"] == "video.render")
    assert item["type_label"] == "渲染成片" and item["label"] == video["title"]
    assert admin.post(f"/api/tasks/{item['id']}/retry").json()["data"]["status"] == "queued"
    assert admin.get(f"/api/videos/{video_id}").json()["data"]["status"] == "queued"
    assert admin.post(f"/api/tasks/{item['id']}/retry").status_code == 409
    with respx.mock:
        mock_tts(voice_mp3)
        run_worker(db)
    assert admin.get(f"/api/videos/{video_id}").json()["data"]["status"] == "pending_review"
    assert db.get(Task, item["id"]).status == "succeeded"


def _clip(cid, scene, length, quality="good", kind="video", dup=False):
    return {"clip_id": cid, "asset_id": "x", "kind": kind, "source": "s", "has_audio": False, "start": 0, "end": length,
            "length": length if kind == "video" else None, "scene": scene, "words": set(), "quality": quality, "duplicate": dup, "index": 0}


def test_choose_segments_prefers_scene_and_fills_exact_frames():
    import random
    from collections import Counter

    pool = [_clip("a", "packing", 2.0), _clip("b", "workshop", 1.0), _clip("c", "other", 9.0, "poor", dup=True)]
    used: set[str] = set()
    segs = renderer.choose_segments(pool, {"scene": "workshop"}, 75, used, Counter(), random.Random(1))
    assert segs[0]["clip_id"] == "b"
    assert sum(s["frames"] for s in segs) == 75
    assert used == {s["clip_id"] for s in segs}
    # 每段讀取的素材長度不超過素材本身（不會停格）
    assert all(s["src_duration"] <= next(c["length"] for c in pool if c["clip_id"] == s["clip_id"]) + 0.001 for s in segs)


def test_choose_segments_slows_down_slightly_short_clip_instead_of_freezing():
    import random
    from collections import Counter

    segs = renderer.choose_segments([_clip("a", "workshop", 1.8)], {"scene": "workshop"}, 60, set(), Counter(), random.Random(1))
    assert len(segs) == 1 and segs[0]["frames"] == 60 and segs[0]["src_duration"] == 1.8


def test_choose_segments_reuses_clips_when_pool_is_exhausted():
    import random
    from collections import Counter

    pool = [_clip("a", "workshop", 1.0), _clip("b", "workshop", 1.0)]
    used = {"a", "b"}  # 前面的鏡頭已經用過
    segs = renderer.choose_segments(pool, {"scene": "workshop"}, 60, used, Counter(), random.Random(2))
    assert sum(s["frames"] for s in segs) == 60
    assert {s["clip_id"] for s in segs} == {"a", "b"}


def test_subtitles_split_and_ass():
    assert renderer.split_subtitle("We machine every part here. Then we check it twice before shipping worldwide.", "en") == [
        "We machine every part here.",
        "Then we check it twice before",
        "shipping worldwide.",
    ]
    assert all(len(c) <= 20 for c in renderer.split_subtitle("我們的工廠每天生產一萬個零件，全部經過品質檢驗後出貨到世界各地。", "zh-TW"))
    assert renderer.split_subtitle("すべての部品は出荷前に検査されます。", "ja") == ["すべての部品は出荷前に検査されます。"]
    ass = renderer.build_ass(
        {"style": "box", "language": "ja", "shots": [{"duration": 2, "caption": "Hi {x}", "voiceover": "こんにちは", "voice_duration": 1.5}]}
    )
    assert "Noto Sans CJK JP" in ass and "Hi (x)" in ass and "0:00:02.00" in ass
