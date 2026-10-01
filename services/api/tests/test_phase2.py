import json
import os
from pathlib import Path

import httpx
import respx
from alembic import command
from alembic.config import Config
from sqlalchemy import select

from app.models import ChannelModel, Script, Task, UsageLedger
from app.services import media
from app.services.template_library import BUILTIN_TEMPLATES
from app.worker import Worker
from tests.conftest import API_DIR

DEEPSEEK = "https://api.deepseek.com/chat/completions"
KIE = "https://api.kie.ai"
LIAM = "TX3LPaxmHKxFdv7VOQHJ"


def create_profile(admin, **extra):
    body = {
        "name": "Acme Steel",
        "industry": "CNC machining",
        "audience": "US hardware brands",
        "selling_points": ["15 years", " ISO 9001 ", "15 years"],
        "target_language": "en",
        "call_to_action": "DM us for a quote",
        "hashtags": ["cnc", "#factory", "made in taiwan"],
        "banned_words": ["cheapest"],
        "voice_id": LIAM,
        **extra,
    }
    r = admin.post("/api/profiles", json=body)
    assert r.status_code == 200, r.text
    return r.json()["data"]


def builtin(admin, key="factory_tour"):
    name = next(t["name"] for t in BUILTIN_TEMPLATES if t["key"] == key)
    return next(t for t in admin.get("/api/templates").json()["data"]["items"] if t["name"] == name)


def variants_reply(count: int, shots: int, banned: bool = False) -> httpx.Response:
    variants = [
        {
            "title": f"Version {i}",
            "hook": f"Hook number {i}",
            "shots": [{"voiceover": f"Line {j} of v{i}" + (" cheapest" if banned and j == 0 else ""), "caption": f"Cap {j}"} for j in range(shots)],
            "post_caption": "Inside our CNC shop.",
            "hashtags": ["cnc", "#factory tour", "#cnc"],
        }
        for i in range(count)
    ]
    return httpx.Response(
        200,
        json={"choices": [{"message": {"content": json.dumps({"variants": variants})}}], "usage": {"prompt_tokens": 1500, "completion_tokens": 900}},
    )


def add_deepseek(admin):
    assert admin.post("/api/channels", json={"provider": "deepseek", "api_key": "sk-test-1234567890abcd"}).status_code == 200


def add_kie(admin):
    r = admin.post("/api/channels", json={"provider": "kie", "api_key": "kie-test-key"})
    assert r.status_code == 200, r.text
    return r.json()["data"]


def run_worker(db) -> bool:
    return Worker(1).run_one(db)


def mock_kie_tts(credits=12.0):
    respx.post(f"{KIE}/api/v1/jobs/createTask").mock(
        return_value=httpx.Response(200, json={"code": 200, "msg": "success", "data": {"taskId": "task_1"}})
    )
    states = iter([{"state": "generating"}, {"state": "success", "resultJson": json.dumps({"resultUrls": ["https://tempfile.aiquickdraw.com/a.mp3"]}), "creditsConsumed": credits}])
    respx.get(f"{KIE}/api/v1/jobs/recordInfo").mock(
        side_effect=lambda request: httpx.Response(200, json={"code": 200, "data": next(states)})
    )
    respx.get("https://tempfile.aiquickdraw.com/a.mp3").mock(return_value=httpx.Response(200, content=b"ID3fake-mp3"))


# ---------------------------------------------------------------- 帳號檔案
def test_profile_crud_and_validation(admin):
    profile = create_profile(admin)
    assert profile["selling_points"] == ["15 years", "ISO 9001"]
    assert profile["hashtags"] == ["#cnc", "#factory", "#madeintaiwan"]
    assert profile["voice_name"] == "Liam"

    r = admin.patch(f"/api/profiles/{profile['id']}", json={"target_language": "klingon"})
    assert r.status_code == 400
    assert admin.patch(f"/api/profiles/{profile['id']}", json={"voice_id": "nope"}).status_code == 400
    r = admin.patch(f"/api/profiles/{profile['id']}", json={"tone": " Friendly ", "voice_speed": 1.1})
    assert r.json()["data"]["tone"] == "Friendly" and r.json()["data"]["voice_speed"] == 1.1

    data = admin.get("/api/profiles").json()["data"]
    assert len(data["items"]) == 1 and "ja" in data["languages"]
    assert admin.post("/api/profiles", json={"name": "  "}).status_code == 400
    assert admin.delete(f"/api/profiles/{profile['id']}").status_code == 200


# ---------------------------------------------------------------- 模板
def test_builtin_templates_are_read_only_but_copyable(admin):
    items = admin.get("/api/templates").json()["data"]["items"]
    assert len([t for t in items if t["builtin"]]) == len(BUILTIN_TEMPLATES) >= 12
    tour = builtin(admin)
    assert admin.patch(f"/api/templates/{tour['id']}", json={"name": "x"}).status_code == 403
    assert admin.delete(f"/api/templates/{tour['id']}").status_code == 403

    copy = admin.post(f"/api/templates/{tour['id']}/copy").json()["data"]
    assert copy["builtin"] is False and copy["shots"] == tour["shots"]
    r = admin.patch(
        f"/api/templates/{copy['id']}",
        json={"name": "我的巡禮", "shots": [{"brief": "開場", "scene": "workshop", "seconds": 3}, {"brief": "結尾", "seconds": 2}]},
    )
    assert r.status_code == 200 and r.json()["data"]["total_seconds"] == 5
    bad = admin.patch(f"/api/templates/{copy['id']}", json={"shots": [{"brief": "x", "scene": "moon"}]})
    assert bad.status_code == 400
    assert admin.post("/api/templates", json={"name": "空"}).status_code == 400
    assert admin.delete(f"/api/templates/{copy['id']}").status_code == 200


# ---------------------------------------------------------------- 文案產生
def test_generate_requires_text_model(admin):
    profile = create_profile(admin)
    r = admin.post("/api/scripts/generate", json={"template_id": builtin(admin)["id"], "profile_id": profile["id"], "variants": 2})
    assert r.status_code == 400 and r.json()["reason"] == "no_model"
    assert "文字" in r.json()["msg"]


def test_generate_scripts_end_to_end(admin, db):
    add_deepseek(admin)
    profile = create_profile(admin)
    template = builtin(admin)
    r = admin.post("/api/scripts/generate", json={"template_id": template["id"], "profile_id": profile["id"], "variants": 3})
    assert r.status_code == 200, r.text
    created = r.json()["data"]
    assert [s["status"] for s in created] == ["generating"] * 3
    assert len({s["batch_id"] for s in created}) == 1

    with respx.mock:
        route = respx.post(DEEPSEEK).mock(return_value=variants_reply(3, len(template["shots"]), banned=True))
        assert run_worker(db) is True
    prompt = json.loads(route.calls[0].request.content)["messages"][1]["content"]
    assert "Acme Steel" in prompt and "DM us for a quote" in prompt and "max 8 words" in prompt

    listing = admin.get("/api/scripts", params={"template_id": template["id"]}).json()["data"]
    assert listing["total"] == 3
    scripts = sorted(listing["items"], key=lambda s: s["variant"])
    first = scripts[0]
    assert first["status"] == "draft" and first["title"] == "Version 0"
    assert first["shots"][0]["voiceover"].startswith("Line 0") and first["shots"][0]["brief"] == template["shots"][0]["brief"]
    assert first["hashtags"] == ["#cnc", "#factorytour"]
    assert "cheapest" in first["error"]
    ledger = db.scalars(select(UsageLedger).where(UsageLedger.source == "script_generate")).one()
    assert ledger.status == "succeeded" and ledger.cost_micros == 1500 * 0.30 + 900 * 1.20

    # 修改並核准
    shots = [{"voiceover": s["voiceover"].replace(" cheapest", ""), "caption": s["caption"]} for s in first["shots"]]
    r = admin.patch(f"/api/scripts/{first['id']}", json={"shots": shots, "status": "approved", "hashtags": ["new tag"]})
    assert r.status_code == 200, r.text
    assert r.json()["data"]["status"] == "approved" and r.json()["data"]["error"] == ""
    assert r.json()["data"]["hashtags"] == ["#newtag"]
    assert admin.patch(f"/api/scripts/{first['id']}", json={"shots": shots[:1]}).status_code == 400

    # 重新產生單一版本：會參考其他版本的開場避免重複
    assert admin.post(f"/api/scripts/{scripts[1]['id']}/regenerate").json()["data"]["status"] == "generating"
    assert admin.post(f"/api/scripts/{scripts[1]['id']}/regenerate").status_code == 409
    with respx.mock:
        route = respx.post(DEEPSEEK).mock(return_value=variants_reply(1, len(template["shots"])))
        run_worker(db)
    assert "Hook number 0" in json.loads(route.calls[0].request.content)["messages"][1]["content"]
    assert admin.get(f"/api/scripts/{scripts[1]['id']}").json()["data"]["status"] == "draft"

    assert admin.delete(f"/api/scripts/{scripts[2]['id']}").status_code == 200
    assert admin.get("/api/scripts", params={"status": "approved"}).json()["data"]["total"] == 1


def test_bad_ai_reply_retries_then_fails(admin, db):
    add_deepseek(admin)
    profile = create_profile(admin)
    admin.post("/api/scripts/generate", json={"template_id": builtin(admin)["id"], "profile_id": profile["id"], "variants": 1})
    bad = httpx.Response(200, json={"choices": [{"message": {"content": "Sorry, I can't"}}], "usage": {}})
    for attempt in range(3):
        with respx.mock:
            respx.post(DEEPSEEK).mock(return_value=bad)
            assert run_worker(db) is True
        task = db.scalars(select(Task)).one()
        db.refresh(task)
        if task.status == "queued":
            task.run_after = task.created_at  # 讓下一次立即重試
            db.commit()
    script = db.scalars(select(Script)).one()
    db.refresh(script)
    assert task.status == "failed" and script.status == "failed"
    assert "格式不正確" in script.error
    assert admin.patch(f"/api/scripts/{script.id}", json={"status": "approved"}).status_code == 409


# ---------------------------------------------------------------- 音色與配音
def test_voice_catalog(admin):
    voices = admin.get("/api/voices").json()["data"]
    liam = next(v for v in voices if v["id"] == LIAM)
    assert liam["recommended"] and liam["preview_url"].endswith(f"/{LIAM}.mp3")


def test_voice_preview_with_kie_tts(admin, db, monkeypatch):
    monkeypatch.setattr("app.services.ai_provider.TTS_POLL_SECONDS", 0)
    assert admin.post("/api/voices/preview", json={"voice_id": LIAM, "text": "Hello"}).json()["reason"] == "no_model"
    add_kie(admin)
    with respx.mock:
        mock_kie_tts(credits=12.0)
        r = admin.post("/api/voices/preview", json={"voice_id": LIAM, "text": "Hello from the factory", "speed": 1.1})
        sent = json.loads(respx.calls[0].request.content)
    assert r.status_code == 200, r.text
    assert sent["model"] == "elevenlabs/text-to-speech-multilingual-v2"
    assert sent["input"]["voice"] == LIAM and sent["input"]["speed"] == 1.1
    url = r.json()["data"]["audio_url"]
    assert r.json()["data"]["cost_usd"] == 0.06  # 12 點 × $0.005
    tenant = url.split("/")[2]
    assert Path(media.media_root(), tenant, "tts", url.rsplit("/", 1)[1]).read_bytes() == b"ID3fake-mp3"
    assert admin.get("/api/media/auth", headers={"X-Forwarded-Uri": url}).status_code == 200
    ledger = db.scalars(select(UsageLedger).where(UsageLedger.action == "ai.tts")).one()
    assert ledger.input_tokens == len("Hello from the factory") and ledger.cost_micros == 60000

    assert admin.post("/api/voices/preview", json={"voice_id": "nope", "text": "x"}).status_code == 400


def test_tts_failure_is_recorded(admin, db, monkeypatch):
    monkeypatch.setattr("app.services.ai_provider.TTS_POLL_SECONDS", 0)
    add_kie(admin)
    with respx.mock:
        respx.post(f"{KIE}/api/v1/jobs/createTask").mock(return_value=httpx.Response(200, json={"code": 402, "msg": "Insufficient Credits"}))
        r = admin.post("/api/voices/preview", json={"voice_id": LIAM, "text": "Hi"})
    assert r.status_code == 502 and "Insufficient Credits" in r.json()["msg"]
    assert db.scalars(select(UsageLedger)).one().status == "failed"


def test_channel_test_for_tts_model_returns_audio(admin, monkeypatch):
    monkeypatch.setattr("app.services.ai_provider.TTS_POLL_SECONDS", 0)
    channel = add_kie(admin)
    tts_model = next(m for m in channel["models"] if m["capability"] == "tts" and m["is_default"])
    with respx.mock:
        mock_kie_tts()
        r = admin.post(f"/api/channel-models/{tts_model['id']}/test", json={})
    assert r.status_code == 200, r.text
    assert r.json()["data"]["audio_url"].startswith("/media/")


def test_script_preview_audio_uses_profile_voice(admin, db, monkeypatch):
    monkeypatch.setattr("app.services.ai_provider.TTS_POLL_SECONDS", 0)
    add_deepseek(admin)
    add_kie(admin)
    profile = create_profile(admin, voice_id="hpp4J3VqNfWAUOO0d1Us", voice_speed=0.9)
    template = builtin(admin)
    admin.post("/api/scripts/generate", json={"template_id": template["id"], "profile_id": profile["id"], "variants": 1})
    with respx.mock:
        respx.post(DEEPSEEK).mock(return_value=variants_reply(1, len(template["shots"])))
        run_worker(db)
    script = admin.get("/api/scripts").json()["data"]["items"][0]
    with respx.mock:
        mock_kie_tts()
        r = admin.post(f"/api/scripts/{script['id']}/preview-audio")
        sent = json.loads(respx.calls[0].request.content)
    assert r.status_code == 200, r.text
    assert sent["input"]["voice"] == "hpp4J3VqNfWAUOO0d1Us" and sent["input"]["speed"] == 0.9
    assert sent["input"]["text"].startswith("Line 0 of v0 Line 1 of v0")


def test_migration_adds_tts_models_to_existing_kie_channel(admin, db):
    channel = add_kie(admin)
    db.query(ChannelModel).filter(ChannelModel.capability == "tts").delete()
    db.commit()
    cfg = Config(os.path.join(API_DIR, "alembic.ini"))
    cfg.set_main_option("script_location", os.path.join(API_DIR, "migrations"))
    command.downgrade(cfg, "0004")
    command.upgrade(cfg, "head")
    db.expire_all()
    models = db.scalars(
        select(ChannelModel).where(ChannelModel.channel_id == channel["id"], ChannelModel.capability == "tts").order_by(ChannelModel.created_at)
    ).all()
    assert [(m.model_key, m.is_default) for m in models] == [
        ("elevenlabs/text-to-speech-multilingual-v2", True),
        ("elevenlabs/text-to-speech-turbo-2-5", False),
    ]
