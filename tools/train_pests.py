"""Train the insect-pest classifier on IP102 (official train / val / test split).

    .venv/bin/python tools/train_pests.py --arch efficientnet_b0 --epochs 12

Outputs: models/pest_<arch>.pt (weights, classes, temperature, metrics) and
reports/pests/<arch>/{history,test_metrics,...}.json. IP102 is licensed for academic use.
"""
import argparse
import json
import sys
import time
from pathlib import Path

import torch

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from ml.common import (MEAN, STD, ImageListDataset, balanced_sampler, build_model, dump_metrics,  # noqa: E402
                       eval_transform, evaluate, fit, fit_temperature, latency_ms, loader,
                       predict_logits, seed_everything, train_transform)

DATA = ROOT / "data" / "pests"


def items(split, classes):
    idx = {c: i for i, c in enumerate(classes)}
    return [(str(f.relative_to(DATA)), idx[f.parent.name]) for f in sorted((DATA / split).rglob("*.jpg"))]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--arch", default="efficientnet_b0")
    ap.add_argument("--size", type=int, default=224)
    ap.add_argument("--epochs", type=int, default=12)
    ap.add_argument("--batch", type=int, default=48)
    ap.add_argument("--lr", type=float, default=1e-3)
    ap.add_argument("--workers", type=int, default=6)
    ap.add_argument("--seed", type=int, default=42)
    a = ap.parse_args()
    seed_everything(a.seed)
    dev = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    torch.backends.cudnn.benchmark = True
    names = json.loads((DATA / "classes.json").read_text())
    classes = sorted(d.name for d in (DATA / "train").iterdir() if d.is_dir())
    tr, va, te = items("train", classes), items("val", classes), items("test", classes)
    print(f"IP102: {len(classes)} classes | train {len(tr)} val {len(va)} test {len(te)} | {dev}", flush=True)
    out = ROOT / "reports" / "pests" / a.arch
    out.mkdir(parents=True, exist_ok=True)

    train_dl = loader(ImageListDataset(DATA, tr, train_transform(a.size)), a.batch, a.workers,
                      sampler=balanced_sampler([y for _, y in tr], power=0.5))
    val_dl = loader(ImageListDataset(DATA, va, eval_transform(a.size)), a.batch * 2, a.workers)
    test_dl = loader(ImageListDataset(DATA, te, eval_transform(a.size)), a.batch * 2, a.workers)

    model = build_model(a.arch, len(classes)).to(dev)
    t0 = time.time()
    model, hist, best = fit(model, train_dl, val_dl, dev, a.epochs, a.lr, out, classes=classes)
    vl, vy = predict_logits(model, val_dl, dev)
    T = fit_temperature(vl, vy)
    tl, ty = predict_logits(model, test_dl, dev)
    m_raw = evaluate(tl, ty, classes)
    m = evaluate(tl, ty, classes, temperature=T)
    m.update({"temperature": T, "ece_uncalibrated": m_raw["ece"], "train_minutes": round((time.time() - t0) / 60, 1),
              "latency_ms_gpu": latency_ms(model, a.size, dev) if dev.type == "cuda" else None,
              "latency_ms_cpu": latency_ms(model.cpu(), a.size, torch.device("cpu"), runs=10)})
    dump_metrics(m, out / "test_metrics.json")
    display = {c: names[int(c.split("_", 1)[0])] for c in classes}
    version = f"pest-{a.arch}-{time.strftime('%Y%m%d')}"
    torch.save({"arch": a.arch, "classes": [display[c] for c in classes], "mean": MEAN, "std": STD,
                "img_size": a.size, "state_dict": model.state_dict(), "temperature": T, "version": version,
                "metrics": {k: m[k] for k in ("accuracy", "top5_accuracy", "macro_f1", "ece", "n")},
                "dataset": "IP102 (Wu et al., CVPR 2019) — academic use"},
               ROOT / "models" / f"pest_{a.arch}.pt")
    print(f"TEST acc {m['accuracy']:.4f} top5 {m['top5_accuracy']:.4f} macroF1 {m['macro_f1']:.4f} "
          f"ECE {m_raw['ece']:.4f} -> {m['ece']:.4f} (T={T:.2f})", flush=True)


if __name__ == "__main__":
    main()
