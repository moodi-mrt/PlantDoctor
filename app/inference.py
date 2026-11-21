"""Model loading, prediction and Grad-CAM explanation."""
import base64
import io
from pathlib import Path

import numpy as np
import torch
import torch.nn as nn
import torch.nn.functional as F
from PIL import Image
from torchvision import models, transforms

from app.small_cnn import SmallCNN

ROOT = Path(__file__).resolve().parent.parent
MODEL_PATH = ROOT / "models" / "plantdoctor_effnetb0.pt"

BACKGROUND = "Background_without_leaves"
CONFIDENT = 0.70
UNCERTAIN = 0.40
BACKGROUND_MIN = 0.60


def pretty(name: str):
    """'Tomato___Early_blight' -> ('Tomato', 'Early blight')."""
    if "___" not in name:
        return "—", name.replace("_", " ")
    crop, dis = name.split("___", 1)
    crop = crop.replace("_", " ").replace(",", "").replace("(including sour)", "").strip()
    crop = crop.replace("Pepper bell", "Bell pepper").replace("Corn (maize)", "Corn (maize)")
    dis = dis.replace("_", " ").replace("  ", " ").strip()
    dis = DISPLAY.get(dis, dis)
    return crop, dis[0].upper() + dis[1:]


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


class Predictor:
    def __init__(self, path: Path = MODEL_PATH):
        path = Path(path)
        if not path.exists():
            raise FileNotFoundError(f"Model checkpoint not found at: {path.resolve()}")
        ck = torch.load(path, map_location="cpu", weights_only=False)
        self.classes = ck["classes"]
        self.device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
        if ck.get("arch", "efficientnet_b0") == "small_cnn":
            m = SmallCNN(len(self.classes))
        else:
            m = models.efficientnet_b0(weights=None)
            m.classifier = nn.Sequential(nn.Dropout(0.3), nn.Linear(m.classifier[1].in_features, len(self.classes)))
        m.load_state_dict(ck["state_dict"])
        self.model = m.eval().to(self.device)
        self.val_acc = ck.get("val_acc")
        size = ck.get("img_size", 224)
        self.tf = transforms.Compose([
            transforms.Resize(256), transforms.CenterCrop(size),
            transforms.ToTensor(), transforms.Normalize(ck["mean"], ck["std"]),
        ])
        self.view = transforms.Compose([transforms.Resize(256), transforms.CenterCrop(size)])
        self.size = size
        self.norm = transforms.Compose([transforms.ToTensor(), transforms.Normalize(ck["mean"], ck["std"])])
        self.bg = self.classes.index(BACKGROUND) if BACKGROUND in self.classes else None

    def _views(self, img: Image.Image):
        center = self.view(img)
        whole = img.resize((self.size, self.size), Image.BILINEAR)
        flip = Image.Transpose.FLIP_LEFT_RIGHT
        return [center.transpose(flip), whole, whole.transpose(flip)]

    def predict(self, img: Image.Image, topk: int = 5):
        img = img.convert("RGB")
        x = self.tf(img).unsqueeze(0).to(self.device)

        with torch.no_grad():
            xs = torch.stack([self.norm(v) for v in self._views(img)]).to(self.device)
            tta_probs = F.softmax(self.model(xs), 1)

        feats = {}
        def hook(_, __, out):
            out.retain_grad()
            feats["a"] = out
        h = self.model.features.register_forward_hook(hook)
        self.model.zero_grad(set_to_none=True)
        with torch.enable_grad():
            logits = self.model(x)
            probs = torch.cat([F.softmax(logits, 1), tta_probs]).mean(0)
            p = probs.detach().cpu().numpy()
            if self.bg is not None and not (p.argmax() == self.bg and p[self.bg] >= BACKGROUND_MIN):
                p = p.copy()
                p[self.bg] = 0.0
                s = p.sum()
                if s > 0:
                    p /= s
            winner = int(p.argmax())
            logits[0, winner].backward()
        h.remove()

        a, g = feats["a"][0], feats["a"].grad[0]
        cam = F.relu((g.mean((1, 2))[:, None, None] * a).sum(0))
        cam = cam / (cam.max() + 1e-8)
        cam = F.interpolate(cam[None, None], size=x.shape[-2:], mode="bilinear", align_corners=False)[0, 0]
        heat = self._overlay(self.view(img), cam.detach().cpu().numpy())

        order = p.argsort()[::-1][:topk]
        preds = []
        for i in order:
            crop, dis = pretty(self.classes[i])
            preds.append({"label": self.classes[i], "crop": crop, "disease": dis, "prob": float(p[i])})

        best = preds[0]
        if best["label"] == BACKGROUND:
            status = "no_leaf"
        elif best["prob"] < UNCERTAIN:
            status = "uncertain"
        elif best["prob"] < CONFIDENT:
            status = "tentative"
        else:
            status = "confident"
        return {"status": status, "top": preds, "heatmap": heat,
                "healthy": best["label"].endswith("healthy")}

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
