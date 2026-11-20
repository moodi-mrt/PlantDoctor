"""Shared training / evaluation code for PlantDoctor image models.

Everything that must be identical between training and serving lives here:
normalisation constants, eval transform, architecture builders. app/inference.py builds
models through `build_model(arch, n, pretrained=False)` from this module.
"""
from __future__ import annotations

import json
import math
import random
import time
from collections import Counter
from pathlib import Path

import numpy as np
import torch
import torch.nn as nn
import torch.nn.functional as F
from PIL import Image, ImageFile
from torch.utils.data import DataLoader, Dataset, WeightedRandomSampler
from torchvision import models, transforms

ImageFile.LOAD_TRUNCATED_IMAGES = False
MEAN, STD = [0.485, 0.456, 0.406], [0.229, 0.224, 0.225]
ARCHS = ("efficientnet_b0", "efficientnet_b2", "convnext_tiny", "mobilenet_v3_large")


def seed_everything(seed: int):
    random.seed(seed); np.random.seed(seed); torch.manual_seed(seed); torch.cuda.manual_seed_all(seed)


# ---------------------------------------------------------------- models
def build_model(arch: str, n: int, pretrained: bool = True) -> nn.Module:
    if arch == "efficientnet_b0":
        m = models.efficientnet_b0(weights=models.EfficientNet_B0_Weights.IMAGENET1K_V1 if pretrained else None)
        m.classifier = nn.Sequential(nn.Dropout(0.3), nn.Linear(m.classifier[1].in_features, n))
    elif arch == "efficientnet_b2":
        m = models.efficientnet_b2(weights=models.EfficientNet_B2_Weights.IMAGENET1K_V1 if pretrained else None)
        m.classifier = nn.Sequential(nn.Dropout(0.3), nn.Linear(m.classifier[1].in_features, n))
    elif arch == "convnext_tiny":
        m = models.convnext_tiny(weights=models.ConvNeXt_Tiny_Weights.IMAGENET1K_V1 if pretrained else None)
        m.classifier[2] = nn.Linear(m.classifier[2].in_features, n)
    elif arch == "mobilenet_v3_large":
        m = models.mobilenet_v3_large(weights=models.MobileNet_V3_Large_Weights.IMAGENET1K_V2 if pretrained else None)
        m.classifier[3] = nn.Linear(m.classifier[3].in_features, n)
    else:
        raise ValueError(f"unknown arch {arch}")
    return m


def head_params(m: nn.Module):
    return m.classifier.parameters()


def features(m: nn.Module, x: torch.Tensor) -> torch.Tensor:
    """Penultimate features = input of the final Linear layer (used for OOD detection).
    Runs the backbone, pooling and every classifier layer except the last Linear."""
    f = m.avgpool(m.features(x))
    if not isinstance(m, models.ConvNeXt):
        f = torch.flatten(f, 1)
    return m.classifier[:-1](f)


def last_linear(m: nn.Module) -> nn.Linear:
    return [x for x in m.classifier.modules() if isinstance(x, nn.Linear)][-1]


# ---------------------------------------------------------------- data
def train_transform(size: int):
    return transforms.Compose([
        transforms.RandomResizedCrop(size, scale=(0.35, 1.0), ratio=(0.75, 1.33)),
        transforms.RandomHorizontalFlip(),
        transforms.RandomVerticalFlip(),
        transforms.RandomApply([transforms.RandomRotation(30)], p=0.5),
        transforms.RandomApply([transforms.RandomPerspective(0.25, p=1.0)], p=0.2),
        transforms.ColorJitter(0.35, 0.35, 0.3, 0.04),
        transforms.RandomApply([transforms.GaussianBlur(5, sigma=(0.1, 2.0))], p=0.2),
        transforms.RandomGrayscale(p=0.02),
        transforms.ToTensor(),
        transforms.Normalize(MEAN, STD),
        transforms.RandomErasing(p=0.2, scale=(0.02, 0.12)),
    ])


def eval_transform(size: int):
    """MUST match app/inference.py (resize ×256/224 then centre crop)."""
    return transforms.Compose([transforms.Resize(int(round(size * 256 / 224))), transforms.CenterCrop(size),
                               transforms.ToTensor(), transforms.Normalize(MEAN, STD)])


class ImageListDataset(Dataset):
    def __init__(self, root: Path, items: list, tf):
        self.root, self.items, self.tf = Path(root), items, tf

    def __len__(self):
        return len(self.items)

    def __getitem__(self, i):
        f, y = self.items[i]
        with Image.open(self.root / f) as im:
            img = im.convert("RGB")
        return self.tf(img), y


def balanced_sampler(labels: list[int], power: float = 0.5, weights_extra: list[float] | None = None,
                     epoch_size: int | None = None):
    """Sample class c with probability ∝ count_c ** power (power 0.5 = square-root balancing)."""
    cnt = Counter(labels)
    w = np.array([cnt[y] ** (power - 1.0) for y in labels], dtype=np.float64)
    if weights_extra is not None:
        w *= np.asarray(weights_extra)
    return WeightedRandomSampler(torch.as_tensor(w), num_samples=epoch_size or len(labels), replacement=True)


def loader(ds, batch, workers, sampler=None, shuffle=False):
    return DataLoader(ds, batch_size=batch, sampler=sampler, shuffle=shuffle and sampler is None,
                      num_workers=workers, pin_memory=True, persistent_workers=workers > 0,
                      drop_last=sampler is not None or shuffle)


# ---------------------------------------------------------------- training
def train_one_epoch(model, dl, device, criterion, opt, scaler, sched=None, log_every=200):
    model.train()
    tot, correct, n, t0 = 0.0, 0, 0, time.time()
    for step, (x, y) in enumerate(dl):
        x, y = x.to(device, non_blocking=True), y.to(device, non_blocking=True)
        with torch.autocast(device.type, enabled=device.type == "cuda"):
            out = model(x)
            loss = criterion(out, y)
        opt.zero_grad(set_to_none=True)
        scaler.scale(loss).backward()
        scaler.unscale_(opt)
        nn.utils.clip_grad_norm_(model.parameters(), 5.0)
        scaler.step(opt)
        scaler.update()
        if sched is not None:
            sched.step()
        tot += loss.item() * x.size(0); correct += (out.argmax(1) == y).sum().item(); n += x.size(0)
        if step % log_every == 0:
            print(f"    step {step:5d}/{len(dl)}  loss {tot/n:.4f}  acc {correct/n:.4f}  ({time.time()-t0:.0f}s)", flush=True)
    return tot / n, correct / n


@torch.no_grad()
def predict_logits(model, dl, device, with_features=False):
    model.eval()
    L, Y, Fs = [], [], []
    for x, y in dl:
        x = x.to(device, non_blocking=True)
        with torch.autocast(device.type, enabled=device.type == "cuda"):
            if with_features:
                f = features(model, x)
                out = last_linear(model)(f)
                Fs.append(f.float().cpu())
            else:
                out = model(x)
        L.append(out.float().cpu()); Y.append(y)
    res = (torch.cat(L), torch.cat(Y))
    return (*res, torch.cat(Fs)) if with_features else res


def make_scheduler(opt, total_steps, warmup_frac=0.05):
    warm = max(1, int(total_steps * warmup_frac))

    def f(step):
        if step < warm:
            return (step + 1) / warm
        p = (step - warm) / max(1, total_steps - warm)
        return 0.5 * (1 + math.cos(math.pi * min(1.0, p)))
    return torch.optim.lr_scheduler.LambdaLR(opt, f)


def fit(model, train_dl, val_dl, device, epochs, lr, out_dir: Path, patience=3, label_smoothing=0.1,
        head_epochs=1, classes=None):
    """Head warm-up, then full fine-tune with warmup+cosine LR; early stopping on val macro-F1."""
    out_dir.mkdir(parents=True, exist_ok=True)
    crit = nn.CrossEntropyLoss(label_smoothing=label_smoothing)
    scaler = torch.amp.GradScaler(enabled=device.type == "cuda")
    hist, best, best_state, bad = [], -1.0, None, 0
    for p in model.parameters():
        p.requires_grad = False
    for p in head_params(model):
        p.requires_grad = True
    opt = torch.optim.AdamW(head_params(model), lr=lr, weight_decay=1e-4)
    for e in range(head_epochs):
        tl, ta = train_one_epoch(model, train_dl, device, crit, opt, scaler)
        m = evaluate(*predict_logits(model, val_dl, device), classes)
        hist.append({"epoch": e + 1, "stage": "head", "train_loss": tl, "train_acc": ta, **_brief(m)})
        print(f"  [head] epoch {e+1} train {tl:.4f}/{ta:.4f} val acc {m['accuracy']:.4f} macroF1 {m['macro_f1']:.4f}", flush=True)
    for p in model.parameters():
        p.requires_grad = True
    opt = torch.optim.AdamW(model.parameters(), lr=lr / 3, weight_decay=0.05)
    sched = make_scheduler(opt, (epochs - head_epochs) * len(train_dl))
    for e in range(head_epochs, epochs):
        tl, ta = train_one_epoch(model, train_dl, device, crit, opt, scaler, sched)
        m = evaluate(*predict_logits(model, val_dl, device), classes)
        hist.append({"epoch": e + 1, "stage": "finetune", "train_loss": tl, "train_acc": ta, **_brief(m)})
        print(f"  epoch {e+1} train {tl:.4f}/{ta:.4f} val acc {m['accuracy']:.4f} macroF1 {m['macro_f1']:.4f} "
              f"ECE {m['ece']:.4f}", flush=True)
        (out_dir / "history.json").write_text(json.dumps(hist, indent=1))
        if m["macro_f1"] > best:
            best, bad = m["macro_f1"], 0
            best_state = {k: v.detach().cpu().clone() for k, v in model.state_dict().items()}
            torch.save(best_state, out_dir / "best_state.pt")
        else:
            bad += 1
            if bad >= patience:
                print(f"  early stop (no val macro-F1 gain for {patience} epochs)", flush=True)
                break
    model.load_state_dict(best_state)
    return model, hist, best


def _brief(m):
    return {k: m[k] for k in ("accuracy", "macro_f1", "ece", "nll")}


# ---------------------------------------------------------------- metrics
def ece_score(probs: np.ndarray, y: np.ndarray, bins: int = 15) -> tuple[float, list]:
    conf = probs.max(1); pred = probs.argmax(1); acc = (pred == y).astype(float)
    edges = np.linspace(0, 1, bins + 1)
    e, table = 0.0, []
    for lo, hi in zip(edges[:-1], edges[1:]):
        m = (conf > lo) & (conf <= hi)
        if m.any():
            e += m.mean() * abs(acc[m].mean() - conf[m].mean())
            table.append({"lo": round(lo, 3), "hi": round(hi, 3), "n": int(m.sum()),
                          "acc": float(acc[m].mean()), "conf": float(conf[m].mean())})
    return float(e), table


def evaluate(logits: torch.Tensor, y: torch.Tensor, classes=None, temperature: float = 1.0) -> dict:
    probs = F.softmax(logits / temperature, 1).numpy()
    y = y.numpy()
    n = probs.shape[1]
    pred = probs.argmax(1)
    cm = np.zeros((n, n), dtype=np.int64)
    np.add.at(cm, (y, pred), 1)
    per = {}
    f1s, ws = [], []
    for i in range(n):
        tp = cm[i, i]; fp = cm[:, i].sum() - tp; fn = cm[i, :].sum() - tp
        p = tp / (tp + fp) if tp + fp else 0.0
        r = tp / (tp + fn) if tp + fn else 0.0
        f1 = 2 * p * r / (p + r) if p + r else 0.0
        sup = int(cm[i].sum())
        if sup:
            f1s.append(f1); ws.append(sup)
        name = classes[i] if classes else str(i)
        per[name] = {"precision": round(p, 4), "recall": round(r, 4), "f1": round(f1, 4), "support": sup,
                     "accuracy": round(tp / sup, 4) if sup else None}
    top5 = np.argsort(probs, 1)[:, -5:]
    ece, rel = ece_score(probs, y)
    nll = float(F.nll_loss(torch.log(torch.as_tensor(probs).clamp_min(1e-12)), torch.as_tensor(y)).item())
    sup = [p for p in per.values() if p["support"]]
    return {
        "n": int(len(y)), "accuracy": float((pred == y).mean()),
        "top5_accuracy": float((top5 == y[:, None]).any(1).mean()),
        "macro_precision": float(np.mean([p["precision"] for p in sup])),
        "macro_recall": float(np.mean([p["recall"] for p in sup])),
        "macro_f1": float(np.mean(f1s)), "weighted_f1": float(np.average(f1s, weights=ws)),
        "ece": ece, "nll": nll, "reliability": rel, "per_class": per, "confusion_matrix": cm,
        "roc_auc_ovr_macro": _auc_ovr(probs, y),
    }


def _auc_ovr(probs, y):
    """Macro one-vs-rest ROC-AUC (rank-based, no sklearn dependency)."""
    aucs = []
    for c in range(probs.shape[1]):
        pos = y == c
        if pos.sum() == 0 or pos.sum() == len(y):
            continue
        s = probs[:, c]
        order = s.argsort()
        ranks = np.empty(len(s)); ranks[order] = np.arange(1, len(s) + 1)
        aucs.append((ranks[pos].sum() - pos.sum() * (pos.sum() + 1) / 2) / (pos.sum() * (~pos).sum()))
    return float(np.mean(aucs)) if aucs else None


def fit_temperature(logits: torch.Tensor, y: torch.Tensor) -> float:
    """Temperature scaling (Guo et al. 2017), fitted on the validation set by minimising NLL."""
    t = torch.zeros(1, requires_grad=True)
    opt = torch.optim.LBFGS([t], lr=0.1, max_iter=200)

    def closure():
        opt.zero_grad()
        loss = F.cross_entropy(logits / t.exp(), y)
        loss.backward()
        return loss
    opt.step(closure)
    return float(t.exp().item())


# ---------------------------------------------------------------- OOD
def fit_mahalanobis(feats: torch.Tensor, y: torch.Tensor, n_classes: int, shrink: float = 1e-3):
    """Class means + shared (tied) covariance precision for Mahalanobis OOD scoring (Lee et al. 2018)."""
    d = feats.shape[1]
    means = torch.zeros(n_classes, d)
    centered = []
    for c in range(n_classes):
        m = y == c
        if m.any():
            means[c] = feats[m].mean(0)
            centered.append(feats[m] - means[c])
    X = torch.cat(centered)
    cov = (X.T @ X) / len(X) + shrink * torch.eye(d)
    return means, torch.linalg.inv(cov)


def mahalanobis_score(feats: torch.Tensor, means: torch.Tensor, prec: torch.Tensor) -> torch.Tensor:
    """Min class Mahalanobis distance (higher = more out-of-distribution)."""
    out = []
    for chunk in feats.split(1024):
        diff = chunk[:, None, :] - means[None]                # B x C x D
        dist = torch.einsum("bcd,de,bce->bc", diff, prec, diff)
        out.append(dist.min(1).values)
    return torch.cat(out)


def energy_score(logits: torch.Tensor, T: float = 1.0) -> torch.Tensor:
    """Negative free energy; higher = more in-distribution (Liu et al. 2020)."""
    return T * torch.logsumexp(logits / T, 1)


def auroc(pos_scores: np.ndarray, neg_scores: np.ndarray) -> float:
    s = np.concatenate([pos_scores, neg_scores]); lab = np.r_[np.ones(len(pos_scores)), np.zeros(len(neg_scores))]
    order = s.argsort(); ranks = np.empty(len(s)); ranks[order] = np.arange(1, len(s) + 1)
    p = lab == 1
    return float((ranks[p].sum() - p.sum() * (p.sum() + 1) / 2) / (p.sum() * (~p).sum()))


@torch.no_grad()
def latency_ms(model, size: int, device, runs: int = 30) -> float:
    model.eval()
    x = torch.randn(1, 3, size, size, device=device)
    for _ in range(5):
        model(x)
    if device.type == "cuda":
        torch.cuda.synchronize()
    t = time.perf_counter()
    for _ in range(runs):
        model(x)
    if device.type == "cuda":
        torch.cuda.synchronize()
    return (time.perf_counter() - t) / runs * 1000


def dump_metrics(m: dict, path: Path):
    m = dict(m)
    cm = m.pop("confusion_matrix")
    np.save(path.with_suffix(".confusion.npy"), cm)
    path.write_text(json.dumps(m, indent=1))
