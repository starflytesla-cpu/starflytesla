from fastapi.testclient import TestClient

from app.main import app


def test_health(client):
    r = client.get("/api/health")
    assert r.json() == {"code": 0, "data": {"status": "ok"}, "msg": "ok"}


def test_initial_admin_can_login_and_read_me(admin):
    r = admin.get("/api/auth/me")
    assert r.status_code == 200
    data = r.json()["data"]
    assert data["email"] == "admin@example.com"
    assert data["role"] == "admin"
    assert "password_hash" not in data


def test_session_cookie_is_httponly_and_secure_over_https(client):
    r = client.post("/api/auth/login", json={"email": "admin@example.com", "password": "admin-password"})
    cookie = r.headers["set-cookie"].lower()
    assert "httponly" in cookie
    assert "secure" in cookie
    assert "samesite=lax" in cookie


def test_wrong_password_returns_error_envelope(client):
    r = client.post("/api/auth/login", json={"email": "admin@example.com", "password": "nope"})
    assert r.status_code == 401
    assert r.json() == {
        "code": 401,
        "data": None,
        "msg": "帳號或密碼錯誤",
        "reason": "invalid_credentials",
    }


def test_unknown_email_gives_same_error_as_wrong_password(client):
    r = client.post("/api/auth/login", json={"email": "ghost@example.com", "password": "nope"})
    assert r.status_code == 401
    assert r.json()["reason"] == "invalid_credentials"


def test_login_is_rate_limited_after_repeated_failures(client):
    for _ in range(10):
        client.post("/api/auth/login", json={"email": "admin@example.com", "password": "bad"})
    r = client.post("/api/auth/login", json={"email": "admin@example.com", "password": "admin-password"})
    assert r.status_code == 429
    assert r.json()["reason"] == "rate_limited"


def test_requests_without_session_are_rejected(client):
    r = client.get("/api/auth/me")
    assert r.status_code == 401
    assert r.json()["reason"] == "unauthorized"


def test_validation_error_uses_envelope(client):
    r = client.post("/api/auth/login", json={"email": "not-an-email", "password": "x"})
    assert r.status_code == 422
    assert r.json()["reason"] == "validation_error"


def test_changing_password_invalidates_other_sessions(admin):
    with TestClient(app, base_url="https://testserver") as other:
        other.post("/api/auth/login", json={"email": "admin@example.com", "password": "admin-password"})
        assert other.get("/api/auth/me").status_code == 200

        r = admin.post(
            "/api/auth/password",
            json={"old_password": "admin-password", "new_password": "new-password-123"},
        )
        assert r.status_code == 200
        # 改密碼的這個裝置拿到新 cookie，繼續可用；其他裝置立即失效。
        assert admin.get("/api/auth/me").status_code == 200
        assert other.get("/api/auth/me").status_code == 401


def test_weak_new_password_is_rejected(admin):
    r = admin.post("/api/auth/password", json={"old_password": "admin-password", "new_password": "short"})
    assert r.status_code == 400
    assert r.json()["reason"] == "weak_password"


def test_admin_creates_shooter_who_cannot_use_admin_apis(admin):
    r = admin.post(
        "/api/users",
        json={"email": "Shooter@Example.com", "display_name": "拍攝員", "password": "shooter-pass", "role": "shooter"},
    )
    assert r.status_code == 200, r.text
    assert r.json()["data"]["email"] == "shooter@example.com"

    with TestClient(app, base_url="https://testserver") as shooter:
        r = shooter.post("/api/auth/login", json={"email": "shooter@example.com", "password": "shooter-pass"})
        assert r.status_code == 200
        assert shooter.get("/api/dashboard").status_code == 200
        for path in ("/api/users", "/api/channels", "/api/usage"):
            r = shooter.get(path)
            assert r.status_code == 403, path
            assert r.json()["reason"] == "forbidden"


def test_duplicate_email_is_rejected(admin):
    body = {"email": "a@example.com", "display_name": "A", "password": "password-1"}
    assert admin.post("/api/users", json=body).status_code == 200
    r = admin.post("/api/users", json={**body, "email": "A@example.com"})
    assert r.status_code == 409


def test_cannot_disable_last_admin(admin):
    me = admin.get("/api/auth/me").json()["data"]
    r = admin.patch(f"/api/users/{me['id']}", json={"is_active": False})
    assert r.status_code == 400
    assert r.json()["reason"] == "last_admin"


def test_disabling_user_revokes_their_session(admin):
    r = admin.post("/api/users", json={"email": "b@example.com", "display_name": "B", "password": "password-1"})
    user_id = r.json()["data"]["id"]
    with TestClient(app, base_url="https://testserver") as user:
        user.post("/api/auth/login", json={"email": "b@example.com", "password": "password-1"})
        assert user.get("/api/auth/me").status_code == 200
        admin.patch(f"/api/users/{user_id}", json={"is_active": False})
        assert user.get("/api/auth/me").status_code == 401
        r = user.post("/api/auth/login", json={"email": "b@example.com", "password": "password-1"})
        assert r.json()["reason"] == "user_disabled"


def test_internal_domain_emails_are_accepted(admin):
    r = admin.post(
        "/api/users",
        json={"email": " Worker@Factory.Local ", "display_name": "W", "password": "password-1"},
    )
    assert r.status_code == 200, r.text
    assert r.json()["data"]["email"] == "worker@factory.local"
    r = admin.post("/api/auth/login", json={"email": "worker@factory.local", "password": "password-1"})
    assert r.status_code == 200
