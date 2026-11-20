import json
from unittest import mock

import pytest
from fastapi.testclient import TestClient

from app.knowledge import kb
from app.server import app
from app.services import llm, products, weather
from conftest import register, sample


def test_every_model_class_has_a_complete_kb_entry(client):
    from app.services.inference_service import service
    missing = [c for c in service.predictor.classes if not kb.entry(c)["kb_complete"]]
    assert missing == []


def test_kb_entries_never_contain_doses():
    for label in kb.disease_keys():
        blob = json.dumps(kb.entry(label))
        assert not llm._DOSE.search(blob.replace("0800-17000", "")), label


def test_kb_references_resolve():
    for label in kb.disease_keys():
        for r in kb.entry(label)["references"]:
            assert r["url"].startswith("http"), (label, r)


def test_crops_and_resolve(client):
    c = TestClient(app)
    crops = c.get("/api/v1/crops").json()
    assert crops["supported_count"] >= 20
    r = c.get("/api/v1/crops/resolve?q=tamatar").json()
    assert r["items"][0]["key"] == "tomato" and r["items"][0]["supported"]
    assert c.get("/api/v1/crops/resolve?q=gandum").json()["items"][0]["key"] == "wheat"


def test_disease_search_and_detail(client):
    c = TestClient(app)
    r = c.get("/api/v1/diseases?q=late blight").json()
    assert {d["crop"] for d in r["items"]} >= {"Tomato", "Potato"}
    assert c.get("/api/v1/diseases?crop=rice&kind=pest").json()["total"] >= 3
    d = c.get("/api/v1/diseases/Tomato___Late_blight").json()
    assert d["pathogen"].startswith("Phytophthora") and d["references"]
    assert c.get("/api/v1/diseases/Nope___Nothing").status_code == 404


def test_products_are_verified_or_labelled_search(client):
    r = TestClient(app).get("/api/v1/products?label=Tomato___Late_blight").json()
    assert r["groups"]
    for g in r["groups"]:
        for p in g["verified"]:
            assert p["type"] == "verified" and p["url"].startswith("https://") and p["verified_on"]
        assert all(s["type"] == "search" for s in g["search"])
    # metalaxyl-M must not match plain metalaxyl products
    g = next(g for g in r["groups"] if g["active_ingredient"].startswith("metalaxyl-M"))
    assert all("metalaxyl-m" in p["active_ingredient"].lower().replace(" ", "-") or "mefenoxam" in p["active_ingredient"].lower()
               for p in g["verified"])


FAKE_HOURLY = {"time": [f"2026-01-15T{h:02d}:00" for h in range(24)] * 3,
               "temperature_2m": [12.0] * 72, "relative_humidity_2m": [95] * 72}


def test_weather_risk_rules_respect_season():
    jan = weather.disease_risks(FAKE_HOURLY, ["wheat", "potato", "mango"])
    names = {(r["crop"], r["disease"]) for r in jan}
    assert ("Wheat", "Yellow (stripe) rust") in names
    assert ("Potato", "Late blight") in names
    july = dict(FAKE_HOURLY, time=[t.replace("-01-", "-07-") for t in FAKE_HOURLY["time"]])
    assert not any(r["crop"] == "Wheat" for r in weather.disease_risks(july, ["wheat"]))


def test_weather_endpoint_with_mocked_api(client):
    fake = {"data": {"current": {"temperature_2m": 20}, "daily": {"precipitation_sum": [0, 0, 0],
            "et0_fao_evapotranspiration": [3, 3, 3]}, "hourly": {**FAKE_HOURLY, "precipitation": [0] * 72}},
            "source": "test", "fetched_at": "2026-01-15T00:00:00Z", "cached": False}
    with mock.patch.object(weather, "geocode", return_value={"name": "Lahore", "lat": 31.5, "lon": 74.3}), \
         mock.patch.object(weather, "forecast", return_value=fake):
        r = TestClient(app).get("/api/v1/weather?q=Lahore&crops=potato").json()
    assert r["place"]["name"] == "Lahore" and r["source"] == "test" and r["irrigation"]
    assert any(x["disease"] == "Late blight" for x in r["risks"])


def test_llm_validator_blocks_doses_and_foreign_ingredients():
    e = kb.entry("Tomato___Late_blight")
    ok = llm.Explanation(summary="Late blight.", what_to_do_now=["Remove infected plants."], why_it_happened="Cool wet weather.",
                         prevention=["Use resistant varieties."], caution="Confirm with an agronomist.")
    assert llm.validate(ok, e) == []
    bad = ok.model_copy(update={"what_to_do_now": ["Spray mancozeb at 2 g per litre."]})
    assert llm.validate(bad, e)
    foreign = ok.model_copy(update={"what_to_do_now": ["Spray imidacloprid now."]})
    assert any("imidacloprid" in p for p in llm.validate(foreign, e))


def test_plants_and_analytics(client):
    c = register("plants@example.com")
    p = c.post("/api/v1/plants", json={"nickname": "Back garden tomatoes", "crop_key": "tomato"}).json()
    assert p["crop"] == "Tomato"
    assert c.post("/api/v1/plants", json={"nickname": "x", "crop_key": "dragonfruit"}).status_code == 422
    r = c.post("/api/v1/predictions", files={"file": ("a.jpg", sample(), "image/jpeg")}, data={"plant_id": p["id"]})
    assert r.status_code == 201
    other = register("plants2@example.com")
    assert other.post("/api/v1/predictions", files={"file": ("a.jpg", sample(), "image/jpeg")},
                      data={"plant_id": p["id"]}).status_code == 404
    lst = c.get("/api/v1/plants").json()["items"]
    assert lst[0]["diagnosis_count"] == 1 and lst[0]["last_condition"] == "Early blight"
    a = c.get("/api/v1/analytics/overview").json()
    assert a["total_diagnoses"] == 1 and a["diseased"] == 1 and a["crops"][0]["crop"] == "Tomato"


def test_assistant_falls_back_to_kb_without_llm(client):
    c = register("assist@example.com")
    did = c.post("/api/v1/predictions", files={"file": ("a.jpg", sample(), "image/jpeg")}).json()["id"]
    r = c.post("/api/v1/assistant/chat", json={"message": "How do I treat this?", "diagnosis_id": did})
    assert r.status_code == 200, r.text
    j = r.json()
    assert j["mode"] == "knowledge_base" and "Tomato___Early_blight" in [x["doc_id"] for x in j["citations"]]
    conv = c.get(f"/api/v1/assistant/conversations/{j['conversation_id']}").json()
    assert [m["role"] for m in conv["messages"]] == ["user", "assistant"]
    other = register("assist2@example.com")
    assert other.get(f"/api/v1/assistant/conversations/{j['conversation_id']}").status_code == 404
    assert other.post("/api/v1/assistant/chat", json={"message": "hi", "diagnosis_id": did}).status_code == 404


def test_assistant_rejects_unsafe_llm_answer(client):
    from app.api.v1 import assistant
    c = register("assist3@example.com")

    class Resp:
        stop_reason = "end_turn"
        model = "fake"
        parsed_output = assistant.Answer(answer="Spray mancozeb 2.5 g per litre every 7 days [Tomato___Late_blight]",
                                         cited_ids=["Tomato___Late_blight"], needs_expert=False)

    class Client:
        def __init__(self, *a, **k):
            self.beta = type("B", (), {"messages": type("M", (), {"parse": staticmethod(lambda **kw: Resp())})()})()

    with mock.patch.object(llm, "available", return_value=True), mock.patch("anthropic.Anthropic", Client):
        j = c.post("/api/v1/assistant/chat", json={"message": "late blight tomato dose"}).json()
    assert j["mode"] == "knowledge_base" and "safety check" in j["reason"]
    assert "2.5 g" not in j["answer"]


def test_spa_fallback_and_unknown_api(client):
    c = TestClient(app)
    assert c.get("/api/v1/does-not-exist").status_code == 404
    assert c.get("/classic").status_code == 200
    r = c.get("/app/diagnose")
    assert r.status_code == 200 and "text/html" in r.headers["content-type"]
