import re

from fastapi.testclient import TestClient

from app.server import app
from conftest import _TMP, register


def _last_link(kind):
    import email
    from email import policy
    files = sorted((_TMP / "outbox").glob("*.eml"), key=lambda f: f.stat().st_mtime_ns)
    txt = email.message_from_bytes(files[-1].read_bytes(), policy=policy.default).get_content()
    m = re.search(rf"/{kind}\?token=([\w-]+)", txt)
    return m.group(1)


def test_register_login_logout_flow(client):
    c = TestClient(app)
    r = c.post("/api/v1/auth/register", json={"email": "Flow@Example.com", "name": "  Ali   Khan ", "password": "correct-horse-42"})
    assert r.status_code == 201
    u = r.json()
    assert u["email"] == "flow@example.com" and u["name"] == "Ali Khan" and u["role"] == "farmer"
    assert u["email_verified"] is False
    assert "pd_session" in c.cookies and "pd_csrf" in c.cookies
    assert c.get("/api/v1/users/me").json()["id"] == u["id"]
    # state-changing call without CSRF header is refused
    assert c.post("/api/v1/auth/logout").status_code == 403
    assert c.post("/api/v1/auth/logout", headers={"X-CSRF-Token": c.cookies["pd_csrf"]}).status_code == 204
    assert c.get("/api/v1/users/me").status_code == 401
    # login again
    r = c.post("/api/v1/auth/login", json={"email": "flow@example.com", "password": "correct-horse-42"})
    assert r.status_code == 200


def test_duplicate_and_weak_password(client):
    register("dup@example.com")
    c = TestClient(app)
    r = c.post("/api/v1/auth/register", json={"email": "DUP@example.com", "name": "x", "password": "correct-horse-42"})
    assert r.status_code == 409 and r.json()["error"]["code"] == "email_taken"
    r = c.post("/api/v1/auth/register", json={"email": "weak@example.com", "name": "x", "password": "password123"})
    assert r.status_code == 422 and r.json()["error"]["code"] == "weak_password"
    r = c.post("/api/v1/auth/register", json={"email": "not-an-email", "name": "x", "password": "correct-horse-42"})
    assert r.status_code == 422 and r.json()["error"]["details"][0]["field"] == "email"


def test_login_errors_are_generic_and_rate_limited(client):
    register("rl@example.com")
    c = TestClient(app)
    bad = c.post("/api/v1/auth/login", json={"email": "rl@example.com", "password": "wrong-password-1"})
    missing = c.post("/api/v1/auth/login", json={"email": "nobody@example.com", "password": "wrong-password-1"})
    assert bad.status_code == missing.status_code == 401
    assert bad.json()["error"]["message"] == missing.json()["error"]["message"]
    codes = [c.post("/api/v1/auth/login", json={"email": "rl@example.com", "password": "x"}).status_code for _ in range(6)]
    assert 429 in codes


def test_email_verification(client):
    c = register("verify@example.com")
    token = _last_link("verify")
    r = c.post("/api/v1/auth/verify", json={"token": token})
    assert r.status_code == 200 and r.json()["email_verified"] is True
    assert c.post("/api/v1/auth/verify", json={"token": token}).status_code == 400   # single use


def test_password_reset_revokes_sessions(client):
    c = register("reset@example.com")
    anon = TestClient(app)
    r = anon.post("/api/v1/auth/forgot", json={"email": "reset@example.com"})
    assert r.status_code == 202
    # unknown email gets the same answer
    assert anon.post("/api/v1/auth/forgot", json={"email": "ghost@example.com"}).json() == r.json()
    token = _last_link("reset")
    assert anon.post("/api/v1/auth/reset", json={"token": token, "password": "short"}).status_code == 422
    token = (anon.post("/api/v1/auth/forgot", json={"email": "reset@example.com"}), _last_link("reset"))[1]
    assert anon.post("/api/v1/auth/reset", json={"token": token, "password": "brand-new-pass-77"}).status_code == 204
    assert c.get("/api/v1/users/me").status_code == 401           # old session revoked
    assert anon.post("/api/v1/auth/login", json={"email": "reset@example.com", "password": "brand-new-pass-77"}).status_code == 200


def test_change_password_keeps_current_session(client):
    c = register("chpw@example.com")
    other = TestClient(app)
    other.post("/api/v1/auth/login", json={"email": "chpw@example.com", "password": "correct-horse-42"})
    r = c.post("/api/v1/auth/password", json={"current_password": "correct-horse-42", "new_password": "another-good-pass-9"})
    assert r.status_code == 204
    assert c.get("/api/v1/users/me").status_code == 200
    assert other.get("/api/v1/users/me").status_code == 401


def test_profile_update_whitelists_prefs(client):
    c = register("prof@example.com")
    r = c.patch("/api/v1/users/me", json={"name": "New Name", "locale": "ur", "prefs": {"weather_alerts": True, "role": "admin"}})
    assert r.status_code == 200
    j = r.json()
    assert j["name"] == "New Name" and j["locale"] == "ur" and j["prefs"] == {"weather_alerts": True} and j["role"] == "farmer"
    assert c.patch("/api/v1/users/me", json={"locale": "xx"}).status_code == 422


def test_admin_from_env_and_role_guard(client):
    admin = register("admin@example.com")
    assert admin.get("/api/v1/users/me").json()["role"] == "admin"
    farmer = register("plain@example.com")
    assert farmer.get("/api/v1/admin/overview").status_code == 403
    assert admin.get("/api/v1/admin/overview").status_code == 200
    uid = farmer.get("/api/v1/users/me").json()["id"]
    assert admin.patch(f"/api/v1/admin/users/{uid}", json={"is_active": False}).status_code == 200
    assert farmer.get("/api/v1/users/me").status_code == 401      # deactivated
    me = admin.get("/api/v1/users/me").json()["id"]
    assert admin.patch(f"/api/v1/admin/users/{me}", json={"role": "farmer"}).status_code == 400
    events = admin.get("/api/v1/admin/audit?action=admin.").json()["items"]
    assert any(e["action"] == "admin.user_updated" for e in events)


def test_delete_account(client):
    c = register("del@example.com")
    assert c.request("DELETE", "/api/v1/users/me", json={"password": "nope-nope-nope"}).status_code == 400
    assert c.request("DELETE", "/api/v1/users/me", json={"password": "correct-horse-42"}).status_code == 204
    assert TestClient(app).post("/api/v1/auth/login", json={"email": "del@example.com", "password": "correct-horse-42"}).status_code == 401
