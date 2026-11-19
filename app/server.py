"""PlantDoctor web server.  Run:  ./run.sh   then open http://127.0.0.1:8000"""
import io
import json
import time
from pathlib import Path

import torch
from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from PIL import Image, UnidentifiedImageError

from .inference import ROOT, Predictor, pretty
from .knowledge import lookup

STATIC = Path(__file__).parent / "static"
app = FastAPI(title="PlantDoctor", docs_url="/api/docs")
predictor = Predictor()

_metrics = {}
mp = ROOT / "reports" / "test_metrics.json"
if mp.exists():
    m = json.loads(mp.read_text())
    _metrics = {"test_acc": m["test_acc"], "macro_f1": m["macro_f1"], "n_test": m["n_test"],
                "top5_acc": m.get("top5_acc")}
fp = ROOT / "reports" / "field_metrics.json"
if fp.exists():
    fm = json.loads(fp.read_text())
    _metrics["field"] = {k: fm[k] for k in ("n_images", "top1_acc", "top5_acc", "crop_acc",
                                            "share_flagged_low_conf", "acc_when_confident")}
REPORT_PDF = ROOT / "reports" / "PlantDoctor_Report.pdf"


@app.get("/")
def index():
    return FileResponse(STATIC / "index.html")


@app.get("/report")
def report():
    if not REPORT_PDF.exists():
        raise HTTPException(404, "Report not generated yet.")
    return FileResponse(REPORT_PDF, media_type="application/pdf", filename="PlantDoctor_Report.pdf",
                        content_disposition_type="inline")


@app.get("/api/info")
def info():
    crops = {}
    for c in predictor.classes:
        crop, dis = pretty(c)
        if crop != "—":
            crops.setdefault(crop, []).append(dis)
    samples = json.loads((STATIC / "samples" / "samples.json").read_text()) if (STATIC / "samples" / "samples.json").exists() else []
    return {"classes": len(predictor.classes), "crops": crops, "device": str(predictor.device),
            "gpu": torch.cuda.get_device_name(0) if torch.cuda.is_available() else None,
            "samples": samples, **_metrics}


@app.post("/api/predict")
async def predict(file: UploadFile = File(...)):
    data = await file.read()
    if len(data) > 15 * 1024 * 1024:
        raise HTTPException(413, "Image is larger than 15 MB.")
    try:
        img = Image.open(io.BytesIO(data))
        img.load()
    except (UnidentifiedImageError, OSError):
        raise HTTPException(400, "That file isn't a readable image (use JPG, PNG or WebP).")
    t0 = time.perf_counter()
    res = predictor.predict(img)
    res["ms"] = round((time.perf_counter() - t0) * 1000)
    res["info"] = lookup(res["top"][0]["label"])
    return JSONResponse(res)


app.mount("/static", StaticFiles(directory=STATIC), name="static")
