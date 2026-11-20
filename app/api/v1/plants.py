"""My Plants and analytics — /api/v1/plants, /api/v1/analytics."""
from __future__ import annotations

from collections import Counter, defaultdict
from datetime import timedelta

from fastapi import APIRouter, Depends, Response
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.orm import Session as DBSession

from ...core.errors import AppError
from ...core.security import current_user
from ...db import Diagnosis, Plant, User, aware, get_session, now
from ...knowledge import kb

router = APIRouter(tags=["plants", "analytics"])


class PlantIn(BaseModel):
    nickname: str = Field(min_length=1, max_length=80)
    crop_key: str | None = Field(None, max_length=40)
    location: str | None = Field(None, max_length=120)
    notes: str | None = Field(None, max_length=2000)


def plant_out(db: DBSession, p: Plant) -> dict:
    last = db.scalar(select(Diagnosis).where(Diagnosis.plant_id == p.id).order_by(Diagnosis.id.desc()).limit(1))
    n = db.scalar(select(func.count()).select_from(Diagnosis).where(Diagnosis.plant_id == p.id))
    info = kb.plant_info(p.crop_key) if p.crop_key else None
    return {"id": p.id, "nickname": p.nickname, "crop_key": p.crop_key, "crop": info["name"] if info else None,
            "scientific": info["scientific"] if info else None, "location": p.location, "notes": p.notes,
            "created_at": aware(p.created_at).isoformat(), "diagnosis_count": n,
            "last_status": last.status if last else None, "last_healthy": last.healthy if last else None,
            "last_condition": kb.entry(last.label)["name"] if last and last.label else None,
            "last_checked": aware(last.created_at).isoformat() if last else None}


def _own(db, user, pid) -> Plant:
    p = db.get(Plant, pid)
    if not p or p.user_id != user.id:
        raise AppError(404, "Plant not found.")
    return p


def _check_crop(key):
    if key and key not in kb.plants():
        raise AppError(422, "Unknown crop.", details=[{"field": "crop_key", "message": "Choose a crop from the list."}])


@router.get("/plants")
def list_plants(user: User = Depends(current_user), db: DBSession = Depends(get_session)):
    rows = db.scalars(select(Plant).where(Plant.user_id == user.id).order_by(Plant.nickname))
    return {"items": [plant_out(db, p) for p in rows]}


@router.post("/plants", status_code=201)
def create_plant(body: PlantIn, user: User = Depends(current_user), db: DBSession = Depends(get_session)):
    _check_crop(body.crop_key)
    if db.scalar(select(func.count()).select_from(Plant).where(Plant.user_id == user.id)) >= 200:
        raise AppError(409, "You have reached the limit of 200 plants.")
    p = Plant(user_id=user.id, **body.model_dump())
    db.add(p)
    db.commit()
    return plant_out(db, p)


@router.patch("/plants/{pid}")
def update_plant(pid: int, body: PlantIn, user: User = Depends(current_user), db: DBSession = Depends(get_session)):
    p = _own(db, user, pid)
    _check_crop(body.crop_key)
    for k, v in body.model_dump().items():
        setattr(p, k, v)
    db.commit()
    return plant_out(db, p)


@router.delete("/plants/{pid}", status_code=204)
def delete_plant(pid: int, user: User = Depends(current_user), db: DBSession = Depends(get_session)):
    db.delete(_own(db, user, pid))   # diagnoses keep existing (plant_id set NULL)
    db.commit()
    return Response(status_code=204)


@router.get("/analytics/overview")
def overview(days: int = 180, user: User = Depends(current_user), db: DBSession = Depends(get_session)):
    since = now() - timedelta(days=max(7, min(days, 730)))
    rows = list(db.scalars(select(Diagnosis).where(Diagnosis.user_id == user.id, Diagnosis.created_at >= since)
                           .order_by(Diagnosis.created_at)))
    diagnosed = [d for d in rows if d.status in ("confident", "tentative")]
    by_status = Counter(d.status for d in rows)
    by_disease = Counter(kb.entry(d.label)["name"] + f" ({kb.entry(d.label)['crop']})"
                         for d in diagnosed if d.label and not d.healthy)
    crops = defaultdict(lambda: {"total": 0, "healthy": 0, "diseased": 0, "unclear": 0})
    for d in rows:
        c = (kb.plant_info(d.crop_key) or {}).get("name", "Unknown") if d.crop_key else "Unknown"
        crops[c]["total"] += 1
        if d.status in ("confident", "tentative"):
            crops[c]["healthy" if d.healthy else "diseased"] += 1
        else:
            crops[c]["unclear"] += 1
    weekly = defaultdict(lambda: {"healthy": 0, "diseased": 0, "unclear": 0})
    for d in rows:
        wk = (aware(d.created_at) - timedelta(days=aware(d.created_at).weekday())).date().isoformat()
        k = "unclear" if d.status not in ("confident", "tentative") else ("healthy" if d.healthy else "diseased")
        weekly[wk][k] += 1
    total_all = db.scalar(select(func.count()).select_from(Diagnosis).where(Diagnosis.user_id == user.id))
    n_plants = db.scalar(select(func.count()).select_from(Plant).where(Plant.user_id == user.id))
    return {
        "period_days": days, "total_diagnoses": total_all, "in_period": len(rows), "plants": n_plants,
        "healthy": sum(1 for d in diagnosed if d.healthy), "diseased": sum(1 for d in diagnosed if not d.healthy),
        "unclear": len(rows) - len(diagnosed), "by_status": dict(by_status),
        "top_conditions": [{"name": k, "count": v} for k, v in by_disease.most_common(8)],
        "crops": [{"crop": k, **v} for k, v in sorted(crops.items(), key=lambda kv: -kv[1]["total"])],
        "weekly": [{"week": k, **v} for k, v in sorted(weekly.items())],
        "avg_confidence": round(sum(d.confidence for d in diagnosed) / len(diagnosed), 4) if diagnosed else None,
    }
