import httpx
import pytest
import respx
from sqlalchemy import select, update

from app.models import PublishChannel, Tenant, UsageLedger
from app.security import decrypt_secret, encrypt_secret

URL = "https://api.upload-post.com/api/uploadposts/me"
KEY = "test-uploadpost-secret-abcd"


def create_channel(admin, **changes):
    r = admin.post("/api/publish-channels", json={"api_key": KEY, **changes})
    assert r.status_code == 200, r.text
    return r.json()["data"]


def test_encrypts_key_and_exposes_only_safe_fields(admin, db):
    channel = create_channel(admin, api_key=f"  {KEY}\n")
    stored = db.get(PublishChannel, channel["id"])
    assert decrypt_secret(stored.api_key_encrypted) == KEY
    assert KEY not in stored.api_key_encrypted
    response = admin.get("/api/publish-channels")
    assert KEY not in response.text and stored.api_key_encrypted not in response.text
    assert channel["api_key_last4"] == "abcd"
    assert channel["has_api_key"] is True
    assert channel["check_status"] == "untested"


def test_can_save_without_key_and_edit_without_losing_key(admin, db):
    empty = create_channel(admin, api_key="")
    assert empty["has_api_key"] is False
    assert admin.post(f"/api/publish-channels/{empty['id']}/test").json()["reason"] == "missing_api_key"
    channel = create_channel(admin)
    for body in ({"name": "新名稱"}, {"api_key": ""}, {"api_key": None}):
        r = admin.patch(f"/api/publish-channels/{channel['id']}", json=body)
        assert r.status_code == 200 and r.json()["data"]["has_api_key"] is True
    assert decrypt_secret(db.get(PublishChannel, channel["id"]).api_key_encrypted) == KEY
    assert db.scalars(select(UsageLedger)).first() is None


@pytest.mark.parametrize("body", [
    {"api_key": "short"}, {"api_key": "long\nkey-value"}, {"api_key": "非英文金鑰八個字"},
    {"name": "  "}, {"base_url": "https://api.upload-post.com/api?token=bad"},
    {"base_url": "https://api.upload-post.com/api#fragment"},
    {"base_url": "http://api.upload-post.com/api"},
    {"base_url": "https://user:pass@api.upload-post.com/api"},
    {"base_url": "https://127.0.0.1/api"},
    {"base_url": "https://api.upload-post.com:invalid/api"},
    {"base_url": "https://[invalid/api"},
])
def test_rejects_invalid_credentials_and_unsafe_urls(admin, body):
    r = admin.post("/api/publish-channels", json=body)
    assert r.status_code in (400, 422)


@respx.mock
def test_checks_account_with_apikey_and_records_usage(admin, db):
    route = respx.get(URL).mock(return_value=httpx.Response(200, json={
        "success": True, "email": "private@example.com", "plan": "Professional", "token": KEY,
    }))
    channel = create_channel(admin)
    r = admin.post(f"/api/publish-channels/{channel['id']}/test")
    assert r.status_code == 200, r.text
    assert r.json()["data"]["plan"] == "Professional"
    assert KEY not in r.text and "private@example.com" not in r.text
    assert route.calls.last.request.headers["authorization"] == f"Apikey {KEY}"
    assert len(respx.calls) == 1 and respx.calls[0].request.method == "GET"
    stored = db.get(PublishChannel, channel["id"])
    db.refresh(stored)
    assert stored.check_status == "succeeded" and stored.checked_at is not None
    entry = db.scalars(select(UsageLedger)).one()
    assert entry.publish_channel_id == channel["id"] and entry.channel_id is None
    assert entry.action == "publish.channel_test" and entry.status == "succeeded"
    assert entry.cost_micros == 0
    usage = admin.get("/api/usage").json()["data"]["items"][0]
    assert usage["channel_name"] == "Upload-Post"


@respx.mock
@pytest.mark.parametrize("response,reason", [
    (httpx.Response(401, json={"message": KEY}), "upstream_auth"),
    (httpx.Response(403, json={"message": KEY}), "upstream_auth"),
    (httpx.Response(429, json={"message": KEY}), "upstream_error"),
    (httpx.Response(503, text=KEY), "upstream_error"),
    (httpx.Response(302, headers={"Location": "https://127.0.0.1/secret"}), "upstream_error"),
    (httpx.Response(200, text=KEY), "invalid_upstream_response"),
    (httpx.Response(200, json={"success": False, "message": KEY}), "invalid_upstream_response"),
    (httpx.Response(200, json=[]), "invalid_upstream_response"),
    (httpx.Response(200, json={"success": True}), "invalid_upstream_response"),
    (httpx.Response(200, json={"success": True, "plan": KEY}), "invalid_upstream_response"),
])
def test_failed_checks_are_sanitized_and_persisted(admin, db, response, reason):
    respx.get(URL).mock(return_value=response)
    channel = create_channel(admin)
    r = admin.post(f"/api/publish-channels/{channel['id']}/test")
    assert r.status_code == 502 and r.json()["reason"] == reason
    assert KEY not in r.text
    stored = db.get(PublishChannel, channel["id"])
    db.refresh(stored)
    assert stored.check_status == "failed" and stored.plan == ""
    assert KEY not in stored.check_error
    entry = db.scalars(select(UsageLedger)).one()
    assert entry.status == "failed" and KEY not in entry.error
    assert len(respx.calls) == 1


@respx.mock
@pytest.mark.parametrize("error,reason", [
    (httpx.ReadTimeout(KEY), "upstream_timeout"), (httpx.ConnectError(KEY), "upstream_error"),
])
def test_network_errors_do_not_leak_credentials(admin, db, error, reason):
    respx.get(URL).mock(side_effect=error)
    channel = create_channel(admin)
    r = admin.post(f"/api/publish-channels/{channel['id']}/test")
    assert r.status_code == 502 and r.json()["reason"] == reason and KEY not in r.text
    assert db.scalars(select(UsageLedger)).one().status == "failed"


@respx.mock
def test_key_change_or_clear_invalidates_previous_success(admin, db):
    respx.get(URL).mock(return_value=httpx.Response(200, json={"success": True, "plan": "Basic"}))
    channel = create_channel(admin)
    path = f"/api/publish-channels/{channel['id']}"
    assert admin.post(f"{path}/test").status_code == 200
    r = admin.patch(path, json={"api_key": "new-test-key-efgh"})
    assert r.json()["data"]["check_status"] == "untested"
    assert r.json()["data"]["checked_at"] is None
    assert r.json()["data"]["plan"] == ""
    r = admin.patch(path, json={"clear_api_key": True})
    assert r.json()["data"]["has_api_key"] is False
    assert db.get(PublishChannel, channel["id"]).api_key_encrypted == ""
    assert admin.post(f"{path}/test").json()["reason"] == "missing_api_key"
    assert len(respx.calls) == 1


@respx.mock
@pytest.mark.parametrize("changes", [
    {"api_key_encrypted": encrypt_secret("new-concurrent-key")}, {"enabled": False},
])
def test_old_check_does_not_overwrite_concurrent_setting_change(admin, db, changes):
    channel = create_channel(admin)
    def respond(_request):
        db.execute(update(PublishChannel).where(PublishChannel.id == channel["id"]).values(**changes))
        db.commit()
        return httpx.Response(200, json={"success": True, "plan": "Professional"})
    respx.get(URL).mock(side_effect=respond)
    r = admin.post(f"/api/publish-channels/{channel['id']}/test")
    assert r.status_code == 409 and r.json()["reason"] == "channel_changed"
    stored = db.get(PublishChannel, channel["id"])
    db.refresh(stored)
    assert stored.check_status == "untested" and stored.checked_at is None and stored.plan == ""
    assert db.scalars(select(UsageLedger)).one().status == "failed"


@respx.mock
def test_revalidates_dns_and_does_not_call_disabled_channel(admin, fake_dns):
    channel = create_channel(admin)
    path = f"/api/publish-channels/{channel['id']}"
    admin.patch(path, json={"enabled": False})
    assert admin.post(f"{path}/test").json()["reason"] == "channel_disabled"
    admin.patch(path, json={"enabled": True})
    fake_dns["ip"] = "10.0.0.5"
    assert admin.post(f"{path}/test").json()["reason"] == "private_upstream"
    assert len(respx.calls) == 0


@respx.mock
def test_cannot_read_update_or_test_another_tenants_channel(admin, db):
    other = Tenant(name="其他租戶")
    db.add(other)
    db.flush()
    channel = PublishChannel(tenant_id=other.id, name="隱私渠道", base_url="https://api.upload-post.com/api")
    db.add(channel)
    db.commit()
    assert admin.get("/api/publish-channels").json()["data"] == []
    path = f"/api/publish-channels/{channel.id}"
    assert admin.patch(path, json={"name": "修改"}).status_code == 404
    assert admin.post(f"{path}/test").status_code == 404
    assert len(respx.calls) == 0


def test_shooter_and_anonymous_users_cannot_access_publish_channels(client, admin):
    channel = create_channel(admin)
    admin.post("/api/users", json={"email": "shooter@example.com", "display_name": "拍攝員", "password": "test-shooter-password", "role": "shooter"})
    admin.post("/api/auth/logout")
    assert client.get("/api/publish-channels").status_code == 401
    client.post("/api/auth/login", json={"email": "shooter@example.com", "password": "test-shooter-password"})
    assert client.get("/api/publish-channels").status_code == 403
    assert client.post("/api/publish-channels", json={}).status_code == 403
    assert client.patch(f"/api/publish-channels/{channel['id']}", json={"enabled": False}).status_code == 403
    assert client.post(f"/api/publish-channels/{channel['id']}/test").status_code == 403
