import json
import os

import httpx
import pytest
import respx
from alembic import command
from alembic.config import Config
from sqlalchemy import select

from app.errors import AppError
from app.models import ChannelModel, ModelChannel, UsageLedger
from app.services import ai_provider
from tests.conftest import API_DIR

KIE_CHAT = "https://api.kie.ai/gemini-3-8-flash-openai/v1/chat/completions"
KIE_UPLOAD = "https://kieai.redpandaai.co/api/file-base64-upload"


def create_kie(admin):
    r = admin.post("/api/channels", json={"provider": "kie", "api_key": "kie-test-key-4af1"})
    assert r.status_code == 200, r.text
    return r.json()["data"]


def test_kie_preset_has_gemini_vision_model(admin):
    channel = create_kie(admin)
    model = channel["models"][0]
    assert model["model_key"] == "gemini-3-8-flash-openai"
    assert model["capability"] == "vision" and model["is_default"] is True
    assert "vision" in admin.get("/api/dashboard").json()["data"]["ready_capabilities"]


def test_kie_image_is_uploaded_and_model_path_used(admin, db):
    create_kie(admin)
    model = ai_provider.default_model(db, db.scalars(select(ModelChannel)).one().tenant_id, "vision")
    messages = [
        {"role": "system", "content": "只回 JSON"},
        {"role": "user", "content": [{"type": "text", "text": "看圖"}, {"type": "image_url", "image_url": {"url": "data:image/jpeg;base64,AAAA"}}]},
    ]
    with respx.mock:
        upload = respx.post(KIE_UPLOAD).mock(
            return_value=httpx.Response(200, json={"success": True, "code": 200, "data": {"downloadUrl": "https://tempfile.redpandaai.co/x/k.jpg"}})
        )
        chat = respx.post(KIE_CHAT).mock(
            return_value=httpx.Response(200, json={"choices": [{"message": {"content": '{"scene":"workshop"}'}}], "usage": {"prompt_tokens": 300, "completion_tokens": 40}})
        )
        result = ai_provider.chat(db, model, messages, source="asset_analyze", user=None)

    assert result.content == '{"scene":"workshop"}'
    assert json.loads(upload.calls[0].request.content)["base64Data"] == "data:image/jpeg;base64,AAAA"
    assert upload.calls[0].request.headers["authorization"] == "Bearer kie-test-key-4af1"
    sent = json.loads(chat.calls[0].request.content)
    assert sent["stream"] is False
    assert "max_tokens" not in sent
    assert sent["messages"][1]["content"][1]["image_url"]["url"] == "https://tempfile.redpandaai.co/x/k.jpg"
    assert sent["messages"][0] == messages[0]


def test_kie_gemini_native_response_and_errors(admin, db):
    create_kie(admin)
    model = db.scalars(select(ChannelModel)).one()
    text_only = [{"role": "user", "content": "hi"}]
    native = {
        "candidates": [{"content": {"parts": [{"text": "思考中", "thought": True}, {"text": "你好"}]}}],
        "usageMetadata": {"promptTokenCount": 10, "candidatesTokenCount": 5, "thoughtsTokenCount": 20},
    }
    with respx.mock:
        respx.post(KIE_CHAT).mock(return_value=httpx.Response(200, json=native))
        result = ai_provider.chat(db, model, text_only, source="channel_test", user=None)
    assert result.content == "你好"
    assert (result.input_tokens, result.output_tokens) == (10, 25)

    # kie 出錯時可能回 HTTP 200，錯誤放在 code / msg
    with respx.mock:
        respx.post(KIE_CHAT).mock(return_value=httpx.Response(200, json={"code": 402, "msg": "Insufficient Credits"}))
        with pytest.raises(AppError, match="Insufficient Credits"):
            ai_provider.chat(db, model, text_only, source="channel_test", user=None)
    failed = db.scalars(select(UsageLedger).where(UsageLedger.status == "failed")).one()
    assert "402" in failed.error


def test_openai_compatible_requests_disable_streaming(admin, db):
    admin.post("/api/channels", json={"provider": "deepseek", "api_key": "sk-test-1234567890abcd"})
    model = ai_provider.default_model(db, db.scalars(select(ModelChannel)).one().tenant_id, "text")
    with respx.mock:
        route = respx.post("https://api.deepseek.com/chat/completions").mock(
            return_value=httpx.Response(200, json={"choices": [{"message": {"content": "ok"}}], "usage": {}})
        )
        ai_provider.chat(db, model, [{"role": "user", "content": "hi"}], source="channel_test", user=None, max_tokens=50)
    sent = json.loads(route.calls[0].request.content)
    assert sent["stream"] is False and sent["max_tokens"] == 50 and sent["model"] == "deepseek-flash"


def test_migration_adds_gemini_to_existing_kie_channel(admin, db):
    channel = create_kie(admin)
    # 模擬舊版建立的 kie 渠道：沒有任何模型
    db.query(ChannelModel).delete()
    db.commit()
    cfg = Config(os.path.join(API_DIR, "alembic.ini"))
    cfg.set_main_option("script_location", os.path.join(API_DIR, "migrations"))
    command.downgrade(cfg, "0002")
    command.upgrade(cfg, "head")
    db.expire_all()
    models = db.scalars(select(ChannelModel).where(ChannelModel.channel_id == channel["id"])).all()
    assert [(m.model_key, m.capability, m.is_default) for m in models] == [("gemini-3-8-flash-openai", "vision", True)]
    # 再跑一次不會重複新增
    command.downgrade(cfg, "0002")
    command.upgrade(cfg, "head")
    assert len(db.scalars(select(ChannelModel)).all()) == 1
