def test_health(client):
    assert client.get("/api/v1/health/live").json() == {"status": "ok"}
    r = client.get("/api/v1/health/ready")
    assert r.status_code == 200, r.text
    assert r.json()["checks"]["disease_model"] == "ok"


def test_meta_and_security_headers(client):
    r = client.get("/api/v1/meta")
    assert r.status_code == 200
    assert r.json()["model_loaded"] is True
    assert r.headers["x-content-type-options"] == "nosniff"
    assert "frame-ancestors 'none'" in r.headers["content-security-policy"]
    assert r.headers["x-request-id"]
