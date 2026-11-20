"""Train + evaluate a disease model on the grouped v3 split (ml/prepare_split.py).

    .venv/bin/python ml/train_disease.py --arch efficientnet_b0 --epochs 3 --subset 400 --tag cmp   # quick comparison
    .venv/bin/python ml/train_disease.py --arch efficientnet_b2 --size 260 --epochs 10               # full run

Outputs  runs/<run>/ (history, metrics, confusion) and, for full runs, models/plantdoctor_v3_<arch>.pt
with classes, temperature, OOD statistics and metrics, plus an entry in models/registry.json.

Evaluation (all on data never used for training):
  * test split (grouped, leakage-checked): accuracy, macro/weighted P/R/F1, per-class, confusion,
    ROC-AUC (OvR), ECE before/after temperature scaling, reliability table
  * external field set (PlantDoc test photos, other photographers/cameras/backgrounds)
  * robustness: test images under brightness / blur / JPEG / low-resolution / crop shifts
  * OOD: Mahalanobis threshold at 95 % TPR on val; AUROC vs. synthetic and non-plant negatives
  * latency (GPU and CPU, batch 1) and model size
"""
from __future__ import annotations

import argparse
import io
import json
import random
import re
from functools import partial
import sys
import time
from pathlib import Path

import numpy as np
import torch
from PIL import Image, ImageEnhance, ImageFilter
from torch.utils.data import Dataset

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from ml.common import (MEAN, STD, ImageListDataset, auroc, balanced_sampler, build_model, dump_metrics,  # noqa: E402
                       eval_transform, evaluate, features, fit, fit_mahalanobis, fit_temperature, last_linear,
                       latency_ms, loader, mahalanobis_score, predict_logits, seed_everything, train_transform)

DATA = ROOT / "data"
SPLIT = ROOT / "reports" / "v3" / "split.json"
FIELD = DATA / "plantdoc_test"
# PlantDoc folder -> v3 class label
FIELD_MAP = {
    "Apple Scab Leaf": "Apple___Apple_scab", "Apple leaf": "Apple___healthy", "Apple rust leaf": "Apple___Cedar_apple_rust",
    "Bell_pepper leaf spot": "Pepper,_bell___Bacterial_spot", "Bell_pepper leaf": "Pepper,_bell___healthy",
    "Blueberry leaf": "Blueberry___healthy", "Cherry leaf": "Cherry___healthy",
    "Corn Gray leaf spot": "Corn___Cercospora_leaf_spot Gray_leaf_spot", "Corn leaf blight": "Corn___Northern_Leaf_Blight",
    "Corn rust leaf": "Corn___Common_rust", "Peach leaf": "Peach___healthy", "Potato leaf early blight": "Potato___Early_blight",
    "Potato leaf late blight": "Potato___Late_blight", "Raspberry leaf": "Raspberry___healthy", "Soyabean leaf": "Soybean___healthy",
    "Squash Powdery mildew leaf": "Squash___Powdery_mildew", "Strawberry leaf": "Strawberry___healthy",
    "Tomato Early blight leaf": "Tomato___Early_blight", "Tomato Septoria leaf spot": "Tomato___Septoria_leaf_spot",
    "Tomato leaf bacterial spot": "Tomato___Bacterial_spot", "Tomato leaf late blight": "Tomato___Late_blight",
    "Tomato leaf mosaic virus": "Tomato___Tomato_mosaic_virus", "Tomato leaf yellow virus": "Tomato___Tomato_Yellow_Leaf_Curl_Virus",
    "Tomato leaf": "Tomato___healthy", "Tomato mold leaf": "Tomato___Leaf_Mold", "grape leaf black rot": "Grape___Black_rot",
    "grape leaf": "Grape___healthy",
}
def _bright(im, f):
    return ImageEnhance.Brightness(im).enhance(f)


def _blur(im, r):
    return im.filter(ImageFilter.GaussianBlur(r))


def _lowres(im, px):
    return im.resize((px, px)).resize(im.size)


def _crop(im, frac):
    m = (1 - frac) / 2
    return im.crop((int(im.width * m), int(im.height * m), int(im.width * (1 - m)), int(im.height * (1 - m))))


# Module-level callables (picklable for DataLoader workers under the forkserver start method).
SHIFTS = {
    "brightness_0.5": partial(_bright, f=0.5), "brightness_1.6": partial(_bright, f=1.6),
    "blur_r2": partial(_blur, r=2), "jpeg_q20": None, "lowres_96px": partial(_lowres, px=96),
    "center_crop_60": partial(_crop, frac=0.6),
}


def _jpeg(im, q):
    b = io.BytesIO()
    im.convert("RGB").save(b, "JPEG", quality=q)
    return Image.open(io.BytesIO(b.getvalue())).convert("RGB")


SHIFTS["jpeg_q20"] = partial(_jpeg, q=20)


class ShiftDataset(Dataset):
    def __init__(self, base: ImageListDataset, fn):
        self.base, self.fn = base, fn

    def __len__(self):
        return len(self.base)

    def __getitem__(self, i):
        f, y = self.base.items[i]
        with Image.open(self.base.root / f) as im:
            return self.base.tf(self.fn(im.convert("RGB"))), y


class NoiseDataset(Dataset):
    """Synthetic out-of-distribution negatives: noise, flat colours, gradients."""
    def __init__(self, n, tf, seed=0):
        self.n, self.tf, self.rng = n, tf, np.random.default_rng(seed)
        self.imgs = []
        for i in range(n):
            k = i % 3
            if k == 0:
                a = self.rng.integers(0, 255, (256, 256, 3))
            elif k == 1:
                a = np.ones((256, 256, 3)) * self.rng.integers(0, 255, 3)
            else:
                a = np.linspace(0, 255, 256)[None, :, None] * np.ones((256, 1, 3)) * self.rng.random(3)
            self.imgs.append(Image.fromarray(a.astype("uint8")))

    def __len__(self):
        return self.n

    def __getitem__(self, i):
        return self.tf(self.imgs[i]), -1


def field_items(classes):
    idx = {c: i for i, c in enumerate(classes)}
    items = []
    for folder, label in FIELD_MAP.items():
        if label not in idx:
            continue
        for f in sorted((FIELD / folder).glob("*")):
            try:
                with Image.open(f) as im:
                    im.verify()
                items.append((str(f.relative_to(DATA)), idx[label]))
            except Exception:
                pass
    return items


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--arch", default="efficientnet_b0")
    ap.add_argument("--size", type=int, default=224)
    ap.add_argument("--epochs", type=int, default=10)
    ap.add_argument("--batch", type=int, default=48)
    ap.add_argument("--lr", type=float, default=1e-3)
    ap.add_argument("--workers", type=int, default=6)
    ap.add_argument("--seed", type=int, default=42)
    ap.add_argument("--subset", type=int, default=0, help="max train images per class (quick comparison runs)")
    ap.add_argument("--field-weight", type=float, default=2.0, help="sampling weight of non-PlantVillage images")
    ap.add_argument("--patience", type=int, default=3)
    ap.add_argument("--epoch-size", type=int, default=0, help="samples per epoch (0 = len(train)); sampler draws with replacement")
    ap.add_argument("--tag", default="full")
    ap.add_argument("--split", default=str(SPLIT))
    ap.add_argument("--cpu", action="store_true")
    a = ap.parse_args()
    seed_everything(a.seed)
    dev = torch.device("cpu" if a.cpu or not torch.cuda.is_available() else "cuda")
    torch.backends.cudnn.benchmark = True
    sp = json.loads(Path(a.split).read_text())
    classes = sp["classes"]
    rnd = random.Random(a.seed)
    train = sp["train"]
    if a.subset:
        by = {}
        for it in train:
            by.setdefault(it[1], []).append(it)
        train = [x for v in by.values() for x in rnd.sample(v, min(len(v), a.subset))]
    run = ROOT / "runs" / f"{time.strftime('%Y%m%d-%H%M')}_{a.arch}_{a.size}_{a.tag}"
    run.mkdir(parents=True, exist_ok=True)
    (run / "config.json").write_text(json.dumps({**vars(a), "split_sha": sp["sha"], "n_train": len(train),
                                                 "n_val": len(sp["val"]), "n_test": len(sp["test"]), "classes": len(classes)}, indent=1))
    print(f"{a.arch}@{a.size} | {len(classes)} classes | train {len(train)} val {len(sp['val'])} test {len(sp['test'])} | {run.name}", flush=True)

    tr = [(f, y) for f, y, _ in train]
    w = [a.field_weight if src != "plantvillage" else 1.0 for _, _, src in train]
    train_dl = loader(ImageListDataset(DATA, tr, train_transform(a.size)), a.batch, a.workers,
                      sampler=balanced_sampler([y for _, y in tr], 0.5, w, a.epoch_size or None))
    ev = eval_transform(a.size)
    val_ds = ImageListDataset(DATA, [(f, y) for f, y, _ in sp["val"]], ev)
    test_ds = ImageListDataset(DATA, [(f, y) for f, y, _ in sp["test"]], ev)
    val_dl, test_dl = loader(val_ds, a.batch * 2, a.workers), loader(test_ds, a.batch * 2, a.workers)

    model = build_model(a.arch, len(classes)).to(dev)
    t0 = time.time()
    model, hist, best = fit(model, train_dl, val_dl, dev, a.epochs, a.lr, run, patience=a.patience, classes=classes)
    train_min = round((time.time() - t0) / 60, 1)

    # calibration on val
    vl, vy, vf = predict_logits(model, val_dl, dev, with_features=True)
    T = fit_temperature(vl, vy)
    tl, ty, tfeat = predict_logits(model, test_dl, dev, with_features=True)
    raw = evaluate(tl, ty, classes)
    m = evaluate(tl, ty, classes, temperature=T)
    m.update({"temperature": T, "ece_uncalibrated": raw["ece"], "train_minutes": train_min, "best_val_macro_f1": best})

    # OOD: Mahalanobis on penultimate features; threshold = 95th percentile of val scores (95 % TPR)
    trl, try_, trf = predict_logits(model, loader(ImageListDataset(DATA, tr[:: max(1, len(tr) // 20000)], ev),
                                                  a.batch * 2, a.workers), dev, with_features=True)
    means, prec = fit_mahalanobis(trf, try_, len(classes))
    val_scores = mahalanobis_score(vf, means, prec).numpy()
    thr = float(np.percentile(val_scores, 95))
    noise_dl = loader(NoiseDataset(300, ev), 64, 0)
    _, _, nf = predict_logits(model, noise_dl, dev, with_features=True)
    test_scores = mahalanobis_score(tfeat, means, prec).numpy()
    noise_scores = mahalanobis_score(nf, means, prec).numpy()
    ood = {"threshold": thr, "tpr_val": 0.95, "test_in_dist_accept_rate": float((test_scores <= thr).mean()),
           "noise_reject_rate": float((noise_scores > thr).mean()),
           "auroc_test_vs_noise": auroc(-test_scores, -noise_scores)}
    bg = classes.index("Background_without_leaves") if "Background_without_leaves" in classes else None
    if bg is not None:
        nonplant = (ty == bg).numpy()
        ood["background_class_note"] = f"'no plant' photos are a trained class ({int(nonplant.sum())} in test)"
    m["ood"] = ood

    # external field set
    fi = field_items(classes)
    if fi:
        fl, fy = predict_logits(model, loader(ImageListDataset(DATA, fi, ev), a.batch * 2, a.workers), dev)
        fm = evaluate(fl, fy, classes, temperature=T)
        crop = lambda c: classes[c].split("___")[0]
        pred = fl.argmax(1).numpy()
        m["field"] = {"n": fm["n"], "accuracy": fm["accuracy"], "top5_accuracy": fm["top5_accuracy"],
                      "macro_f1_present": float(np.mean([v["f1"] for v in fm["per_class"].values() if v["support"]])),
                      "crop_accuracy": float(np.mean([crop(p) == crop(t) for p, t in zip(pred, fy.numpy())])), "ece": fm["ece"]}

    # robustness
    rob = {}
    sub = ImageListDataset(DATA, test_ds.items[:: max(1, len(test_ds) // 3000)], ev)
    for name, fn in SHIFTS.items():
        sl, sy = predict_logits(model, loader(ShiftDataset(sub, fn), a.batch * 2, a.workers), dev)
        r = evaluate(sl, sy, classes, temperature=T)
        rob[name] = {"accuracy": r["accuracy"], "macro_f1": r["macro_f1"], "ece": r["ece"]}
    bl, by_ = predict_logits(model, loader(sub, a.batch * 2, a.workers), dev)
    rob["clean_subset"] = {"accuracy": evaluate(bl, by_, classes, temperature=T)["accuracy"]}
    m["robustness"] = rob

    m["latency_ms_gpu"] = latency_ms(model, a.size, dev) if dev.type == "cuda" else None
    m["latency_ms_cpu"] = latency_ms(model.cpu(), a.size, torch.device("cpu"), runs=15)
    m["params_m"] = round(sum(p.numel() for p in model.parameters()) / 1e6, 2)
    dump_metrics(m, run / "test_metrics.json")
    (run / "history.json").write_text(json.dumps(hist, indent=1))
    brief = {k: m[k] for k in ("accuracy", "macro_f1", "weighted_f1", "top5_accuracy", "ece", "ece_uncalibrated",
                               "roc_auc_ovr_macro", "latency_ms_cpu", "latency_ms_gpu", "params_m", "n")}
    brief["field"] = m.get("field")
    brief["ood"] = ood
    print("RESULT", json.dumps(brief), flush=True)

    if a.tag == "full":
        model = model.cpu()
        version = f"v3-{a.arch}-{time.strftime('%Y%m%d')}"
        path = ROOT / "models" / f"plantdoctor_v3_{a.arch}.pt"
        torch.save({"arch": a.arch, "classes": classes, "mean": MEAN, "std": STD, "img_size": a.size,
                    "state_dict": model.state_dict(), "temperature": T, "version": version,
                    "ood": {"means": means.float(), "prec": prec.float(), "threshold": thr, "method": "mahalanobis"},
                    "metrics": {**{k: v for k, v in brief.items() if not isinstance(v, dict)},
                                "field_accuracy": (m.get("field") or {}).get("accuracy"),
                                "field_crop_accuracy": (m.get("field") or {}).get("crop_accuracy")},
                    "split_sha": sp["sha"], "run": run.name}, path)
        reg_p = ROOT / "models" / "registry.json"
        reg = json.loads(reg_p.read_text()) if reg_p.exists() else {}
        reg[version] = {"artifact": str(path.relative_to(ROOT)), "arch": a.arch, "img_size": a.size, "classes": len(classes),
                        "split_sha": sp["sha"], "run": run.name, "metrics": brief, "created": time.strftime("%Y-%m-%d %H:%M")}
        reg_p.write_text(json.dumps(reg, indent=1))
        print(f"saved {path} as {version}", flush=True)


if __name__ == "__main__":
    main()
