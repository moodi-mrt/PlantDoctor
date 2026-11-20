"""Model loading, two-stage prediction (plant -> disease), Grad-CAM and severity estimate.

The image model is a single EfficientNet whose classes are "<Crop>___<Condition>". We use it in
two stages so each answer has its own, honest confidence:

  1. Plant identification: P(crop) = sum of the probabilities of that crop's classes.
     If the best crop is not clearly ahead, we do NOT guess — status "needs_input" asks the
     user to type the plant name (or retake the photo).
  2. Disease detection: probabilities renormalised within the identified (or user-given) crop.
     Every other condition of that crop scoring >= SECONDARY is reported as a possible
     co-occurring problem.

All thresholds are named constants below and were chosen on the validation split (see
reports/thresholds.json written by tools/eval_field.py).
"""
import base64
import io
import json
import logging
from pathlib import Path

import numpy as np
import torch
import torch.nn as nn
import torch.nn.functional as F
from PIL import Image, ImageFilter, ImageOps
from torchvision import models, transforms

from .config import DEVICE, MODEL_PATH, PEST_MODEL_PATH, ROOT


def pick_device() -> torch.device:
    if DEVICE == "cpu" or not torch.cuda.is_available():
        return torch.device("cpu")
    return torch.device("cuda")

log = logging.getLogger("plantdoctor.inference")

BACKGROUND = "Background_without_leaves"
CONFIDENT = 0.70        # disease probability (within crop) at/above which we state a firm result
UNCERTAIN = 0.40        # below this the disease is reported as inconclusive
BACKGROUND_MIN = 0.60   # "no plant" only if the background class is at least this sure
PLANT_MIN = 0.55        # crop probability needed to accept the photo-based plant identification
PLANT_MARGIN = 0.15     # ...and the lead it must have over the runner-up crop
SECONDARY = 0.15        # other conditions above this are listed as possible co-occurring problems

# Legacy class prefix -> current prefix (the v2 model calls citrus "Orange").
PREFIX_ALIAS = {"Orange": "Citrus"}

DISPLAY = {
    "Cercospora leaf spot Gray leaf spot": "Gray leaf spot (Cercospora)",
    "Northern Leaf Blight": "Northern leaf blight",
    "Haunglongbing (Citrus greening)": "Huanglongbing (citrus greening)",
    "Esca (Black Measles)": "Esca (black measles)",
    "Leaf blight (Isariopsis Leaf Spot)": "Leaf blight (Isariopsis leaf spot)",
    "Spider mites Two-spotted spider mite": "Spider mites (two-spotted)",
    "Tomato Yellow Leaf Curl Virus": "Yellow leaf curl virus",
    "Tomato mosaic virus": "Mosaic virus",
    "Leaf Mold": "Leaf mold",
    "Target Spot": "Target spot",
    "Apple scab": "Scab",
    "healthy": "Healthy",
}


def crop_prefix(label: str) -> str:
    p = label.split("___", 1)[0] if "___" in label else ""
    return PREFIX_ALIAS.get(p, p)


def pretty(name: str):
    """'Tomato___Early_blight' -> ('Tomato', 'Early blight')."""
    if "___" not in name:
        return "—", name.replace("_", " ")
    crop, dis = name.split("___", 1)
    crop = PREFIX_ALIAS.get(crop, crop)
    crop = crop.replace("_", " ").replace(",", "").replace("(including sour)", "").strip()
    crop = crop.replace("Pepper bell", "Bell pepper")
    dis = dis.replace("_", " ").replace("  ", " ").strip()
    dis = DISPLAY.get(dis, dis)
    return crop, dis[0].upper() + dis[1:]


def _build(arch: str, n: int) -> nn.Module:
    """Same builder as training (ml/common.py) so serving matches training exactly."""
    from ml.common import build_model
    return build_model(arch, n, pretrained=False)


class Predictor:
    def __init__(self, path: Path = MODEL_PATH):
        ck = torch.load(path, map_location="cpu", weights_only=False)
        self.classes = ck["classes"]
        self.arch = ck.get("arch", "efficientnet_b0")
        self.version = ck.get("version") or Path(path).stem
        self.device = pick_device()
        m = _build(self.arch, len(self.classes))
        m.load_state_dict(ck["state_dict"])
        self.model = m.eval().to(self.device)
        self.val_acc = ck.get("val_acc")
        size = ck.get("img_size", 224)
        resize = int(round(size * 256 / 224))
        self.view = transforms.Compose([transforms.Resize(resize), transforms.CenterCrop(size)])
        self.size = size
        self.norm = transforms.Compose([transforms.ToTensor(), transforms.Normalize(ck["mean"], ck["std"])])
        self.bg = self.classes.index(BACKGROUND) if BACKGROUND in self.classes else None
        # Calibration + out-of-distribution detector (present in v3+ checkpoints, see tools/calibrate.py).
        self.temperature = float(ck.get("temperature", 1.0))
        ood = ck.get("ood")
        self.ood = None
        if ood:
            self.ood = {"means": ood["means"].float().to(self.device), "prec": ood["prec"].float().to(self.device),
                        "threshold": float(ood["threshold"]), "method": ood.get("method", "mahalanobis")}
        self.metrics = ck.get("metrics", {})
        self.path = Path(path)
        self.crop_of = [crop_prefix(c) for c in self.classes]
        self.crops = sorted({c for c in self.crop_of if c})
        thr = ROOT / "reports" / "thresholds.json"
        if thr.exists():
            t = json.loads(thr.read_text()).get(self.version, {})
            global PLANT_MIN, PLANT_MARGIN
            PLANT_MIN = t.get("plant_min", PLANT_MIN)
            PLANT_MARGIN = t.get("plant_margin", PLANT_MARGIN)

    def to_cpu(self):
        """Fallback when the GPU is unavailable (e.g. out of memory)."""
        self.device = torch.device("cpu")
        self.model = self.model.to(self.device)
        if self.ood:
            self.ood = {**self.ood, "means": self.ood["means"].cpu(), "prec": self.ood["prec"].cpu()}

    # ---------------------------------------------------------------- helpers
    def _views(self, img: Image.Image):
        center = self.view(img)
        whole = img.resize((self.size, self.size), Image.BILINEAR)
        flip = Image.Transpose.FLIP_LEFT_RIGHT
        return [center, center.transpose(flip), whole, whole.transpose(flip)]

    @torch.no_grad()
    def probabilities(self, img: Image.Image) -> tuple[np.ndarray, float | None]:
        """Test-time augmentation (centre crop + whole image, each mirrored), temperature-scaled.
        Also returns the OOD score of the centre view (higher = less like the training data)."""
        from ml.common import features, last_linear, mahalanobis_score
        xs = torch.stack([self.norm(v) for v in self._views(img)]).to(self.device)
        f = features(self.model, xs).float()
        logits = last_linear(self.model)(f)
        p = F.softmax(logits / self.temperature, 1).mean(0).cpu().numpy()
        score = None
        if self.ood:
            score = float(mahalanobis_score(f[:1], self.ood["means"], self.ood["prec"])[0])
        return p, score

    def gradcam(self, img: Image.Image, cls: int) -> tuple[str, np.ndarray]:
        x = self.norm(self.view(img)).unsqueeze(0).to(self.device)
        feats = {}

        def hook(_, __, out):
            out.retain_grad()
            feats["a"] = out
        layer = self.model.features
        h = layer.register_forward_hook(hook)
        self.model.zero_grad(set_to_none=True)
        try:
            with torch.enable_grad():
                logits = self.model(x)
                logits[0, cls].backward()
        finally:
            h.remove()
        a, g = feats["a"][0], feats["a"].grad[0]
        cam = F.relu((g.mean((1, 2))[:, None, None] * a).sum(0))
        cam = cam / (cam.max() + 1e-8)
        cam = F.interpolate(cam[None, None], size=x.shape[-2:], mode="bilinear", align_corners=False)[0, 0]
        cam = cam.detach().cpu().numpy()
        return self._overlay(self.view(img), cam), cam

    def crop_probs(self, p: np.ndarray) -> dict:
        out = {}
        for i, c in enumerate(self.crop_of):
            if c:
                out[c] = out.get(c, 0.0) + float(p[i])
        return dict(sorted(out.items(), key=lambda kv: -kv[1]))

    # ---------------------------------------------------------------- main API
    def analyze(self, img: Image.Image, crop: str | None = None, topk: int = 5) -> dict:
        """Two-stage analysis. `crop` is a model crop prefix (e.g. 'Tomato') if the user named the plant."""
        img = ImageOps.exif_transpose(img).convert("RGB")
        p, ood_score = self.probabilities(img)
        ood = None
        if self.ood is not None:
            ood = {"score": round(ood_score, 2), "threshold": round(self.ood["threshold"], 2),
                   "out_of_distribution": ood_score > self.ood["threshold"]}
            if ood["out_of_distribution"]:
                # The image is unlike anything the model was trained on: refuse to diagnose.
                return {"status": "unknown", "plant": None, "top": self._rank(p, crop if crop in self.crops else None, topk),
                        "findings": [], "heatmap": None, "healthy": False, "ood": ood,
                        "model_version": self.version}

        bg_p = float(p[self.bg]) if self.bg is not None else 0.0
        if self.bg is not None and int(p.argmax()) == self.bg and bg_p >= BACKGROUND_MIN and not crop:
            heat, _ = self.gradcam(img, self.bg)
            return {"status": "no_leaf", "plant": None, "top": [], "findings": [], "heatmap": heat,
                    "healthy": False, "background_prob": bg_p, "model_version": self.version}

        pc = self.crop_probs(p)
        ranked = list(pc.items())
        plant = {"source": "user" if crop else "image", "candidates": [
            {"crop": c, "prob": round(v / max(1e-8, 1 - bg_p), 4)} for c, v in ranked[:3]]}

        if crop:
            if crop not in self.crops:
                return {"status": "unsupported_crop", "plant": {**plant, "crop": crop, "prob": None},
                        "top": [], "findings": [], "heatmap": None, "healthy": False,
                        "supported_crops": self.crops, "model_version": self.version}
            chosen = crop
            plant["crop"] = crop
            plant["prob"] = round(pc.get(crop, 0.0) / max(1e-8, 1 - bg_p), 4)  # model's agreement with the user
            plant["agrees"] = ranked[0][0] == crop
        else:
            (c1, v1), (_, v2) = ranked[0], (ranked[1] if len(ranked) > 1 else (None, 0.0))
            v1n, v2n = v1 / max(1e-8, 1 - bg_p), v2 / max(1e-8, 1 - bg_p)
            plant["crop"], plant["prob"] = c1, round(v1n, 4)
            if v1n < PLANT_MIN or (v1n - v2n) < PLANT_MARGIN:
                # Not confident about the plant: ask instead of guessing.
                heat, _ = self.gradcam(img, int(p.argmax()))
                return {"status": "needs_input", "plant": plant, "top": self._rank(p, None, topk),
                        "findings": [], "heatmap": heat, "healthy": False, "model_version": self.version}
            chosen = c1

        top = self._rank(p, chosen, topk)
        best = top[0]
        heat, cam = self.gradcam(img, best["index"])
        if best["prob"] < UNCERTAIN:
            status = "uncertain"
        elif best["prob"] < CONFIDENT:
            status = "tentative"
        else:
            status = "confident"
        healthy = best["label"].endswith("healthy")
        findings = [t for t in top[1:] if t["prob"] >= SECONDARY and not t["label"].endswith("healthy")]
        sev = None if healthy or status == "uncertain" else estimate_severity(self.view(img), cam)
        return {"status": status, "plant": plant, "top": top, "findings": findings, "heatmap": heat,
                "healthy": healthy, "severity": sev, "ood": ood, "model_version": self.version}

    def _rank(self, p: np.ndarray, crop: str | None, topk: int) -> list:
        idx = [i for i, c in enumerate(self.crop_of) if c and (crop is None or c == crop)]
        sub = p[idx]
        sub = sub / max(1e-8, sub.sum())
        order = np.argsort(sub)[::-1][:topk]
        out = []
        for j in order:
            i = idx[j]
            c, d = pretty(self.classes[i])
            out.append({"index": int(i), "label": self.classes[i], "crop": c, "disease": d,
                        "prob": float(sub[j]), "joint_prob": float(p[i])})
        return out

    def predict(self, img: Image.Image, topk: int = 5):
        """v1 API shape (kept for backwards compatibility with /api/predict)."""
        r = self.analyze(img, None, topk)
        if r["status"] in ("needs_input", "unknown"):
            r["status"] = "uncertain"
        r.pop("plant", None)
        for t in r["top"]:
            t.pop("index", None)
        if not r["top"]:
            r["top"] = [{"label": BACKGROUND, "crop": "—", "disease": "No plant", "prob": r.get("background_prob", 1.0)}]
        return r

    @staticmethod
    def _overlay(img: Image.Image, cam: np.ndarray) -> str:
        base = np.asarray(img).astype(np.float32) / 255.0
        c = cam[..., None]
        color = np.concatenate([np.ones_like(c) * 0.95, 0.85 - 0.65 * c, 0.15 * (1 - c)], -1)
        alpha = np.clip((c - 0.25) / 0.75, 0, 1) * 0.65
        out = base * (1 - alpha) + color * alpha
        buf = io.BytesIO()
        Image.fromarray((out * 255).astype(np.uint8)).save(buf, "JPEG", quality=88)
        return "data:image/jpeg;base64," + base64.b64encode(buf.getvalue()).decode()


# ---------------------------------------------------------------- severity
SEVERITY_BANDS = [(0.05, "Low"), (0.15, "Moderate"), (0.35, "High"), (1.01, "Critical")]


def estimate_severity(img: Image.Image, cam: np.ndarray | None = None) -> dict:
    """Visual estimate of the share of visible plant tissue that looks symptomatic.

    Plant tissue = pixels that are reasonably saturated and not near-white/near-black background.
    Symptomatic = plant pixels whose hue is outside the healthy-green band (yellow, brown, black
    lesions, white powdery growth inside the leaf). This is a heuristic on ONE photo: it says
    nothing about how much of the field is affected, and is labelled as such in the UI.
    """
    hsv = np.asarray(img.convert("HSV")).astype(np.float32)
    h, s, v = hsv[..., 0] * 360 / 255, hsv[..., 1] / 255, hsv[..., 2] / 255
    green = (h >= 55) & (h <= 170) & (s >= 0.18) & (v >= 0.15)
    lesion_colour = ((h < 55) | (h > 170)) & (s >= 0.15) & (v >= 0.08) & (v <= 0.95)   # yellow/brown/red
    dark = (v < 0.22)                                                                 # necrotic/black
    powdery = (s < 0.12) & (v > 0.75)                                                 # white growth
    # Restrict dark / powdery pixels to the neighbourhood of green tissue (i.e. inside the leaf).
    near_leaf = np.asarray(Image.fromarray(green.astype(np.uint8) * 255).filter(ImageFilter.MaxFilter(13))) > 0
    lesion = lesion_colour | ((dark | powdery) & near_leaf)
    if cam is not None:
        # Down-weight lesion-coloured pixels the model did not attend to at all (e.g. soil, pots).
        lesion &= (cam > 0.15) | near_leaf
    plant = green | lesion
    n_plant = int(plant.sum())
    if n_plant < 0.05 * plant.size:
        return {"level": None, "affected_pct": None, "method": "lesion-area estimate",
                "note": "Too little plant tissue visible to estimate severity."}
    frac = float(lesion.sum()) / n_plant
    level = next(lbl for th, lbl in SEVERITY_BANDS if frac < th)
    return {"level": level, "affected_pct": round(frac * 100, 1), "method": "lesion-area estimate",
            "validated": False,
            "note": "Experimental: colour-based estimate from this photo only, not validated against expert "
                    "severity ratings. Not shown to users as a diagnosis."}


# ---------------------------------------------------------------- pest model (IP102)
class PestPredictor:
    """Optional insect-pest classifier (102 IP102 classes). Loaded only if the weights exist."""

    def __init__(self, path: Path = PEST_MODEL_PATH):
        ck = torch.load(path, map_location="cpu", weights_only=False)
        self.classes = ck["classes"]
        self.version = ck.get("version") or Path(path).stem
        self.metrics = ck.get("metrics", {})
        self.temperature = float(ck.get("temperature", 1.0))
        self.path = Path(path)
        self.device = pick_device()
        m = _build(ck.get("arch", "efficientnet_b0"), len(self.classes))
        m.load_state_dict(ck["state_dict"])
        self.model = m.eval().to(self.device)
        size = ck.get("img_size", 224)
        self.tf = transforms.Compose([transforms.Resize(int(size * 256 / 224)), transforms.CenterCrop(size),
                                      transforms.ToTensor(), transforms.Normalize(ck["mean"], ck["std"])])

    @torch.no_grad()
    def predict(self, img: Image.Image, topk: int = 5) -> list:
        img = ImageOps.exif_transpose(img).convert("RGB")
        x = torch.stack([self.tf(img), self.tf(img.transpose(Image.Transpose.FLIP_LEFT_RIGHT))]).to(self.device)
        p = F.softmax(self.model(x).float() / self.temperature, 1).mean(0).cpu().numpy()
        order = p.argsort()[::-1][:topk]
        return [{"label": self.classes[i], "prob": float(p[i])} for i in order]
