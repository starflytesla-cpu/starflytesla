"""豆包方舟（BytePlus / 火山引擎）Key 驗證失敗時的診斷。"""

import httpx
import respx
from sqlalchemy import select

from app import diagnostics
from app.models import UsageLedger

BYTEPLUS_URL = "https://ark.ap-southeast.bytepluses.com/api/v3/chat/completions"
VOLC_URL = "https://ark.cn-beijing.volces.com/api/v3/chat/completions"
VOLC_KEY = "6f1c2d3e-4a5b-4c6d-8e9f-0a1b2c3d9914"
ARK_401 = {"error": {"code": "AuthenticationError", "message": "The API key doesn't exist. Request id: 0217", "type": "Unauthorized"}}


def _accepts(valid_key: str | None):
    """模擬方舟端點：只有 valid_key 能通過驗證（模型不存在回 404），其他一律 401。"""

    def handler(request: httpx.Request) -> httpx.Response:
        if valid_key and request.headers["authorization"] == f"Bearer {valid_key}":
            return httpx.Response(404, json={"error": {"code": "InvalidEndpointOrModel.NotFound"}})
        return httpx.Response(401, json=ARK_401)

    return handler


def _byteplus_vision(admin, api_key):
    r = admin.post("/api/channels", json={"provider": "byteplus", "api_key": api_key})
    assert r.status_code == 200, r.text
    return r.json()["data"]["models"][0]


@respx.mock
def test_volcengine_key_on_byteplus_tells_user_where_it_belongs(admin, db):
    respx.post(BYTEPLUS_URL).mock(side_effect=_accepts(None))
    respx.post(VOLC_URL).mock(side_effect=_accepts(VOLC_KEY))
    model = _byteplus_vision(admin, VOLC_KEY)

    r = admin.post(f"/api/channel-models/{model['id']}/test", json={"prompt": "hi"})
    assert r.status_code == 502
    body = r.json()
    assert body["reason"] == "upstream_auth"
    assert "HTTP 401" in body["msg"] and "火山引擎方舟（中國區）" in body["msg"]
    assert "https://ark.cn-beijing.volces.com/api/v3" in body["msg"]
    assert VOLC_KEY not in body["msg"]

    entry = db.scalars(select(UsageLedger)).one()
    assert entry.status == "failed" and entry.cost_micros == 0


@respx.mock
def test_access_key_is_detected_without_probing(admin):
    route = respx.post(BYTEPLUS_URL).mock(side_effect=_accepts(None))
    volc = respx.post(VOLC_URL).mock(side_effect=_accepts(None))
    model = _byteplus_vision(admin, "AKLTabcdefghijklmnop")

    r = admin.post(f"/api/channel-models/{model['id']}/test", json={"prompt": "hi"})
    assert r.status_code == 502
    assert "Access Key" in r.json()["msg"]
    assert route.call_count == 1 and volc.call_count == 0


@respx.mock
def test_unknown_key_everywhere(admin):
    respx.post(BYTEPLUS_URL).mock(side_effect=_accepts(None))
    respx.post(VOLC_URL).mock(side_effect=_accepts(None))
    model = _byteplus_vision(admin, VOLC_KEY)

    r = admin.post(f"/api/channel-models/{model['id']}/test", json={"prompt": "hi"})
    assert "都不認得這把 Key" in r.json()["msg"]


@respx.mock
def test_inconclusive_probe_gives_no_wrong_hint(admin):
    """端點對任何 Key 都回 404（例如先檢查模型）時，不能誤判 Key 屬於那裡。"""
    respx.post(BYTEPLUS_URL).mock(side_effect=_accepts(None))
    respx.post(VOLC_URL).mock(return_value=httpx.Response(404, json={}))
    model = _byteplus_vision(admin, VOLC_KEY)

    r = admin.post(f"/api/channel-models/{model['id']}/test", json={"prompt": "hi"})
    assert "火山引擎方舟（中國區）」" not in r.json()["msg"]


def test_volcengine_preset(admin):
    presets = {p["provider"]: p for p in admin.get("/api/channel-presets").json()["data"]["presets"]}
    assert presets["volcengine"]["base_url"] == "https://ark.cn-beijing.volces.com/api/v3"
    r = admin.post("/api/channels", json={"provider": "volcengine", "api_key": VOLC_KEY})
    assert r.status_code == 200, r.text
    assert r.json()["data"]["base_url"] == "https://ark.cn-beijing.volces.com/api/v3"


@respx.mock
def test_diagnostics_never_prints_the_key(admin, capsys):
    respx.post(BYTEPLUS_URL).mock(side_effect=_accepts(None))
    respx.post(VOLC_URL).mock(side_effect=_accepts(VOLC_KEY))
    _byteplus_vision(admin, VOLC_KEY)

    diagnostics.main()
    out = capsys.readouterr().out
    assert "UUID 格式" in out
    assert "BytePlus 國際版（東南亞）（目前設定）：401 不認得這把 Key" in out
    assert "火山引擎方舟（中國區）：404 驗證通過" in out
    assert VOLC_KEY not in out and "9914" not in out
