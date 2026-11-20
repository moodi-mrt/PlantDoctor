"""Owns the loaded models, the model-version registry and a lock around GPU work.

Inference runs in-process (≈0.1 s per image on the GPU, a few hundred ms on CPU). The public
surface — `analyze()` / `identify_pest()` — is what a separate inference service would expose if
measured load ever justifies splitting it out.
"""
from __future__ import annotations

import hashlib
import logging
import threading
import time
from pathlib import Path

from PIL import Image
from sqlalchemy import select, update

from ..config import LOAD_MODELS, MODEL_PATH, PEST_MODEL_PATH
from ..db import ModelVersion, SessionLocal

log = logging.getLogger("plantdoctor.inference")


def _sha(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


class InferenceService:
    def __init__(self):
        self.predictor = None
        self.pest = None
        self.disease_version_id = None
        self.pest_version_id = None
        self.error: str | None = None
        self._lock = threading.Lock()
        self.stats = {"requests": 0, "errors": 0, "total_ms": 0.0}

    def load(self):
        if not LOAD_MODELS:
            self.error = "model loading disabled (PD_LOAD_MODELS=0)"
            return
        from ..inference import PestPredictor, Predictor
        try:
            self.predictor = Predictor(MODEL_PATH)
            self.disease_version_id = self._register("disease", self.predictor)
            log.info("disease model %s loaded on %s (%d classes)", self.predictor.version,
                     self.predictor.device, len(self.predictor.classes))
        except Exception as e:  # app still serves knowledge, history, etc.
            self.error = f"disease model failed to load: {e}"
            log.exception("disease model failed to load")
        if PEST_MODEL_PATH.exists():
            try:
                self.pest = PestPredictor(PEST_MODEL_PATH)
                self.pest_version_id = self._register("pest", self.pest)
            except Exception:
                log.exception("pest model failed to load")

    def _register(self, task: str, pred) -> int:
        sha = _sha(pred.path)
        with SessionLocal() as s:
            mv = s.scalar(select(ModelVersion).where(ModelVersion.task == task, ModelVersion.version == pred.version))
            if mv is None:
                mv = ModelVersion(task=task, version=pred.version, arch=getattr(pred, "arch", "efficientnet_b0"),
                                  artifact_path=str(pred.path), sha256=sha, n_classes=len(pred.classes),
                                  metrics=getattr(pred, "metrics", {}) or {})
                s.add(mv)
                s.flush()
            elif mv.sha256 != sha:
                log.warning("model %s artifact changed on disk (sha mismatch) — recording new hash", pred.version)
                mv.sha256 = sha
            s.execute(update(ModelVersion).where(ModelVersion.task == task).values(is_active=False))
            mv.is_active = True
            s.commit()
            return mv.id

    @property
    def ready(self) -> bool:
        return self.predictor is not None

    def analyze(self, img: Image.Image, crop: str | None) -> tuple[dict, int]:
        if not self.ready:
            from ..core.errors import AppError
            raise AppError(503, "The diagnosis model is not available right now. Please try again later.")
        t0 = time.perf_counter()
        try:
            with self._lock:     # Grad-CAM uses hooks on the shared model: one request at a time
                try:
                    r = self.predictor.analyze(img, crop)
                except RuntimeError as e:
                    if "CUDA" not in str(e) or self.predictor.device.type != "cuda":
                        raise
                    log.error("GPU inference failed (%s) — switching to CPU", str(e)[:120])
                    import torch
                    torch.cuda.empty_cache()
                    self.predictor.to_cpu()
                    r = self.predictor.analyze(img, crop)
        except Exception:
            self.stats["errors"] += 1
            raise
        ms = int((time.perf_counter() - t0) * 1000)
        self.stats["requests"] += 1
        self.stats["total_ms"] += ms
        return r, ms

    def identify_pest(self, img: Image.Image) -> list | None:
        if self.pest is None:
            return None
        with self._lock:
            return self.pest.predict(img)


service = InferenceService()
