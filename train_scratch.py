"""Train the 4-conv-block SmallCNN baseline from scratch on split.json."""
import argparse
import json
import random
from pathlib import Path

import numpy as np
import torch
import torch.nn as nn
from torch.utils.data import DataLoader

from app.small_cnn import SmallCNN
from train import MEAN, STD, LeafDataset, build_transforms, find_data_dir, per_class_report, run_epoch, stratified_split

ROOT = Path(__file__).resolve().parent


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--data", default=str(ROOT / "data" / "raw"))
    ap.add_argument("--extra", default=str(ROOT / "data" / "extra"))
    ap.add_argument("--out", default=str(ROOT / "models" / "plantdoctor_smallcnn.pt"))
    ap.add_argument("--field-repeat", type=int, default=3)
    ap.add_argument("--epochs", type=int, default=20)
    ap.add_argument("--batch", type=int, default=64)
    ap.add_argument("--lr", type=float, default=2e-3)
    ap.add_argument("--workers", type=int, default=2)
    ap.add_argument("--seed", type=int, default=42)
    args = ap.parse_args()

    random.seed(args.seed); np.random.seed(args.seed); torch.manual_seed(args.seed)
    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    torch.backends.cudnn.benchmark = True

    split_path = ROOT / "reports" / "split.json"
    if split_path.exists():
        saved = json.loads(split_path.read_text())
        data_dir = ROOT / "data"
        classes = saved["classes"]
        split = {k: saved[k] for k in ("train", "val", "test")}
    else:
        pv_dir = find_data_dir(Path(args.data))
        class_dirs = [pv_dir] + ([Path(args.extra)] if args.extra and Path(args.extra).is_dir() else [])
        data_dir = ROOT / "data"
        classes, split = stratified_split(class_dirs, data_dir, args.seed)

    pv_prefix = str(find_data_dir(Path(args.data)).relative_to(data_dir))
    field = [it for it in split["train"] if not it[0].startswith(pv_prefix)]
    split_train = split["train"] + field * (args.field_repeat - 1)

    train_tf, eval_tf = build_transforms()
    mk = lambda items, tf, shuf: DataLoader(
        LeafDataset(data_dir, items, tf), batch_size=args.batch, shuffle=shuf,
        num_workers=args.workers, pin_memory=True, persistent_workers=args.workers > 0, drop_last=shuf)
    train_dl, val_dl, test_dl = mk(split_train, train_tf, True), mk(split["val"], eval_tf, False), mk(split["test"], eval_tf, False)

    model = SmallCNN(len(classes)).to(device)
    criterion = nn.CrossEntropyLoss(label_smoothing=0.1)
    scaler = torch.amp.GradScaler(enabled=device.type == "cuda")
    opt = torch.optim.AdamW(model.parameters(), lr=args.lr, weight_decay=1e-4)
    sched = torch.optim.lr_scheduler.OneCycleLR(opt, max_lr=args.lr, total_steps=args.epochs * len(train_dl), pct_start=0.1)

    history = []
    best_va, best_state = 0.0, None
    print(f"Training SmallCNN from scratch ({sum(p.numel() for p in model.parameters()):,} params) on {device}")

    for e in range(args.epochs):
        tl, ta, _ = run_epoch(model, train_dl, device, criterion, opt, scaler, sched)
        vl, va, _ = run_epoch(model, val_dl, device, criterion)
        history.append({"epoch": e + 1, "stage": "scratch", "train_loss": tl, "train_acc": ta, "val_loss": vl, "val_acc": va})
        print(f"  epoch {e+1:2d}/{args.epochs}  train {tl:.4f}/{ta:.4f}  val {vl:.4f}/{va:.4f}")
        if va >= best_va:
            best_va, best_state = va, {k: v.detach().cpu().clone() for k, v in model.state_dict().items()}
        (ROOT / "reports" / "scratch_history.json").write_text(json.dumps(history, indent=1))

    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    model.load_state_dict(best_state)
    torch.save({"arch": "small_cnn", "classes": classes, "mean": MEAN, "std": STD,
                "img_size": 224, "state_dict": best_state, "val_acc": best_va}, out_path)
    print(f"Saved SmallCNN checkpoint -> {out_path.resolve()}")

    tl, tacc, (top5, ys) = run_epoch(model, test_dl, device, criterion)
    pred = top5[:, 0]
    top5_acc = float((top5 == ys[:, None]).any(1).mean())
    crop = lambda c: c.split("___")[0]
    crop_acc = float(np.mean([crop(classes[a]) == crop(classes[b]) for a, b in zip(pred, ys)]))
    cm = np.zeros((len(classes), len(classes)), dtype=np.int64)
    np.add.at(cm, (ys, pred), 1)
    np.save(ROOT / "reports" / "scratch_confusion_matrix.npy", cm)
    rep = per_class_report(cm, classes)
    macro_f1 = float(np.mean([r["f1"] for r in rep.values()]))

    (ROOT / "reports" / "scratch_test_metrics.json").write_text(json.dumps({
        "arch": "small_cnn", "test_acc": tacc, "test_loss": tl, "macro_f1": macro_f1,
        "best_val_acc": best_va, "top5_acc": top5_acc, "crop_acc": crop_acc,
        "n_test": int(len(ys)), "per_class": rep,
    }, indent=1))
    print(f"\nSCRATCH TEST accuracy {tacc:.4f}  macro-F1 {macro_f1:.4f}  top-5 {top5_acc:.4f}")


if __name__ == "__main__":
    main()
