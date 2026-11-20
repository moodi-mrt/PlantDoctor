"""Crops, diseases (Knowledge Center), products and weather — /api/v1."""
from __future__ import annotations

from fastapi import APIRouter, Depends, Query, Request

from ...config import DEFAULT_LOCATION
from ...core import ratelimit
from ...core.errors import AppError
from ...core.security import optional_user
from ...db import User
from ...knowledge import kb
from ...services import products, weather
from ...services.inference_service import service

router = APIRouter(tags=["knowledge"])


def _supported_prefixes() -> set:
    return set(service.predictor.crops) if service.ready else set()


def crop_out(key: str) -> dict:
    p = kb.plant_info(key)
    sup = _supported_prefixes()
    model = "Citrus" if p["model"] in ("Citrus", "Orange") else p["model"]
    labels = [l for l in kb.disease_keys() if kb.plant_key_for_label(l) == key]
    return {**p, "supported": model in sup, "disease_count": len(labels)}


@router.get("/crops")
def crops():
    out = [crop_out(k) for k in kb.plants()]
    out.sort(key=lambda c: (not c["supported"], c["name"]))
    return {"items": out, "supported_count": sum(c["supported"] for c in out)}


@router.get("/crops/resolve")
def resolve(q: str = Query(..., min_length=1, max_length=60)):
    """Autocomplete: 'tamatar' / 'Kinnow' / 'Solanum lycopersicum' -> crops."""
    hits = kb.find_plant(q, limit=6)
    return {"query": q, "items": [{**h, "supported": crop_out(h["key"])["supported"]} for h in hits]}


def disease_summary(label: str) -> dict:
    e = kb.entry(label)
    return {"label": e["label"], "name": e["name"], "crop": e["crop"], "crop_key": e["crop_key"], "kind": e["kind"],
            "pathogen": e["pathogen"], "symptoms": e["symptoms"], "affected_parts": e["affected_parts"],
            "in_model": service.ready and label in service.predictor.classes}


@router.get("/diseases")
def diseases(crop: str | None = Query(None, max_length=40), kind: str | None = Query(None, max_length=20),
             q: str | None = Query(None, max_length=80)):
    items = []
    ql = (q or "").lower().strip()
    for label in kb.disease_keys():
        e = kb.entry(label)
        if crop and e["crop_key"] != crop:
            continue
        if kind and e["kind"] != kind:
            continue
        if ql:
            hay = " ".join([e["name"], e["crop"] or "", e["pathogen"], e["symptoms"], e["causes"]]).lower()
            if not all(w in hay for w in ql.split()):
                continue
        items.append(disease_summary(label))
    items.sort(key=lambda d: (d["crop"] or "", d["name"]))
    kinds = sorted({kb.entry(l)["kind"] for l in kb.disease_keys()})
    return {"items": items, "total": len(items), "kinds": kinds}


@router.get("/diseases/{label}")
def disease(label: str):
    if label not in kb.disease_keys() and not label.endswith("healthy"):
        raise AppError(404, "Disease not found in the knowledge base.")
    e = kb.entry(label)
    return {**e, "in_model": service.ready and label in service.predictor.classes}


@router.get("/products")
def product_suggestions(label: str = Query(..., max_length=120)):
    if label not in kb.disease_keys():
        raise AppError(404, "Unknown disease label.")
    return products.for_label(label)


@router.get("/weather")
def get_weather(request: Request, q: str | None = Query(None, max_length=80), lat: float | None = None,
                lon: float | None = None, crops: str | None = Query(None, max_length=200),
                user: User | None = Depends(optional_user)):
    ratelimit.hit(f"wx:{ratelimit.client_ip(request)}", 60, 60)
    try:
        if lat is not None and lon is not None:
            place = {"name": f"{lat:.2f}, {lon:.2f}", "lat": lat, "lon": lon}
        else:
            place = weather.geocode(q or (user.location if user and user.location else DEFAULT_LOCATION))
        fc = weather.forecast(place["lat"], place["lon"])
    except LookupError as e:
        raise AppError(404, str(e).capitalize() + ". Try a nearby city name.")
    except ValueError as e:
        raise AppError(422, str(e))
    except Exception:
        raise AppError(503, "Weather service is not reachable right now. Please try again later.")
    d = fc["data"]
    crop_keys = [c for c in (crops or "").split(",") if c] or None
    return {"place": place, "current": d.get("current"), "daily": d.get("daily"),
            "hourly": {k: d["hourly"][k][:72] for k in ("time", "temperature_2m", "relative_humidity_2m", "precipitation")},
            "risks": weather.disease_risks(d["hourly"], crop_keys), "irrigation": weather.irrigation_hint(d.get("daily", {})),
            "source": fc["source"], "fetched_at": fc["fetched_at"], "stale": fc.get("stale", False),
            "risk_method": "Hours in the next 72 h with temperature and humidity inside each disease's favourable range "
                           "(knowledge base rules). Indicates elevated infection risk, not certainty."}
