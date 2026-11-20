import io

import numpy as np
from fastapi.testclient import TestClient
from PIL import Image

from app.server import app
from conftest import register, sample


def _post(c, data, name="leaf.jpg", **form):
    return c.post("/api/v1/predictions", files={"file": (name, data, "image/jpeg")}, data=form)


def _png(arr):
    b = io.BytesIO()
    Image.fromarray(arr.astype("uint8")).save(b, "PNG")
    return b.getvalue()


def test_guest_prediction_is_not_stored(client):
    r = _post(TestClient(app), sample())
    assert r.status_code == 201, r.text
    j = r.json()
    assert j["saved"] is False and j["id"] is None
    assert j["status"] == "confident"
    assert j["plant"]["model_crop"] == "Tomato" and j["plant"]["info"]["scientific"] == "Solanum lycopersicum"
    assert j["diagnosis"]["name"] == "Early blight"
    assert j["diagnosis"]["knowledge"]["treatment"]["chemical"]
    assert j["heatmap_url"].startswith("data:image/jpeg;base64,")
    assert "severity" not in j          # unvalidated severity is not exposed to users


def test_saved_prediction_roundtrip_and_privacy(client):
    a = register("owner@example.com")
    b = register("intruder@example.com")
    r = _post(a, sample("potato-late-blight.jpg"), crop="aloo")
    assert r.status_code == 201
    j = r.json()
    assert j["saved"] and j["plant"]["source"] == "user" and j["plant"]["typed"] == "Potato"
    did = j["id"]
    assert a.get(f"/api/v1/predictions/{did}").status_code == 200
    img = a.get(f"/api/v1/predictions/{did}/image")
    assert img.status_code == 200 and img.headers["content-type"] == "image/jpeg"
    assert a.get(f"/api/v1/predictions/{did}/heatmap").status_code == 200
    # another user cannot see, edit, download or delete it (same 404 as missing)
    for m, u in [("get", ""), ("get", "/image"), ("get", "/heatmap"), ("get", "/report.pdf"), ("delete", "")]:
        assert getattr(b, m)(f"/api/v1/predictions/{did}{u}").status_code == 404
    assert b.patch(f"/api/v1/predictions/{did}", json={"notes": "x"}).status_code == 404
    assert TestClient(app).get(f"/api/v1/predictions/{did}").status_code == 401
    # stored image has no EXIF
    stored = Image.open(io.BytesIO(img.content))
    assert not stored.getexif()


def test_history_filters_pagination_export(client):
    c = register("history@example.com")
    for f in ["tomato-early-blight.jpg", "corn-common-rust.jpg", "grape-black-rot.jpg"]:
        assert _post(c, sample(f)).status_code == 201
    r = c.get("/api/v1/predictions?limit=2").json()
    assert r["total"] == 3 and len(r["items"]) == 2 and r["next_cursor"]
    r2 = c.get(f"/api/v1/predictions?limit=2&cursor={r['next_cursor']}").json()
    assert len(r2["items"]) == 1
    assert c.get("/api/v1/predictions?crop=corn").json()["total"] == 1
    assert c.get("/api/v1/predictions?q=rust").json()["total"] == 1
    csv = c.get("/api/v1/predictions/export.csv")
    assert csv.status_code == 200 and csv.text.count("\n") == 4
    pid = r["items"][0]["id"]
    assert c.patch(f"/api/v1/predictions/{pid}", json={"notes": "sprayed", "feedback": "correct"}).json()["notes"] == "sprayed"
    pdf = c.get(f"/api/v1/predictions/{pid}/report.pdf")
    assert pdf.status_code == 200 and pdf.content[:4] == b"%PDF" and len(pdf.content) > 20000
    assert c.delete(f"/api/v1/predictions/{pid}").status_code == 204
    assert c.get(f"/api/v1/predictions/{pid}").status_code == 404


def test_refuses_to_guess_on_noise(client):
    rng = np.random.default_rng(0)
    r = _post(TestClient(app), _png(rng.integers(0, 255, (320, 320, 3))), name="noise.png")
    assert r.status_code == 201
    j = r.json()
    assert j["status"] in ("needs_input", "unknown", "no_leaf", "uncertain")
    assert j["diagnosis"] is None or j["status"] == "uncertain"
    assert j["message"]


def test_unsupported_and_unknown_typed_crop(client):
    r = _post(TestClient(app), sample(), crop="okra").json()
    assert r["status"] == "unsupported_crop" and r["diagnosis"] is None and r["message"]
    r = _post(TestClient(app), sample(), crop="banana").json()   # in KB, not in v2 model
    assert r["status"] in ("unsupported_crop", "confident", "tentative", "uncertain")


def test_upload_validation(client):
    c = TestClient(app)
    assert _post(c, b"not an image at all").status_code == 415
    assert _post(c, b"").status_code == 400
    gif = io.BytesIO(); Image.new("RGB", (300, 300)).save(gif, "GIF")
    assert _post(c, gif.getvalue(), name="x.gif").status_code == 415
    assert _post(c, _png(np.zeros((60, 60, 3)))).status_code == 422          # too small
    big = b"\xff\xd8" + b"0" * (16 * 1024 * 1024)
    assert _post(c, big).status_code == 413
    # truncated JPEG
    assert _post(c, sample()[:3000]).status_code == 415


def test_quality_warnings(client):
    dark = _png(np.full((400, 400, 3), 10))
    j = _post(TestClient(app), dark).json()
    codes = {w["code"] for w in j["quality"]["warnings"]}
    assert "dark" in codes and "blurry" in codes


def test_legacy_endpoint_still_works(client):
    r = TestClient(app).post("/api/predict", files={"file": ("x.jpg", sample(), "image/jpeg")})
    assert r.status_code == 200
    j = r.json()
    assert j["top"][0]["crop"] == "Tomato" and j["info"]["actions"]
    assert TestClient(app).get("/api/info").json()["classes"] > 0


def test_demo_runs_real_model_on_samples_only(client):
    c = TestClient(app)
    items = c.get("/api/v1/demo/samples").json()["items"]
    r = c.post(f"/api/v1/demo/{items[0]['file']}").json()
    assert r["diagnosis"]["name"] and r["saved"] is False
    assert c.post("/api/v1/demo/..%2F..%2Fserver.py").status_code in (404, 405)   # never served
    assert c.post("/api/v1/demo/not-a-sample.jpg").status_code == 404
