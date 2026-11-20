"""Administration (role=admin) and health checks."""
from __future__ import annotations

import json
import shutil
from datetime import timedelta
from pathlib import Path

from fastapi import APIRouter, Depends, Query, Request, Response
from pydantic import BaseModel, Field
from sqlalchemy import func, or_, select, text
from sqlalchemy.orm import Session as DBSession

from ...config import DATA_DIR, ROOT
from ...core.errors import AppError
from ...core.security import require_admin
from ...db import (ApiCache, AuditEvent, DatasetMeta, Diagnosis, ModelVersion, User, aware, get_session, now)
from ...knowledge import kb
from ...services import audit, llm
from ...services.inference_service import service
from ...services.storage import storage
from .predictions import summary

router = APIRouter(tags=["admin"])
health = APIRouter(tags=["health"])


@health.get("/health/live")
def live():
    return {"status": "ok"}


@health.get("/health/ready")
def ready(response: Response, db: DBSession = Depends(get_session)):
    checks = {}
    try:
        db.execute(text("select 1"))
        checks["database"] = "ok"
    except Exception as e:
        checks["database"] = f"error: {type(e).__name__}"
    checks["disease_model"] = "ok" if service.ready else (service.error or "not loaded")
    ok = all(v == "ok" for v in checks.values())
    response.status_code = 200 if ok else 503
    return {"status": "ok" if ok else "degraded", "checks": checks}


@router.get("/admin/overview")
def overview(_: User = Depends(require_admin), db: DBSession = Depends(get_session)):
    t = now()
    cnt = lambda *w: db.scalar(select(func.count()).select_from(Diagnosis).where(*w))
    by_status = dict(db.execute(select(Diagnosis.status, func.count()).group_by(Diagnosis.status)).all())
    total = sum(by_status.values())
    lat = db.scalar(select(func.avg(Diagnosis.latency_ms)).where(Diagnosis.latency_ms > 0))
    fb = dict(db.execute(select(Diagnosis.feedback, func.count()).where(Diagnosis.feedback.is_not(None))
                         .group_by(Diagnosis.feedback)).all())
    top = db.execute(select(Diagnosis.label, func.count()).where(Diagnosis.status.in_(["confident", "tentative"]),
                                                                  Diagnosis.healthy.is_(False))
                     .group_by(Diagnosis.label).order_by(func.count().desc()).limit(8)).all()
    days = []
    for i in range(13, -1, -1):
        d0 = (t - timedelta(days=i)).replace(hour=0, minute=0, second=0, microsecond=0)
        days.append({"day": d0.date().isoformat(), "count": cnt(Diagnosis.created_at >= d0, Diagnosis.created_at < d0 + timedelta(days=1))})
    return {
        "users": {"total": db.scalar(select(func.count()).select_from(User)),
                  "verified": db.scalar(select(func.count()).select_from(User).where(User.email_verified_at.is_not(None))),
                  "new_7d": db.scalar(select(func.count()).select_from(User).where(User.created_at >= t - timedelta(days=7)))},
        "diagnoses": {"total": total, "last_24h": cnt(Diagnosis.created_at >= t - timedelta(days=1)),
                      "last_7d": cnt(Diagnosis.created_at >= t - timedelta(days=7)), "by_status": by_status,
                      "low_confidence_rate": round(1 - by_status.get("confident", 0) / total, 4) if total else None,
                      "avg_latency_ms": round(lat or 0, 1), "user_feedback": fb, "per_day": days,
                      "top_conditions": [{"label": l, "name": kb.entry(l)["name"], "crop": kb.entry(l)["crop"], "count": c}
                                         for l, c in top if l]},
        "inference": {**service.stats, "loaded": service.ready,
                      "device": str(service.predictor.device) if service.ready else None,
                      "version": service.predictor.version if service.ready else None,
                      "pest_model": service.pest.version if service.pest else None},
    }


class UserPatch(BaseModel):
    role: str | None = Field(None, pattern=r"^(farmer|consultant|admin)$")
    is_active: bool | None = None


def _user_row(u: User) -> dict:
    return {"id": u.id, "email": u.email, "name": u.name, "role": u.role, "is_active": u.is_active,
            "email_verified": u.email_verified_at is not None, "created_at": aware(u.created_at).isoformat(),
            "last_login_at": aware(u.last_login_at).isoformat() if u.last_login_at else None}


@router.get("/admin/users")
def users(q: str | None = Query(None, max_length=80), cursor: int | None = None, limit: int = Query(25, le=100),
          _: User = Depends(require_admin), db: DBSession = Depends(get_session)):
    stmt = select(User)
    if q:
        stmt = stmt.where(or_(User.email.ilike(f"%{q}%"), User.name.ilike(f"%{q}%")))
    if cursor:
        stmt = stmt.where(User.id < cursor)
    rows = list(db.scalars(stmt.order_by(User.id.desc()).limit(limit + 1)))
    counts = dict(db.execute(select(Diagnosis.user_id, func.count()).group_by(Diagnosis.user_id)).all())
    return {"items": [{**_user_row(u), "diagnoses": counts.get(u.id, 0)} for u in rows[:limit]],
            "next_cursor": rows[limit - 1].id if len(rows) > limit else None}


@router.patch("/admin/users/{uid}")
def patch_user(uid: int, body: UserPatch, request: Request, admin: User = Depends(require_admin),
               db: DBSession = Depends(get_session)):
    u = db.get(User, uid)
    if not u:
        raise AppError(404, "User not found.")
    if u.id == admin.id and (body.role not in (None, "admin") or body.is_active is False):
        raise AppError(400, "You can't remove your own admin access or deactivate yourself.")
    changes = {}
    if body.role and body.role != u.role:
        changes["role"] = [u.role, body.role]
        u.role = body.role
    if body.is_active is not None and body.is_active != u.is_active:
        changes["is_active"] = [u.is_active, body.is_active]
        u.is_active = body.is_active
    db.commit()
    if changes:
        audit.record(db, request, "admin.user_updated", admin.id, "user", uid, **changes)
    return _user_row(u)


@router.get("/admin/models")
def models(_: User = Depends(require_admin), db: DBSession = Depends(get_session)):
    rows = db.scalars(select(ModelVersion).order_by(ModelVersion.created_at.desc()))
    reg = ROOT / "models" / "registry.json"
    registry = json.loads(reg.read_text()) if reg.exists() else {}
    out = []
    for m in rows:
        out.append({"id": m.id, "task": m.task, "version": m.version, "arch": m.arch, "n_classes": m.n_classes,
                    "sha256": m.sha256[:12], "is_active": m.is_active, "created_at": aware(m.created_at).isoformat(),
                    "metrics": m.metrics or registry.get(m.version, {}).get("metrics", {}),
                    "artifact_exists": Path(m.artifact_path).exists()})
    legacy = {}
    for name in ("test_metrics.json", "field_metrics.json"):
        p = ROOT / "reports" / name
        if p.exists():
            d = json.loads(p.read_text())
            legacy[name.split(".")[0]] = {k: v for k, v in d.items() if not isinstance(v, (dict, list))}
    return {"items": out, "registry": registry, "v2_reports": legacy}


@router.post("/admin/models/{mid}/activate")
def activate(mid: int, request: Request, admin: User = Depends(require_admin), db: DBSession = Depends(get_session)):
    m = db.get(ModelVersion, mid)
    if not m or not Path(m.artifact_path).exists():
        raise AppError(404, "Model artifact not found.")
    from ...inference import PestPredictor, Predictor
    try:
        if m.task == "disease":
            p = Predictor(Path(m.artifact_path))
            service.predictor, service.disease_version_id = p, service._register("disease", p)
        else:
            p = PestPredictor(Path(m.artifact_path))
            service.pest, service.pest_version_id = p, service._register("pest", p)
    except Exception as e:
        raise AppError(500, f"Model failed to load: {type(e).__name__}")
    audit.record(db, request, "admin.model_activated", admin.id, "model_version", mid, version=m.version)
    return {"activated": m.version}


@router.get("/admin/predictions/review")
def review_queue(kind: str = Query("low_confidence", pattern=r"^(low_confidence|feedback_incorrect|all)$"),
                 cursor: int | None = None, limit: int = Query(25, le=100),
                 _: User = Depends(require_admin), db: DBSession = Depends(get_session)):
    """Failed / low-confidence predictions. Photos are only visible if the user opted in to sharing."""
    stmt = select(Diagnosis)
    if kind == "low_confidence":
        stmt = stmt.where(or_(Diagnosis.status != "confident", Diagnosis.confidence < 0.7))
    elif kind == "feedback_incorrect":
        stmt = stmt.where(Diagnosis.feedback == "incorrect")
    if cursor:
        stmt = stmt.where(Diagnosis.id < cursor)
    rows = list(db.scalars(stmt.order_by(Diagnosis.id.desc()).limit(limit + 1)))
    shared = {u.id for u in db.scalars(select(User).where(User.id.in_({d.user_id for d in rows})))
              if (u.prefs or {}).get("share_images_for_improvement")}
    items = []
    for d in rows[:limit]:
        s = summary(d)
        s.pop("thumbnail_url")
        s.update({"user_id": d.user_id, "feedback": d.feedback, "review": d.review,
                  "plant_confidence": d.plant_confidence, "crop_source": d.crop_source,
                  "alternatives": [{"label": t["label"], "prob": round(t["prob"], 3)} for t in (d.result.get("top") or [])[1:4]],
                  "ood": d.result.get("ood"), "severity_experimental": d.result.get("severity"),
                  "image_url": f"/api/v1/admin/predictions/{d.id}/image" if d.user_id in shared and d.image_id else None})
        items.append(s)
    return {"items": items, "next_cursor": rows[limit - 1].id if len(rows) > limit else None}


class ReviewIn(BaseModel):
    review: str = Field(pattern=r"^(confirmed|mislabeled|ood|bad_photo)$")


@router.patch("/admin/predictions/{did}/review")
def set_review(did: int, body: ReviewIn, request: Request, admin: User = Depends(require_admin),
               db: DBSession = Depends(get_session)):
    d = db.get(Diagnosis, did)
    if not d:
        raise AppError(404, "Diagnosis not found.")
    d.review = body.review
    db.commit()
    audit.record(db, request, "admin.prediction_reviewed", admin.id, "diagnosis", did, review=body.review)
    return {"id": did, "review": d.review}


@router.get("/admin/predictions/{did}/image")
def admin_image(did: int, request: Request, admin: User = Depends(require_admin), db: DBSession = Depends(get_session)):
    d = db.get(Diagnosis, did)
    owner = db.get(User, d.user_id) if d else None
    if not d or not d.image or not owner or not (owner.prefs or {}).get("share_images_for_improvement"):
        raise AppError(404, "Image not available (the user has not opted in to sharing).")
    audit.record(db, request, "admin.image_viewed", admin.id, "diagnosis", did)
    return Response(storage.get(d.image.storage_key), media_type="image/jpeg", headers={"Cache-Control": "private, no-store"})


@router.get("/admin/datasets")
def datasets(_: User = Depends(require_admin), db: DBSession = Depends(get_session)):
    cat = DATA_DIR / "catalog.json"
    return {"items": [{"key": d.key, "name": d.name, "license": d.license, **d.data} for d in db.scalars(select(DatasetMeta))],
            "catalog": json.loads(cat.read_text()) if cat.exists() else None}


@router.get("/admin/audit")
def audit_log(action: str | None = Query(None, max_length=60), limit: int = Query(50, le=200),
              _: User = Depends(require_admin), db: DBSession = Depends(get_session)):
    stmt = select(AuditEvent)
    if action:
        stmt = stmt.where(AuditEvent.action.like(f"{action}%"))
    rows = db.scalars(stmt.order_by(AuditEvent.id.desc()).limit(limit))
    return {"items": [{"id": e.id, "action": e.action, "actor_id": e.actor_id, "target": f"{e.target_type}:{e.target_id}",
                       "ip": e.ip, "meta": e.meta, "created_at": aware(e.created_at).isoformat()} for e in rows]}


@router.get("/admin/system")
def system(_: User = Depends(require_admin), db: DBSession = Depends(get_session)):
    du = shutil.disk_usage(DATA_DIR)
    gpu = None
    try:
        import torch
        if torch.cuda.is_available():
            gpu = {"name": torch.cuda.get_device_name(0),
                   "memory_used_mb": round(torch.cuda.memory_allocated() / 2**20, 1)}
    except Exception:
        pass
    return {"database": str(db.bind.url).split("@")[-1].split("///")[-1].split("/")[-1],
            "disk": {"free_gb": round(du.free / 1e9, 1), "total_gb": round(du.total / 1e9, 1)},
            "gpu": gpu, "llm_available": llm.available(),
            "cache_entries": db.scalar(select(func.count()).select_from(ApiCache)),
            "model_error": service.error}
