import httpx
import respx
from sqlalchemy import select

from app.models import ModelChannel, UsageLedger
from app.security import decrypt_secret

DEEPSEEK_URL = "https://api.deepseek.com/chat/completions"


def create_deepseek(admin, api_key="sk-test-1234567890abcd"):
    r = admin.post("/api/channels", json={"provider": "deepseek", "api_key": api_key})
    assert r.status_code == 200, r.text
    return r.json()["data"]


def text_model(channel, key="deepseek-flash"):
    return next(m for m in channel["models"] if m["model_key"] == key)


def test_presets_are_listed(admin):
    data = admin.get("/api/channel-presets").json()["data"]
    providers = {p["provider"] for p in data["presets"]}
    assert {"deepseek", "byteplus", "openrouter", "kie", "custom"} <= providers
    assert "vision" in data["capabilities"]


def test_api_key_is_encrypted_and_never_returned(admin, db):
    channel = create_deepseek(admin)
    assert channel["has_api_key"] is True
    assert channel["api_key_last4"] == "abcd"
    assert "sk-test" not in str(admin.get("/api/channels").json())

    stored = db.get(ModelChannel, channel["id"])
    assert stored.api_key_encrypted and "sk-test" not in stored.api_key_encrypted
    assert decrypt_secret(stored.api_key_encrypted) == "sk-test-1234567890abcd"


def test_preset_models_are_created_with_one_default(admin):
    channel = create_deepseek(admin)
    models = {m["model_key"]: m for m in channel["models"]}
    assert models["deepseek-flash"]["is_default"] is True
    assert models["deepseek-v4-pro"]["is_default"] is False
    assert models["deepseek-flash"]["input_price_per_m"] == 0.30


def test_second_preset_channel_does_not_steal_default(admin):
    first = create_deepseek(admin)
    second = create_deepseek(admin)
    assert text_model(first)["is_default"] is True
    assert text_model(second)["is_default"] is False


def test_setting_default_clears_previous_default(admin):
    channel = create_deepseek(admin)
    pro = text_model(channel, "deepseek-v4-pro")
    r = admin.patch(f"/api/channel-models/{pro['id']}", json={"is_default": True})
    assert r.json()["data"]["is_default"] is True
    models = {m["model_key"]: m for m in admin.get("/api/channels").json()["data"][0]["models"]}
    assert models["deepseek-flash"]["is_default"] is False


def test_private_upstream_is_rejected(admin, fake_dns):
    r = admin.post(
        "/api/channels",
        json={"provider": "custom", "base_url": "https://127.0.0.1:8080/v1", "api_key": "x"},
    )
    assert r.status_code == 400
    assert r.json()["reason"] == "private_upstream"

    fake_dns["ip"] = "10.0.0.5"  # 網域解析到內網也要擋
    r = admin.post(
        "/api/channels",
        json={"provider": "custom", "base_url": "https://internal.example.com/v1", "api_key": "x"},
    )
    assert r.json()["reason"] == "private_upstream"


def test_plain_http_upstream_is_rejected(admin):
    r = admin.post(
        "/api/channels",
        json={"provider": "custom", "base_url": "http://api.example.com/v1", "api_key": "x"},
    )
    assert r.status_code == 400
    assert r.json()["reason"] == "invalid_upstream"


def test_add_custom_model_and_duplicate_is_rejected(admin):
    channel = create_deepseek(admin)
    body = {"model_key": "my-model", "capability": "text", "input_price_per_m": 1, "output_price_per_m": 2}
    r = admin.post(f"/api/channels/{channel['id']}/models", json=body)
    assert r.status_code == 200
    assert admin.post(f"/api/channels/{channel['id']}/models", json=body).status_code == 409


@respx.mock
def test_model_test_calls_upstream_and_records_cost(admin, db):
    route = respx.post(DEEPSEEK_URL).mock(
        return_value=httpx.Response(
            200,
            json={
                "choices": [{"message": {"role": "assistant", "content": "你好，我是測試模型。"}}],
                "usage": {"prompt_tokens": 1000, "completion_tokens": 500},
            },
        )
    )
    channel = create_deepseek(admin)
    r = admin.post(f"/api/channel-models/{text_model(channel)['id']}/test", json={})
    assert r.status_code == 200, r.text
    data = r.json()["data"]
    assert data["reply"] == "你好，我是測試模型。"
    # 1000 × 0.30 + 500 × 1.20 = 900 百萬分之一美元
    assert data["cost_usd"] == 0.0009

    sent = route.calls.last.request
    assert sent.headers["authorization"] == "Bearer sk-test-1234567890abcd"

    entry = db.scalars(select(UsageLedger)).one()
    assert entry.status == "succeeded"
    assert (entry.input_tokens, entry.output_tokens, entry.cost_micros) == (1000, 500, 900)
    assert entry.source == "channel_test"

    usage = admin.get("/api/usage").json()["data"]
    assert usage["total"] == 1
    assert usage["items"][0]["channel_name"] == "DeepSeek"
    summary = admin.get("/api/usage/summary").json()["data"]
    assert summary["month"]["calls"] == 1
    assert summary["by_model"][0]["cost_usd"] == 0.0009


@respx.mock
def test_upstream_failure_is_reported_and_recorded(admin, db):
    respx.post(DEEPSEEK_URL).mock(
        return_value=httpx.Response(401, json={"error": {"message": "Authentication Fails"}})
    )
    channel = create_deepseek(admin)
    r = admin.post(f"/api/channel-models/{text_model(channel)['id']}/test", json={})
    assert r.status_code == 502
    body = r.json()
    assert body["reason"] == "upstream_error"
    assert "HTTP 401" in body["msg"] and "Authentication Fails" in body["msg"]

    entry = db.scalars(select(UsageLedger)).one()
    assert entry.status == "failed"
    assert "HTTP 401" in entry.error
    assert entry.cost_micros == 0
    month = admin.get("/api/usage/summary").json()["data"]["month"]
    assert (month["failed"], month["unpriced"]) == (1, 0)


@respx.mock
def test_unknown_price_records_null_cost(admin, db):
    respx.post("https://ark.ap-southeast.bytepluses.com/api/v3/chat/completions").mock(
        return_value=httpx.Response(
            200,
            json={"choices": [{"message": {"content": "ok"}}], "usage": {"prompt_tokens": 10, "completion_tokens": 2}},
        )
    )
    r = admin.post("/api/channels", json={"provider": "byteplus", "api_key": "ark-key"})
    model = r.json()["data"]["models"][0]
    assert model["capability"] == "vision"
    r = admin.post(f"/api/channel-models/{model['id']}/test", json={"prompt": "hi"})
    assert r.status_code == 200, r.text
    assert r.json()["data"]["cost_usd"] is None
    assert admin.get("/api/usage/summary").json()["data"]["month"]["unpriced"] == 1


def test_missing_api_key_is_reported_without_calling_upstream(admin):
    r = admin.post("/api/channels", json={"provider": "deepseek", "api_key": ""})
    model = text_model(r.json()["data"])
    r = admin.post(f"/api/channel-models/{model['id']}/test", json={})
    assert r.status_code == 400
    assert r.json()["reason"] == "missing_api_key"


def test_dashboard_reports_ready_capabilities(admin):
    create_deepseek(admin)
    data = admin.get("/api/dashboard").json()["data"]
    assert data["ready_capabilities"] == ["text"]
    assert data["channels"] == 1
    assert data["month"]["calls"] == 0
