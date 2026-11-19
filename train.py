"""
PlantDoctor — training script.

Fine-tunes an ImageNet-pretrained EfficientNet-B0 on the PlantVillage dataset
(39 classes: 38 crop/disease classes + 1 "background / no leaf" class).

Usage:
    .venv/bin/python train.py                 # full run (defaults below)
    .venv/bin/python train.py --epochs 2      # quick run

Outputs (in ./models and ./reports):
    models/plantdoctor_effnetb0.pt   weights + class list + normalisation
    reports/history.json             loss / accuracy per epoch
    reports/test_metrics.json        accuracy, per-class precision/recall/F1
    reports/confusion_matrix.npy     raw confusion matrix on the test split
    reports/split.json               exact file lists used for train/val/test
"""
import argparse
import json
import random
import time
from collections import Counter
from pathlib import Path

import numpy as np
import torch
import torch.nn as nn
from PIL import Image
from torch.utils.data import DataLoader, Dataset
from torchvision import models, transforms

ROOT = Path(__file__).resolve().parent
MEAN, STD = [0.485, 0.456, 0.406], [0.229, 0.224, 0.225]


def find_data_dir(raw: Path) -> Path:
    """Locate the folder whose sub-folders are the class folders."""
    for p in [raw, *sorted(raw.rglob("*"))]:
        if p.is_dir():
            subs = [s for s in p.iterdir() if s.is_dir()]
            if len(subs) >= 30:
                return p
    raise SystemExit(f"Could not find class folders under {raw}")


def stratified_split(class_dirs: list, base: Path, seed: int, val=0.1, test=0.1):
    """class_dirs: folders whose sub-folders are classes. A class name may appear
    in several of them (e.g. PlantVillage lab photos + PlantDoc field photos);
    their images are pooled. Paths are stored relative to `base`."""
    rng = random.Random(seed)
    classes = sorted({d.name for cd in class_dirs for d in cd.iterdir() if d.is_dir() and not d.name.startswith(".")})
    split = {"train": [], "val": [], "test": []}
    for ci, c in enumerate(classes):
        files = sorted(
            str(f.relative_to(base))
            for cd in class_dirs if (cd / c).is_dir()
            for f in (cd / c).iterdir()
            if f.suffix.lower() in {".jpg", ".jpeg", ".png"}
        )
        rng.shuffle(files)
        n_test, n_val = int(len(files) * test), int(len(files) * val)
        split["test"] += [(f, ci) for f in files[:n_test]]
        split["val"] += [(f, ci) for f in files[n_test : n_test + n_val]]
        split["train"] += [(f, ci) for f in files[n_test + n_val :]]
    return classes, split


class LeafDataset(Dataset):
    def __init__(self, root: Path, items, tf):
        self.root, self.items, self.tf = root, items, tf

    def __len__(self):
        return len(self.items)

    def __getitem__(self, i):
        f, y = self.items[i]
        img = Image.open(self.root / f).convert("RGB")
        return self.tf(img), y


def build_transforms(size=224):
    # Heavy-ish augmentation: PlantVillage photos are all taken on a plain
    # background under uniform light, so we deliberately perturb colour,
    # scale, orientation and blur to make the model less brittle.
    train_tf = transforms.Compose([
        transforms.RandomResizedCrop(size, scale=(0.4, 1.0)),
        transforms.RandomHorizontalFlip(),
        transforms.RandomVerticalFlip(),
        transforms.RandomRotation(25),
        transforms.ColorJitter(0.3, 0.3, 0.3, 0.05),
        transforms.RandomApply([transforms.GaussianBlur(5, sigma=(0.1, 2.0))], p=0.2),
        transforms.ToTensor(),
        transforms.Normalize(MEAN, STD),
        transforms.RandomErasing(p=0.2, scale=(0.02, 0.12)),
    ])
    eval_tf = transforms.Compose([
        transforms.Resize(256),
        transforms.CenterCrop(size),
        transforms.ToTensor(),
        transforms.Normalize(MEAN, STD),
    ])
    return train_tf, eval_tf


def build_model(num_classes: int, pretrained=True):
    w = models.EfficientNet_B0_Weights.IMAGENET1K_V1 if pretrained else None
    m = models.efficientnet_b0(weights=w)
    m.classifier = nn.Sequential(nn.Dropout(0.3), nn.Linear(m.classifier[1].in_features, num_classes))
    return m


def run_epoch(model, loader, device, criterion, optimizer=None, scaler=None, scheduler=None):
    train = optimizer is not None
    model.train(train)
    tot_loss, correct, n = 0.0, 0, 0
    preds_all, ys_all = [], []
    t0 = time.time()
    for step, (x, y) in enumerate(loader):
        x, y = x.to(device, non_blocking=True), y.to(device, non_blocking=True)
        with torch.set_grad_enabled(train), torch.autocast(device.type, enabled=device.type == "cuda"):
            out = model(x)
            loss = criterion(out, y)
        if train:
            optimizer.zero_grad(set_to_none=True)
            scaler.scale(loss).backward()
            scaler.step(optimizer)
            scaler.update()
            if scheduler is not None:
                scheduler.step()
        p = out.argmax(1)
        tot_loss += loss.item() * x.size(0)
        correct += (p == y).sum().item()
        n += x.size(0)
        if not train:
            preds_all.append(out.float().topk(5, 1).indices.cpu()); ys_all.append(y.cpu())
        if train and step % 100 == 0:
            print(f"    step {step:4d}/{len(loader)}  loss {tot_loss/n:.4f}  acc {correct/n:.4f}  "
                  f"({time.time()-t0:.0f}s)", flush=True)
    extra = (torch.cat(preds_all).numpy(), torch.cat(ys_all).numpy()) if not train else None
    return tot_loss / n, correct / n, extra


def per_class_report(cm, classes):
    rep = {}
    for i, c in enumerate(classes):
        tp = cm[i, i]; fp = cm[:, i].sum() - tp; fn = cm[i, :].sum() - tp
        p = tp / (tp + fp) if tp + fp else 0.0
        r = tp / (tp + fn) if tp + fn else 0.0
        f1 = 2 * p * r / (p + r) if p + r else 0.0
        rep[c] = {"precision": round(p, 4), "recall": round(r, 4), "f1": round(f1, 4), "support": int(cm[i].sum())}
    return rep


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--data", default=str(ROOT / "data" / "raw"))
    ap.add_argument("--extra", default=str(ROOT / "data" / "extra"),
                    help="extra class folders (field photos, fruits, vegetables); '' to disable")
    ap.add_argument("--field-repeat", type=int, default=3,
                    help="repeat real-world (non-PlantVillage) training images this many times per epoch")
    ap.add_argument("--init", default="", help="start from this checkpoint's backbone instead of ImageNet")
    ap.add_argument("--epochs", type=int, default=6)
    ap.add_argument("--batch", type=int, default=48)
    ap.add_argument("--lr", type=float, default=1e-3)
    ap.add_argument("--workers", type=int, default=8)
    ap.add_argument("--seed", type=int, default=42)
    args = ap.parse_args()

    random.seed(args.seed); np.random.seed(args.seed); torch.manual_seed(args.seed)
    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    print(f"Device: {device} {torch.cuda.get_device_name(0) if device.type == 'cuda' else ''}")
    torch.backends.cudnn.benchmark = True

    pv_dir = find_data_dir(Path(args.data))
    class_dirs = [pv_dir] + ([Path(args.extra)] if args.extra and Path(args.extra).is_dir() else [])
    data_dir = ROOT / "data"
    classes, split = stratified_split(class_dirs, data_dir, args.seed)
    print(f"Data: {', '.join(map(str, class_dirs))}\nClasses: {len(classes)} | train {len(split['train'])} "
          f"val {len(split['val'])} test {len(split['test'])}")
    # PlantVillage dominates by count; repeat the real-world photos so the model
    # sees enough cluttered, naturally lit images (the app's actual use case).
    pv_rel = str(pv_dir.relative_to(data_dir))
    field = [it for it in split["train"] if not it[0].startswith(pv_rel)]
    split_train = split["train"] + field * (args.field_repeat - 1)
    print(f"Real-world training images: {len(field)} (x{args.field_repeat} per epoch)")

    (ROOT / "models").mkdir(exist_ok=True); (ROOT / "reports").mkdir(exist_ok=True)
    json.dump({"data_dir": str(data_dir), "classes": classes, **split},
              open(ROOT / "reports" / "split.json", "w"))
    counts = Counter(y for _, y in split["train"])
    json.dump({classes[k]: v for k, v in sorted(counts.items())},
              open(ROOT / "reports" / "class_counts_train.json", "w"), indent=1)

    train_tf, eval_tf = build_transforms()
    mk = lambda items, tf, shuf: DataLoader(
        LeafDataset(data_dir, items, tf), batch_size=args.batch, shuffle=shuf,
        num_workers=args.workers, pin_memory=True, persistent_workers=True, drop_last=shuf)
    train_dl, val_dl, test_dl = mk(split_train, train_tf, True), mk(split["val"], eval_tf, False), mk(split["test"], eval_tf, False)

    model = build_model(len(classes))
    if args.init:
        ck = torch.load(args.init, map_location="cpu", weights_only=False)
        sd = {k: v for k, v in ck["state_dict"].items() if not k.startswith("classifier")}
        model.load_state_dict(sd, strict=False)
        print(f"Backbone initialised from {args.init}")
    model = model.to(device)
    criterion = nn.CrossEntropyLoss(label_smoothing=0.1)
    scaler = torch.amp.GradScaler(enabled=device.type == "cuda")
    history = []

    # ---- Stage 1: warm up the new classifier head with the backbone frozen.
    for p in model.features.parameters():
        p.requires_grad = False
    opt = torch.optim.AdamW(model.classifier.parameters(), lr=args.lr, weight_decay=1e-4)
    print("\n== Stage 1: head only (1 epoch) ==")
    tl, ta, _ = run_epoch(model, train_dl, device, criterion, opt, scaler)
    vl, va, _ = run_epoch(model, val_dl, device, criterion)
    history.append({"epoch": 1, "stage": "head", "train_loss": tl, "train_acc": ta, "val_loss": vl, "val_acc": va})
    print(f"  epoch 1  train {tl:.4f}/{ta:.4f}  val {vl:.4f}/{va:.4f}")

    # ---- Stage 2: unfreeze everything, lower LR, one-cycle cosine schedule.
    for p in model.parameters():
        p.requires_grad = True
    ft_epochs = args.epochs - 1
    opt = torch.optim.AdamW(model.parameters(), lr=args.lr / 3, weight_decay=1e-4)
    sched = torch.optim.lr_scheduler.OneCycleLR(opt, max_lr=args.lr / 3, total_steps=ft_epochs * len(train_dl), pct_start=0.15)
    best_va, best_state = 0.0, None
    print(f"\n== Stage 2: full fine-tune ({ft_epochs} epochs) ==")
    for e in range(ft_epochs):
        tl, ta, _ = run_epoch(model, train_dl, device, criterion, opt, scaler, sched)
        vl, va, _ = run_epoch(model, val_dl, device, criterion)
        history.append({"epoch": e + 2, "stage": "finetune", "train_loss": tl, "train_acc": ta, "val_loss": vl, "val_acc": va})
        print(f"  epoch {e+2}  train {tl:.4f}/{ta:.4f}  val {vl:.4f}/{va:.4f}")
        if va >= best_va:
            best_va, best_state = va, {k: v.detach().cpu().clone() for k, v in model.state_dict().items()}
        json.dump(history, open(ROOT / "reports" / "history.json", "w"), indent=1)

    model.load_state_dict(best_state)
    torch.save({"arch": "efficientnet_b0", "classes": classes, "mean": MEAN, "std": STD,
                "img_size": 224, "state_dict": best_state, "val_acc": best_va},
               ROOT / "models" / "plantdoctor_effnetb0.pt")

    # ---- Final evaluation on the held-out test split (never seen in training).
    tl, tacc, (top5, ys) = run_epoch(model, test_dl, device, criterion)
    pred = top5[:, 0]
    top5_acc = float((top5 == ys[:, None]).any(1).mean())
    crop = lambda c: c.split("___")[0]
    crop_acc = float(np.mean([crop(classes[a]) == crop(classes[b]) for a, b in zip(pred, ys)]))
    cm = np.zeros((len(classes), len(classes)), dtype=np.int64)
    np.add.at(cm, (ys, pred), 1)
    np.save(ROOT / "reports" / "confusion_matrix.npy", cm)
    rep = per_class_report(cm, classes)
    macro_f1 = float(np.mean([r["f1"] for r in rep.values()]))
    json.dump({"test_acc": tacc, "test_loss": tl, "macro_f1": macro_f1, "best_val_acc": best_va,
               "top5_acc": top5_acc, "crop_acc": crop_acc,
               "n_test": int(len(ys)), "per_class": rep}, open(ROOT / "reports" / "test_metrics.json", "w"), indent=1)
    print(f"\nTEST accuracy {tacc:.4f}  macro-F1 {macro_f1:.4f}")


if __name__ == "__main__":
    main()
