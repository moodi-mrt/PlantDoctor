"""Benchmark SmallCNN vs EfficientNet-B0 checkpoints with Total, Lab, and Field accuracy."""
import argparse
import json
import sys
import time
from pathlib import Path

import numpy as np
import torch
import torch.nn as nn
import torch.nn.functional as F
from PIL import Image
from torchvision import models, transforms

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from app.inference import BACKGROUND, BACKGROUND_MIN
from app.small_cnn import SmallCNN

DEFAULT_MODELS = [
    ("SmallCNN (Scratch)", ROOT / "models" / "plantdoctor_smallcnn.pt"),
    ("EfficientNet-B0 v1 (PV)", ROOT / "models" / "plantdoctor_effnetb0_v1_plantvillage.pt"),
    ("EfficientNet-B0 v2 (Current)", ROOT / "models" / "plantdoctor_effnetb0.pt"),
]


def load_checkpoint(path: Path, device: torch.device):
    ck = torch.load(path, map_location="cpu", weights_only=False)
    classes = ck["classes"]
    if ck.get("arch", "efficientnet_b0") == "small_cnn":
        model = SmallCNN(len(classes))
    else:
        model = models.efficientnet_b0(weights=None)
        model.classifier = nn.Sequential(nn.Dropout(0.3), nn.Linear(model.classifier[1].in_features, len(classes)))
    model.load_state_dict(ck["state_dict"])
    model.eval().to(device)
    return model, ck


@torch.no_grad()
def predict_4view(model, img: Image.Image, size: int, mean, std, device: torch.device, bg_idx):
    view = transforms.Compose([transforms.Resize(256), transforms.CenterCrop(size)])
    norm = transforms.Compose([transforms.ToTensor(), transforms.Normalize(mean, std)])
    flip = Image.Transpose.FLIP_LEFT_RIGHT
    center = view(img)
    whole = img.resize((size, size), Image.BILINEAR)
    xs = torch.stack([norm(v) for v in [center, center.transpose(flip), whole, whole.transpose(flip)]]).to(device)
    probs = F.softmax(model(xs), dim=1).mean(0).cpu().numpy()
    if bg_idx is not None and not (probs.argmax() == bg_idx and probs[bg_idx] >= BACKGROUND_MIN):
        probs = probs.copy()
        probs[bg_idx] = 0.0
        s = probs.sum()
        if s > 0:
            probs /= s
    return probs


def eval_items(model, ck, items, split_classes, data_dir: Path, device: torch.device):
    model_classes = ck["classes"]
    size = ck.get("img_size", 224)
    bg_idx = model_classes.index(BACKGROUND) if BACKGROUND in model_classes else None
    split_to_idx = {c: i for i, c in enumerate(split_classes)}
    crop_of = lambda c: c.split("___")[0]

    top1_hits = top5_hits = crop_hits = 0
    cm = np.zeros((len(split_classes), len(split_classes)), dtype=np.int64)
    t0 = time.perf_counter()

    for rel_path, y in items:
        gt_name = split_classes[y]
        img = Image.open(data_dir / rel_path).convert("RGB")
        probs = predict_4view(model, img, size, ck["mean"], ck["std"], device, bg_idx)
        order = probs.argsort()[::-1][:5]
        pred_name = model_classes[int(order[0])]
        top5_names = [model_classes[int(i)] for i in order]

        if pred_name in split_to_idx:
            cm[y, split_to_idx[pred_name]] += 1
        top1_hits += int(pred_name == gt_name)
        top5_hits += int(gt_name in top5_names)
        crop_hits += int(crop_of(pred_name) == crop_of(gt_name))

    elapsed = time.perf_counter() - t0
    n = len(items)
    f1s = []
    for i in range(len(split_classes)):
        tp = cm[i, i]; fp = cm[:, i].sum() - tp; fn = cm[i, :].sum() - tp
        if cm[i, :].sum() == 0:
            continue
        p = tp / (tp + fp) if (tp + fp) else 0.0
        r = tp / (tp + fn) if (tp + fn) else 0.0
        f1s.append(2 * p * r / (p + r) if (p + r) else 0.0)

    return {
        "n": n,
        "correct_top1": top1_hits,
        "top1_acc": round(top1_hits / n, 4),
        "top5_acc": round(top5_hits / n, 4),
        "crop_acc": round(crop_hits / n, 4),
        "macro_f1": round(float(np.mean(f1s)), 4),
        "ms_per_img": round((elapsed / n) * 1000, 2),
        "params": sum(p.numel() for p in model.parameters()),
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--split", default=str(ROOT / "reports" / "split.json"))
    ap.add_argument("--pv-prefix", default="raw")
    args = ap.parse_args()

    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    saved = json.loads(Path(args.split).read_text())
    data_dir = ROOT / "data"
    split_classes = saved["classes"]
    test_items = saved["test"]

    lab_items = [it for it in test_items if it[0].startswith(args.pv_prefix)]
    field_items = [it for it in test_items if not it[0].startswith(args.pv_prefix)]

    results = {}
    for label, path in DEFAULT_MODELS:
        if not path.exists():
            print(f"[skip] {label}: {path.resolve()} not found")
            continue
        print(f"Evaluating {label} ({path.resolve()})...")
        model, ck = load_checkpoint(path, device)
        res = {"all_test": eval_items(model, ck, test_items, split_classes, data_dir, device)}
        if lab_items:
            res["lab_subset"] = eval_items(model, ck, lab_items, split_classes, data_dir, device)
        if field_items:
            res["field_subset"] = eval_items(model, ck, field_items, split_classes, data_dir, device)
        results[label] = res

    (ROOT / "reports" / "model_comparison.json").write_text(json.dumps(results, indent=2))

    print(f"\nHeld-Out Test Split Breakdown: Total = {len(test_items)} | Lab (PV) = {len(lab_items)} | Field (PlantDoc) = {len(field_items)}")
    print("\n| Model | Params | Total Top-1 | Total Top-5 | Lab Top-1 | Field Top-1 | Field Top-5 | Crop Acc | Macro-F1 | Latency |")
    print("| :--- | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: |")
    for label, res in results.items():
        all_m = res["all_test"]
        tot_t1 = f"{all_m['top1_acc']*100:.2f}% ({all_m['correct_top1']}/{all_m['n']})"
        tot_t5 = f"{all_m['top5_acc']*100:.2f}%"
        lab_acc = f"{res['lab_subset']['top1_acc']*100:.2f}%" if "lab_subset" in res else "—"
        fld_t1 = f"{res['field_subset']['top1_acc']*100:.2f}%" if "field_subset" in res else "—"
        fld_t5 = f"{res['field_subset']['top5_acc']*100:.2f}%" if "field_subset" in res else "—"
        print(
            f"| {label} | {all_m['params']/1e6:.2f}M | {tot_t1} | {tot_t5} | {lab_acc} | {fld_t1} | {fld_t5} | "
            f"{all_m['crop_acc']*100:.2f}% | {all_m['macro_f1']:.4f} | {all_m['ms_per_img']} ms |"
        )


if __name__ == "__main__":
    main()
