import os
import shutil
import socket
import tempfile

import pytest

# 必須在匯入 app 之前設定，Settings 會在第一次使用時讀取並快取。
os.environ.setdefault(
    "DATABASE_URL",
    os.environ.get("TEST_DATABASE_URL", "postgresql+psycopg://starfly:starfly@localhost:5432/starfly_test"),
)
os.environ["SECRET_KEY"] = "test-secret-key"
os.environ["ADMIN_EMAIL"] = "admin@example.com"
os.environ["ADMIN_PASSWORD"] = "admin-password"
MEDIA_ROOT = tempfile.mkdtemp(prefix="starfly-media-")
os.environ["MEDIA_ROOT"] = MEDIA_ROOT
os.environ["MIN_FREE_BYTES"] = "0"

from alembic import command  # noqa: E402
from alembic.config import Config  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy import text  # noqa: E402

from app.db import get_engine, get_sessionmaker  # noqa: E402
from app.main import app  # noqa: E402
from app.security import login_limiter  # noqa: E402

API_DIR = os.path.dirname(os.path.dirname(__file__))
PUBLIC_IP = "93.184.216.34"


@pytest.fixture(scope="session", autouse=True)
def _migrate():
    cfg = Config(os.path.join(API_DIR, "alembic.ini"))
    cfg.set_main_option("script_location", os.path.join(API_DIR, "migrations"))
    command.downgrade(cfg, "base")
    command.upgrade(cfg, "head")
    yield


@pytest.fixture(autouse=True)
def _clean_db():
    with get_engine().begin() as conn:
        conn.execute(
            text("TRUNCATE videos, scripts, templates, brand_profiles, tasks, clips, assets, uploads, usage_ledger, channel_models, model_channels, users, tenants CASCADE")
        )
    login_limiter._failures.clear()
    shutil.rmtree(MEDIA_ROOT, ignore_errors=True)
    os.makedirs(MEDIA_ROOT)
    yield


@pytest.fixture(autouse=True)
def fake_dns(monkeypatch):
    """測試不依賴真實 DNS：預設把所有網域解析成公網 IP；個別測試可覆寫。"""
    resolved = {"ip": PUBLIC_IP}
    real_getaddrinfo = socket.getaddrinfo

    def fake_getaddrinfo(host, port, *args, **kwargs):
        if host in ("localhost", os.environ.get("TEST_DB_HOST", "localhost")):
            return real_getaddrinfo(host, port, *args, **kwargs)  # 資料庫連線走真實解析
        try:
            socket.inet_pton(socket.AF_INET, host)
            ip = host
        except OSError:
            ip = resolved["ip"]
        return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", (ip, port))]

    monkeypatch.setattr(socket, "getaddrinfo", fake_getaddrinfo)
    return resolved


@pytest.fixture
def client():
    # 進入 with 會觸發 lifespan，建立初始管理員。
    with TestClient(app, base_url="https://testserver") as c:
        yield c


@pytest.fixture
def admin(client):
    r = client.post("/api/auth/login", json={"email": "admin@example.com", "password": "admin-password"})
    assert r.status_code == 200, r.text
    return client


@pytest.fixture
def db():
    with get_sessionmaker()() as session:
        yield session
