"""Generate report figures into reports/figures/."""
import base64
import io
import json
import random
import sys
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
from PIL import Image  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from app.inference import Predictor, pretty  # noqa: E402

R = ROOT / "reports"; F = R / "figures"; F.mkdir(parents=True, exist_ok=True)
INK, INK2, GRID, BRAND, WARN, BAD = "#17201a", "#5b655e", "#e6e5de", "#2c6b40", "#c98a12", "#b8452f"
plt.rcParams.update({"font.family": "DejaVu Sans", "font.size": 9, "axes.edgecolor": GRID, "axes.labelcolor": INK2,
                     "xtick.color": INK2, "ytick.color": INK2, "axes.spines.top": False, "axes.spines.right": False,
                     "axes.grid": True, "grid.color": GRID, "grid.linewidth": .6, "axes.titleweight": "bold",
                     "axes.titlesize": 10, "axes.titlecolor": INK, "axes.titlelocation": "left"})


def short(label):
    c, d = pretty(label)
    return f"{c} – {d}" if c != "—" else "Background (no leaf)"


def curves():
    h = json.load(open(R / "history.json"))
    e = [x["epoch"] for x in h]
    fig, ax = plt.subplots(1, 2, figsize=(7.2, 2.6))
    ax[0].plot(e, [x["train_loss"] for x in h], "-o", ms=3, color=INK2, label="train")
    ax[0].plot(e, [x["val_loss"] for x in h], "-o", ms=3, color=BRAND, label="validation")
    ax[0].set_title("Loss"); ax[0].set_xlabel("epoch"); ax[0].legend(frameon=False)
    ax[1].plot(e, [x["train_acc"] * 100 for x in h], "-o", ms=3, color=INK2, label="train")
    ax[1].plot(e, [x["val_acc"] * 100 for x in h], "-o", ms=3, color=BRAND, label="validation")
    ax[1].set_title("Accuracy (%)"); ax[1].set_xlabel("epoch"); ax[1].legend(frameon=False)
    for a in ax: a.set_xticks(e)
    fig.tight_layout(); fig.savefig(F / "curves.png", dpi=220); plt.close(fig)


def confusion():
    cm = np.load(R / "confusion_matrix.npy").astype(float)
    classes = json.load(open(R / "split.json"))["classes"]
    cmn = cm / cm.sum(1, keepdims=True)
    fig, ax = plt.subplots(figsize=(7.2, 6.6))
    ax.imshow(cmn, cmap="Greens", vmin=0, vmax=1)
    off = cm.copy(); np.fill_diagonal(off, 0)
    for i, j in zip(*np.nonzero(off)):
        ax.text(j, i, int(off[i, j]), ha="center", va="center", fontsize=5.5, color=BAD, fontweight="bold")
    lab = [short(c) for c in classes]
    ax.set_xticks(range(len(lab))); ax.set_xticklabels(lab, rotation=90, fontsize=5.2)
    ax.set_yticks(range(len(lab))); ax.set_yticklabels(lab, fontsize=5.2)
    ax.set_xlabel("predicted"); ax.set_ylabel("true"); ax.grid(False)
    ax.set_title("Confusion matrix — PlantVillage test split")
    fig.tight_layout(); fig.savefig(F / "confusion.png", dpi=220); plt.close(fig)


def class_dist():
    c = json.load(open(R / "class_counts_train.json"))
    items = sorted(c.items(), key=lambda kv: kv[1])
    fig, ax = plt.subplots(figsize=(7.2, 5.6))
    ax.barh([short(k) for k, _ in items], [v for _, v in items], color=BRAND, height=.7)
    ax.set_title("Training images per class"); ax.tick_params(axis="y", labelsize=6); ax.grid(axis="y", visible=False)
    fig.tight_layout(); fig.savefig(F / "class_dist.png", dpi=220); plt.close(fig)


def lab_vs_field():
    t = json.load(open(R / "test_metrics.json")); f = json.load(open(R / "field_metrics.json"))
    fig, ax = plt.subplots(figsize=(7.2, 2.9))
    names = ["Exact disease (top-1)", "Correct in top-5", "Correct crop"]
    lab = [t["test_acc"] * 100, t.get("top5_acc", t["test_acc"]) * 100, t.get("crop_acc", t["test_acc"]) * 100]
    fld = [f["top1_acc"] * 100, f["top5_acc"] * 100, f["crop_acc"] * 100]
    x = np.arange(3); w = .36
    b1 = ax.bar(x - w / 2, lab, w, color=BRAND, label="Lab photos (PlantVillage test)")
    b2 = ax.bar(x + w / 2, fld, w, color=WARN, label="Field photos (PlantDoc)")
    for b in [*b1, *b2]:
        ax.text(b.get_x() + b.get_width() / 2, b.get_height() + 1.5, f"{b.get_height():.0f}%", ha="center", fontsize=8, color=INK)
    ax.set_xticks(x); ax.set_xticklabels(names); ax.set_ylim(0, 108); ax.set_yticks([0, 25, 50, 75, 100])
    ax.legend(frameon=False, loc="upper center", bbox_to_anchor=(.5, -.14), ncol=2, fontsize=8); ax.grid(axis="x", visible=False)
    ax.set_title("Same model, two kinds of photo")
    fig.tight_layout(); fig.savefig(F / "lab_vs_field.png", dpi=220); plt.close(fig)


def gradcam_grid(n=4, seed=3):
    pr = Predictor()
    sp = json.load(open(R / "split.json"))
    data_dir = Path(sp["data_dir"])
    rng = random.Random(seed)
    lab = [f for f, y in sp["test"] if "healthy" not in sp["classes"][y].lower() and "Background" not in sp["classes"][y]]
    field = sorted((ROOT / "data" / "plantdoc_test").glob("*/*"))
    picks = [("Lab", data_dir / p) for p in rng.sample(lab, n)] + [("Field", p) for p in rng.sample(field, n)]
    fig, ax = plt.subplots(2, n, figsize=(7.2, 4.8))
    for k, (kind, path) in enumerate(picks):
        img = Image.open(path).convert("RGB")
        r = pr.predict(img)
        heat = Image.open(io.BytesIO(base64.b64decode(r["heatmap"].split(",", 1)[1])))
        a = ax[k // n, k % n]; a.imshow(heat); a.axis("off")
        c, d = r["top"][0]["crop"], r["top"][0]["disease"]
        d = d if len(d) < 24 else d[:22] + "…"
        a.set_title(f"{kind} · {c}\n{d} · {r['top'][0]['prob']*100:.0f}%", fontsize=6.2, fontweight="normal", loc="center")
    fig.suptitle("Grad-CAM: warm areas drove the prediction (top: lab, bottom: field)", fontsize=9, x=.02, ha="left", fontweight="bold")
    fig.tight_layout(); fig.savefig(F / "gradcam.png", dpi=220); plt.close(fig)


def samples(seed=1):
    sp = json.load(open(R / "split.json")); data_dir = Path(sp["data_dir"])
    rng = random.Random(seed)
    lab = rng.sample(sp["test"], 4)
    field = rng.sample(sorted((ROOT / "data" / "plantdoc_test").glob("*/*")), 4)
    fig, ax = plt.subplots(2, 4, figsize=(7.2, 3.9))
    for k, (f, y) in enumerate(lab):
        a = ax[0, k]; a.imshow(Image.open(data_dir / f).convert("RGB").resize((256, 256))); a.axis("off")
        a.set_title(short(sp["classes"][y])[:30], fontsize=6.2, fontweight="normal", loc="center")
    for k, p in enumerate(field):
        im = Image.open(p).convert("RGB"); s = min(im.size)
        im = im.crop(((im.width - s) // 2, (im.height - s) // 2, (im.width + s) // 2, (im.height + s) // 2)).resize((256, 256))
        a = ax[1, k]; a.imshow(im); a.axis("off"); a.set_title(p.parent.name[:30], fontsize=6.2, fontweight="normal", loc="center")
    fig.suptitle("Top: PlantVillage (training domain)    Bottom: PlantDoc (real-world field photos)", fontsize=9, x=.02, ha="left", fontweight="bold")
    fig.tight_layout(); fig.savefig(F / "samples.png", dpi=220); plt.close(fig)


if __name__ == "__main__":
    curves(); confusion(); class_dist(); lab_vs_field(); samples(); gradcam_grid()
    print("figures ->", F)
