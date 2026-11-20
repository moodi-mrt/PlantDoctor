"""Diagnosis (prediction) endpoints — /api/v1/predictions."""
from __future__ import annotations

import base64
import csv
import io
from datetime import datetime

from fastapi import APIRouter, Depends, File, Form, Query, Request, Response, UploadFile
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from sqlalchemy import and_, func, or_, select
from sqlalchemy.orm import Session as DBSession

from ...config import GUEST_SCANS_PER_DAY, REQUIRE_VERIFIED_EMAIL
from ...core import ratelimit
from ...core.errors import AppError
from ...core.security import current_user, optional_user
from ...db import Diagnosis, ImageRecord, Plant, User, aware, get_session
from ...knowledge import kb
from ...services import audit, images
from ...services.inference_service import service
from ...services.storage import new_key, storage

router = APIRouter(tags=["predictions"])

MESSAGES = {
    "confident": None,
    "tentative": "Possible match — the model is only moderately sure. Compare the alternatives and confirm with an "
                 "agronomist before spraying.",
    "uncertain": "I cannot confidently identify this plant disease. Please upload a clearer close-up of the affected "
                 "leaf, or consult an agricultural specialist.",
    "needs_input": "I couldn't confidently identify which plant this is. Tell me the plant name and I'll analyse the "
                   "photo for that crop — or retake the photo with one leaf filling the frame.",
    "unknown": "This photo doesn't look like the plant images the model was trained on, so I won't guess. Upload a "
               "clear photo of a single leaf or fruit, or consult an agricultural specialist.",
    "no_leaf": "No plant leaf or fruit was found in this photo. Photograph one leaf filling most of the frame.",
    "unsupported_crop": "This plant isn't supported by the diagnosis model yet, so I can't diagnose it reliably. "
                        "Please consult your local agriculture extension office.",
}


def resolve_crop(text: str | None) -> tuple[str | None, str | None, str | None]:
    """Free text / key -> (plant_key, model_prefix, display). Unknown names give (None, None, text)."""
    if not text or not text.strip():
        return None, None, None
    hits = kb.find_plant(text.strip()[:60], limit=1)
    if not hits:
        return None, None, text.strip()[:60]
    p = hits[0]
    return p["key"], p["model"], p["name"]


def plant_block(model_prefix: str | None, plant_key: str | None = None):
    key = plant_key or (kb.plant_key_for_label(f"{model_prefix}___x") if model_prefix else None)
    info = kb.plant_info(key) if key else None
    return info


def build_response(r: dict, *, diag: Diagnosis | None, heatmap_inline: str | None, quality: dict,
                   crop_text: str | None, latency_ms: int, created_at: datetime | None) -> dict:
    status = r["status"]
    plant = r.get("plant") or {}
    model_prefix = plant.get("crop")
    pinfo = plant_block(model_prefix) if model_prefix else None
    if status == "unsupported_crop":
        pinfo = plant_block(None, kb.find_plant(crop_text, 1)[0]["key"]) if crop_text and kb.find_plant(crop_text, 1) else None
    top = r.get("top") or []
    best = top[0] if top and status in ("confident", "tentative", "uncertain") else None
    entry = kb.entry(best["label"]) if best else None

    def alt(t):
        e = kb.entry(t["label"])
        return {"label": t["label"], "name": e["name"], "crop": e["crop"], "kind": e["kind"], "probability": round(t["prob"], 4)}

    return {
        "id": diag.id if diag else None,
        "saved": diag is not None,
        "created_at": (aware(created_at) or datetime.now().astimezone()).isoformat(),
        "status": status,
        "message": MESSAGES.get(status),
        "model_version": r.get("model_version"),
        "latency_ms": latency_ms,
        "plant": {
            "source": plant.get("source"), "model_crop": model_prefix,
            "confidence": plant.get("prob"), "agrees_with_user": plant.get("agrees"),
            "typed": crop_text, "info": pinfo,
            "candidates": [{"crop": c["crop"], "probability": c["prob"],
                            "info": plant_block(c["crop"])} for c in plant.get("candidates", [])],
        } if (plant or crop_text) else None,
        "diagnosis": {
            "label": best["label"], "name": entry["name"], "kind": entry["kind"], "healthy": r.get("healthy", False),
            "confidence": round(best["prob"], 4), "calibrated": bool(getattr(service.predictor, "temperature", 1.0) != 1.0),
            "knowledge": entry,
        } if best else None,
        "alternatives": [alt(t) for t in top[1:5]] if best else [alt(t) for t in top[:3]],
        "findings": [alt(t) for t in r.get("findings", [])],
        "ood": r.get("ood"),
        "quality": quality,
        "image_url": f"/api/v1/predictions/{diag.id}/image" if diag and diag.image_id else None,
        "heatmap_url": f"/api/v1/predictions/{diag.id}/heatmap" if diag and diag.heatmap_key else heatmap_inline,
        "expert_help": kb.expert_help() if status != "confident" or (best and best["prob"] < 0.85) else [],
        "notes": diag.notes if diag else None,
        "feedback": diag.feedback if diag else None,
        "plant_id": diag.plant_id if diag else None,
    }


def serialize(d: Diagnosis) -> dict:
    r = d.result
    return build_response(r, diag=d, heatmap_inline=None, quality=r.get("_quality", {}),
                          crop_text=r.get("_crop_text"), latency_ms=d.latency_ms, created_at=d.created_at)


def _own(db: DBSession, user: User, did: int) -> Diagnosis:
    d = db.get(Diagnosis, did)
    if not d or d.user_id != user.id:          # same 404 for "missing" and "not yours" (no ID probing)
        raise AppError(404, "Diagnosis not found.")
    return d


@router.post("/predictions", status_code=201)
async def create_prediction(request: Request, file: UploadFile = File(...),
                            crop: str | None = Form(None, max_length=60),
                            plant_id: int | None = Form(None), save: bool = Form(True),
                            user: User | None = Depends(optional_user), db: DBSession = Depends(get_session)):
    ip = ratelimit.client_ip(request)
    if user:
        ratelimit.hit(f"pred:{user.id}", 30, 60)
        if REQUIRE_VERIFIED_EMAIL and not user.email_verified_at:
            raise AppError(403, "Please confirm your email address first — check your inbox.", "email_unverified")
    else:
        ratelimit.hit(f"pred-guest:{ip}", GUEST_SCANS_PER_DAY, 86400,
                      f"Guest limit reached ({GUEST_SCANS_PER_DAY} scans per day). Create a free account to continue.")
    data = await images.read_upload(file)
    img, mime = images.decode(data)
    q = images.quality(img)
    plant_key, prefix, crop_text = resolve_crop(crop)
    model_crop = prefix and ("Citrus" if prefix in ("Citrus", "Orange") else prefix)
    if crop and not prefix:
        # Typed a plant we don't know at all → unsupported, but still a valid answer.
        r = {"status": "unsupported_crop", "plant": {"source": "user", "crop": None, "candidates": []},
             "top": [], "findings": [], "heatmap": None, "model_version": service.predictor.version if service.ready else None}
        ms = 0
    else:
        r, ms = service.analyze(img, model_crop)

    if user and plant_id is not None:
        pl = db.get(Plant, plant_id)
        if not pl or pl.user_id != user.id:
            raise AppError(404, "Plant not found.")

    heat_inline = r.pop("heatmap", None)
    if not (user and save):
        return build_response(r, diag=None, heatmap_inline=heat_inline, quality=q, crop_text=crop_text,
                              latency_ms=ms, created_at=None)

    jpeg = images.to_storage_jpeg(img)
    rec = ImageRecord(owner_id=user.id, sha256=images.sha256(jpeg), storage_key=new_key(f"u{user.id}/img", "jpg"),
                      mime="image/jpeg", width=img.width, height=img.height, bytes=len(jpeg))
    storage.put(rec.storage_key, jpeg)
    db.add(rec)
    db.flush()
    heat_key = None
    if heat_inline and heat_inline.startswith("data:image/jpeg;base64,"):
        heat_key = new_key(f"u{user.id}/cam", "jpg")
        storage.put(heat_key, base64.b64decode(heat_inline.split(",", 1)[1]))
    top = (r.get("top") or [None])[0]
    stored = {**r, "_quality": q, "_crop_text": crop_text, "_upload_mime": mime}
    d = Diagnosis(user_id=user.id, plant_id=plant_id, image_id=rec.id, heatmap_key=heat_key,
                  model_version_id=service.disease_version_id, model_version=r.get("model_version") or "n/a",
                  crop_key=plant_key or kb.plant_key_for_label(f"{(r.get('plant') or {}).get('crop')}___x"),
                  crop_source="user" if crop else "image", label=top["label"] if top else None,
                  status=r["status"], confidence=top["prob"] if top else 0.0,
                  plant_confidence=(r.get("plant") or {}).get("prob"), healthy=bool(r.get("healthy")),
                  result=stored, latency_ms=ms)
    db.add(d)
    db.commit()
    return serialize(d)


class Page(BaseModel):
    items: list[dict]
    next_cursor: int | None
    total: int


def _filters(user: User, crop, status, q, date_from, date_to):
    cond = [Diagnosis.user_id == user.id]
    if crop:
        cond.append(Diagnosis.crop_key == crop)
    if status:
        cond.append(Diagnosis.status.in_(status.split(",")))
    if date_from:
        cond.append(Diagnosis.created_at >= date_from)
    if date_to:
        cond.append(Diagnosis.created_at <= date_to)
    if q:
        like = f"%{q.lower()[:60]}%"
        cond.append(or_(func.lower(Diagnosis.label).like(like), func.lower(Diagnosis.notes).like(like),
                        func.lower(Diagnosis.crop_key).like(like)))
    return and_(*cond)


@router.get("/predictions", response_model=Page)
def list_predictions(crop: str | None = Query(None, max_length=40), status: str | None = Query(None, max_length=80),
                     q: str | None = Query(None, max_length=60), date_from: datetime | None = None,
                     date_to: datetime | None = None, plant_id: int | None = None,
                     cursor: int | None = None, limit: int = Query(20, ge=1, le=100),
                     user: User = Depends(current_user), db: DBSession = Depends(get_session)):
    cond = _filters(user, crop, status, q, date_from, date_to)
    if plant_id:
        cond = and_(cond, Diagnosis.plant_id == plant_id)
    total = db.scalar(select(func.count()).select_from(Diagnosis).where(cond))
    stmt = select(Diagnosis).where(cond)
    if cursor:
        stmt = stmt.where(Diagnosis.id < cursor)
    rows = list(db.scalars(stmt.order_by(Diagnosis.id.desc()).limit(limit + 1)))
    nxt = rows[limit - 1].id if len(rows) > limit else None
    return {"items": [summary(d) for d in rows[:limit]], "next_cursor": nxt, "total": total}


def summary(d: Diagnosis) -> dict:
    e = kb.entry(d.label) if d.label and d.status in ("confident", "tentative", "uncertain") else None
    return {"id": d.id, "created_at": aware(d.created_at).isoformat(), "status": d.status,
            "crop_key": d.crop_key, "crop": (kb.plant_info(d.crop_key) or {}).get("name") if d.crop_key else None,
            "label": d.label, "name": e["name"] if e else None, "kind": e["kind"] if e else None,
            "healthy": d.healthy, "confidence": round(d.confidence, 4), "plant_id": d.plant_id,
            "thumbnail_url": f"/api/v1/predictions/{d.id}/image" if d.image_id else None,
            "model_version": d.model_version}


@router.get("/predictions/export.csv")
def export_csv(crop: str | None = None, status: str | None = None, q: str | None = None,
               user: User = Depends(current_user), db: DBSession = Depends(get_session)):
    rows = db.scalars(select(Diagnosis).where(_filters(user, crop, status, q, None, None)).order_by(Diagnosis.id.desc()))
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(["id", "date", "crop", "condition", "status", "confidence", "healthy", "model_version", "notes"])
    for d in rows:
        s = summary(d)
        w.writerow([d.id, s["created_at"], s["crop"] or "", s["name"] or "", d.status, f"{d.confidence:.3f}",
                    d.healthy, d.model_version, (d.notes or "").replace("\n", " ")])
    return Response(buf.getvalue(), media_type="text/csv",
                    headers={"Content-Disposition": 'attachment; filename="plantdoctor-diagnoses.csv"'})


@router.get("/predictions/{did}")
def get_prediction(did: int, user: User = Depends(current_user), db: DBSession = Depends(get_session)):
    return serialize(_own(db, user, did))


class PatchIn(BaseModel):
    notes: str | None = Field(None, max_length=2000)
    plant_id: int | None = None
    feedback: str | None = Field(None, pattern=r"^(correct|incorrect|unsure)$")


@router.patch("/predictions/{did}")
def patch_prediction(did: int, body: PatchIn, user: User = Depends(current_user), db: DBSession = Depends(get_session)):
    d = _own(db, user, did)
    fields = body.model_fields_set
    if "notes" in fields:
        d.notes = body.notes
    if "feedback" in fields:
        d.feedback = body.feedback
    if "plant_id" in fields:
        if body.plant_id is not None:
            pl = db.get(Plant, body.plant_id)
            if not pl or pl.user_id != user.id:
                raise AppError(404, "Plant not found.")
        d.plant_id = body.plant_id
    db.commit()
    return serialize(d)


@router.delete("/predictions/{did}", status_code=204)
def delete_prediction(did: int, request: Request, user: User = Depends(current_user), db: DBSession = Depends(get_session)):
    d = _own(db, user, did)
    keys = [k for k in (d.heatmap_key, d.image.storage_key if d.image else None) if k]
    img = d.image
    db.delete(d)
    if img:
        db.delete(img)
    db.commit()
    for k in keys:
        storage.delete(k)
    audit.record(db, request, "diagnosis.deleted", user.id, "diagnosis", did)
    return Response(status_code=204)


def _private_image(data: bytes) -> Response:
    return Response(data, media_type="image/jpeg", headers={"Cache-Control": "private, max-age=3600"})


@router.get("/predictions/{did}/image")
def prediction_image(did: int, user: User = Depends(current_user), db: DBSession = Depends(get_session)):
    d = _own(db, user, did)
    if not d.image:
        raise AppError(404, "Image not stored.")
    return _private_image(storage.get(d.image.storage_key))


@router.get("/predictions/{did}/heatmap")
def prediction_heatmap(did: int, user: User = Depends(current_user), db: DBSession = Depends(get_session)):
    d = _own(db, user, did)
    if not d.heatmap_key:
        raise AppError(404, "No heatmap for this diagnosis.")
    return _private_image(storage.get(d.heatmap_key))


@router.get("/predictions/{did}/report.pdf")
def prediction_pdf(did: int, user: User = Depends(current_user), db: DBSession = Depends(get_session)):
    from ...services.report_pdf import build_pdf
    d = _own(db, user, did)
    data = serialize(d)
    photo = storage.get(d.image.storage_key) if d.image else None
    heat = storage.get(d.heatmap_key) if d.heatmap_key else None
    from ...services.products import flat_verified
    prods = flat_verified(d.label) if d.label and data.get("diagnosis") else []
    pdf = build_pdf(data, photo, heat, user, prods)
    return StreamingResponse(io.BytesIO(pdf), media_type="application/pdf",
                             headers={"Content-Disposition": f'attachment; filename="plantdoctor-report-{did}.pdf"'})


@router.post("/pests/identify")
async def identify_pest(request: Request, file: UploadFile = File(...), user: User | None = Depends(optional_user)):
    """Insect identification (IP102 model). Separate from disease diagnosis on purpose."""
    ratelimit.hit(f"pest:{user.id if user else ratelimit.client_ip(request)}", 20 if user else 5, 3600)
    if service.pest is None:
        raise AppError(503, "The insect identification model is not available yet.", "pest_model_unavailable")
    data = await images.read_upload(file)
    img, _ = images.decode(data)
    preds = service.identify_pest(img)
    best = preds[0]
    status = "confident" if best["prob"] >= 0.7 else "tentative" if best["prob"] >= 0.4 else "uncertain"
    return {"status": status, "message": None if status == "confident" else MESSAGES["uncertain"].replace("plant disease", "insect"),
            "predictions": [{"name": p["label"], "probability": round(p["prob"], 4)} for p in preds],
            "model_version": service.pest.version, "metrics": service.pest.metrics,
            "dataset_note": "Insect model trained on IP102 (102 crop pests, mostly East-Asian field photos)."}


@router.get("/predictions/{did}/explanation")
def explanation(did: int, request: Request, lang: str = Query("en", pattern=r"^(en|ur)$"),
                user: User = Depends(current_user), db: DBSession = Depends(get_session)):
    """Plain-language explanation written by Claude from the knowledge-base entry (validated, cached).
    Returns {"available": false} when no Claude credentials are configured."""
    from ...services import llm
    d = _own(db, user, did)
    if not d.label or d.status not in ("confident", "tentative", "uncertain"):
        return {"available": False, "reason": "No diagnosis to explain for this result."}
    ratelimit.hit(f"explain:{user.id}", 30, 3600)
    out = llm.explain(d.result, kb.entry(d.label), lang)
    out["label"] = "AI-generated explanation based only on the PlantDoctor knowledge base"
    return out


DEMO_DIR = __import__("pathlib").Path(__file__).resolve().parents[2] / "static" / "samples"


@router.get("/demo/samples")
def demo_samples():
    import json as _json
    return {"items": _json.loads((DEMO_DIR / "samples.json").read_text())}


@router.post("/demo/{name}")
def demo_run(name: str, request: Request):
    """Real model run on one of the bundled sample photos (landing-page demo; nothing stored)."""
    import json as _json
    ratelimit.hit(f"demo:{ratelimit.client_ip(request)}", 30, 3600)
    allowed = {s["file"] for s in _json.loads((DEMO_DIR / "samples.json").read_text())}
    if name not in allowed:
        raise AppError(404, "Unknown sample.")
    img, _ = images.decode((DEMO_DIR / name).read_bytes())
    r, ms = service.analyze(img, None)
    heat = r.pop("heatmap", None)
    return build_response(r, diag=None, heatmap_inline=heat, quality=images.quality(img), crop_text=None,
                          latency_ms=ms, created_at=None)
