"""PlantDoctor web server (FastAPI app factory).

    ./run.sh                       # dev server on http://127.0.0.1:8000
    uvicorn app.server:app         # production (behind a TLS reverse proxy, --proxy-headers)

Routes:
    /api/v1/*        versioned REST API (OpenAPI docs at /api/docs outside production)
    /api/predict     v1 legacy endpoint kept for the classic UI and existing clients
    /classic         the original single-page UI (unchanged)
    /*               the React app (frontend/dist), with client-side routing fallback
"""
from __future__ import annotations

import io
import json
import logging
import os
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, File, Request, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from .config import CORS_ORIGINS, DB_URL, IS_PROD, ROOT
from .core import errors
from .core.logging import RequestContext, setup_logging
from .services.inference_service import service

log = logging.getLogger("plantdoctor")
STATIC = Path(__file__).parent / "static"
SPA = ROOT / "frontend" / "dist"
REPORT_PDF = ROOT / "reports" / "PlantDoctor_Report.pdf"


def migrate():
    from alembic import command
    from alembic.config import Config
    cfg = Config(str(ROOT / "alembic.ini"))
    cfg.set_main_option("script_location", str(ROOT / "alembic"))
    command.upgrade(cfg, "head")


@asynccontextmanager
async def lifespan(app: FastAPI):
    setup_logging()
    migrate()
    service.load()
    from .services import seed
    p = service.predictor
    seed.sync(set(p.classes) if p else None, set(p.crops) if p else None)
    log.info("PlantDoctor ready (db=%s, model=%s)", DB_URL.split("://")[0], p.version if p else "none")
    yield


def create_app() -> FastAPI:
    docs = None if IS_PROD and os.environ.get("PD_DOCS") != "1" else "/api/docs"
    app = FastAPI(title="PlantDoctor API", version="3.0.0", docs_url=docs, redoc_url=None,
                  openapi_url="/api/openapi.json" if docs else None, lifespan=lifespan)
    errors.install(app)
    app.add_middleware(RequestContext)
    if CORS_ORIGINS:
        app.add_middleware(CORSMiddleware, allow_origins=CORS_ORIGINS, allow_credentials=True,
                           allow_methods=["GET", "POST", "PATCH", "DELETE"], allow_headers=["Content-Type", "X-CSRF-Token"])

    from .api.v1 import admin, assistant, auth, knowledge, plants, predictions
    for r in (auth.router, predictions.router, knowledge.router, plants.router, assistant.router, admin.router):
        app.include_router(r, prefix="/api/v1")
    app.include_router(admin.health, prefix="/api/v1")

    @app.get("/api/v1/meta", tags=["meta"])
    def meta():
        """Public facts for the landing page / model card — real measured numbers only."""
        p = service.predictor
        out = {"model_loaded": service.ready, "model_version": p.version if p else None,
               "classes": len(p.classes) if p else 0, "crops": len(p.crops) if p else 0,
               "device": str(p.device) if p else None, "calibrated": bool(p and p.temperature != 1.0),
               "ood_detection": bool(p and p.ood), "pest_model": service.pest.version if service.pest else None,
               "metrics": (p.metrics if p and p.metrics else None)}
        if not out["metrics"]:
            # Fall back to the v2 evaluation reports shipped with the repository.
            m = {}
            tp, fp = ROOT / "reports" / "test_metrics.json", ROOT / "reports" / "field_metrics.json"
            if tp.exists():
                t = json.loads(tp.read_text())
                m["test"] = {"accuracy": t["test_acc"], "macro_f1": t["macro_f1"], "n": t["n_test"], "split": "random (v2)"}
            if fp.exists():
                f = json.loads(fp.read_text())
                m["field"] = {"top1": f["top1_acc"], "top5": f["top5_acc"], "crop": f["crop_acc"], "n": f["n_images"],
                              "dataset": "PlantDoc test (real field photos)"}
            out["metrics"] = m
        if service.pest:
            out["pest_metrics"] = service.pest.metrics
        return out

    # ───────── legacy endpoints (classic UI) ─────────
    @app.get("/api/info", include_in_schema=False)
    def info():
        from .inference import pretty
        crops = {}
        if service.ready:
            for c in service.predictor.classes:
                crop, dis = pretty(c)
                if crop != "—":
                    crops.setdefault(crop, []).append(dis)
        samples = json.loads((STATIC / "samples" / "samples.json").read_text())
        m = meta()["metrics"] or {}
        legacy = {}
        if "test" in m:
            legacy.update({"test_acc": m["test"]["accuracy"], "macro_f1": m["test"]["macro_f1"], "n_test": m["test"]["n"]})
        if "field" in m:
            f = m["field"]
            legacy["field"] = {"n_images": f["n"], "top1_acc": f["top1"], "top5_acc": f["top5"], "crop_acc": f["crop"]}
        return {"classes": len(service.predictor.classes) if service.ready else 0, "crops": crops,
                "device": str(service.predictor.device) if service.ready else None, "gpu": None,
                "samples": samples, **legacy}

    @app.post("/api/predict", include_in_schema=False)
    async def predict_legacy(request: Request, file: UploadFile = File(...)):
        from .core import ratelimit
        from .knowledge.kb import lookup
        from .services import images
        ratelimit.hit(f"legacy:{ratelimit.client_ip(request)}", 30, 60)
        img, _ = images.decode(await images.read_upload(file))
        if not service.ready:
            return JSONResponse({"detail": "Model not loaded."}, 503)
        import time
        t0 = time.perf_counter()
        with service._lock:
            res = service.predictor.predict(img)
        res["ms"] = round((time.perf_counter() - t0) * 1000)
        res["info"] = lookup(res["top"][0]["label"])
        return res

    @app.get("/report", include_in_schema=False)
    def report():
        if not REPORT_PDF.exists():
            return JSONResponse({"detail": "Report not generated yet."}, 404)
        return FileResponse(REPORT_PDF, media_type="application/pdf", filename="PlantDoctor_Report.pdf",
                            content_disposition_type="inline")

    @app.get("/classic", include_in_schema=False)
    def classic():
        return FileResponse(STATIC / "index.html")

    app.mount("/static", StaticFiles(directory=STATIC), name="static")

    # ───────── React SPA ─────────
    if (SPA / "assets").is_dir():
        app.mount("/assets", StaticFiles(directory=SPA / "assets"), name="assets")

    @app.get("/{path:path}", include_in_schema=False)
    def spa(path: str):
        if path.startswith("api/"):
            return JSONResponse({"error": {"code": "not_found", "message": "Unknown API route."}}, 404)
        f = (SPA / path).resolve()
        if path and SPA.resolve() in f.parents and f.is_file():
            return FileResponse(f)
        if (SPA / "index.html").exists():
            return FileResponse(SPA / "index.html", headers={"Cache-Control": "no-cache"})
        return FileResponse(STATIC / "index.html")   # frontend not built yet: classic UI
    return app


app = create_app()
