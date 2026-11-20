"""Dataset audit + leakage-free (grouped) train / val / test split for the disease model.

    .venv/bin/python ml/prepare_split.py            # writes reports/v3/{dataset_audit.json,.md,split.json}

Steps
1. Collect images: PlantVillage (data/raw) + data/extra (field / fruit / vegetable / Pakistan sources).
   Legacy class names are renamed (Orange HLB -> Citrus___Huanglongbing).
2. Decode every file; drop unreadable / truncated ones; record resolution.
3. Label conflicts: the same picture (dHash distance <= 2) under two different classes -> both dropped.
4. Groups: PlantVillage holds several photos of the same leaf, and several mirrors re-publish photos.
   Images whose ImageNet-EfficientNet embeddings have cosine similarity >= GROUP_COS inside a class
   are joined into one group (union-find); tiles cut from one photo share the photo id.
   A whole group always lands in a single split, so near-duplicates cannot leak into test.
5. Classes with fewer than MIN_IMAGES images are merged where agronomically equivalent (MERGE)
   or excluded from the image model (they stay in the knowledge base).
6. Per class, groups are shuffled (seed) and assigned to test / val / train until ~15 % / 15 % /
   70 % of images; classes larger than CAP images are subsampled by whole groups (train time budget).
7. PlantDoc field photos in data/plantdoc_test are never used — they are the external test set.
"""
from __future__ import annotations

import hashlib
import json
import random
import re
import sys
import time
from collections import Counter, defaultdict
from pathlib import Path

import numpy as np
import torch
from PIL import Image
from torchvision import models, transforms

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
DATA = ROOT / "data"
PV = DATA / "raw" / "Plant_leave_diseases_dataset_without_augmentation"
EXTRA = DATA / "extra"
OUT = ROOT / "reports" / "v3"
SEED = 42
GROUP_COS = 0.93
MIN_IMAGES = 60
CAP = 1800
RENAME = {"Orange___Haunglongbing_(Citrus_greening)": "Citrus___Huanglongbing"}
MERGE = {"Citrus___Scale_insects": "Citrus___Scale_and_mealybugs", "Citrus___Mealybugs": "Citrus___Scale_and_mealybugs"}
EXCLUDE = {"Background_without_leaves": False}   # kept: it is the "no plant" class


def source_of(path: Path) -> str:
    if PV in path.parents:
        return "plantvillage"
    return path.name.split("_", 1)[0]


def photo_id(path: Path) -> str | None:
    """Tiles cut from one photo share an id (e.g. nwrd_123_0_0.jpg -> nwrd_123)."""
    m = re.match(r"(nwrd_\d+)_", path.name)
    return m.group(1) if m else None


def dhash(img: Image.Image, n=8) -> int:
    g = np.asarray(img.convert("L").resize((n + 1, n), Image.BILINEAR), dtype=np.int16)
    bits = (g[:, 1:] > g[:, :-1]).ravel()
    return int("".join("1" if b else "0" for b in bits), 2)


class UF:
    def __init__(self, n):
        self.p = list(range(n))

    def find(self, a):
        while self.p[a] != a:
            self.p[a] = self.p[self.p[a]]
            a = self.p[a]
        return a

    def union(self, a, b):
        a, b = self.find(a), self.find(b)
        if a != b:
            self.p[b] = a


def collect():
    items = []
    for root in (PV, EXTRA):
        for d in sorted(root.iterdir()):
            if not d.is_dir() or d.name.startswith((".", "_")):
                continue
            cls = MERGE.get(RENAME.get(d.name, d.name), RENAME.get(d.name, d.name))
            for f in sorted(d.iterdir()):
                if f.suffix.lower() in (".jpg", ".jpeg", ".png"):
                    items.append({"path": f, "cls": cls, "src": source_of(f)})
    return items


@torch.no_grad()
def embed(paths, device, batch=128):
    m = models.efficientnet_b0(weights=models.EfficientNet_B0_Weights.IMAGENET1K_V1)
    m.classifier = torch.nn.Identity()
    m = m.eval().to(device).half() if device.type == "cuda" else m.eval()
    tf = transforms.Compose([transforms.Resize(160), transforms.CenterCrop(160), transforms.ToTensor(),
                             transforms.Normalize([0.485, 0.456, 0.406], [0.229, 0.224, 0.225])])
    out = []
    for i in range(0, len(paths), batch):
        xs = []
        for p in paths[i:i + batch]:
            with Image.open(p) as im:
                xs.append(tf(im.convert("RGB")))
        x = torch.stack(xs).to(device)
        x = x.half() if device.type == "cuda" else x
        f = m(x).float()
        out.append(torch.nn.functional.normalize(f, dim=1).cpu())
        if i % (batch * 50) == 0:
            print(f"  embedded {i}/{len(paths)}", flush=True)
    return torch.cat(out)


def main():
    global OUT, MIN_IMAGES
    debug = "--debug" in sys.argv
    if debug:                       # quick pipeline check: 20 images per class, separate output
        OUT, MIN_IMAGES = ROOT / "reports" / "v3_debug", 5
    t0 = time.time()
    rnd = random.Random(SEED)
    OUT.mkdir(parents=True, exist_ok=True)
    items = collect()
    if debug:
        per = Counter()
        items = [it for it in items if (per.update([it["cls"]]) or per[it["cls"]] <= 20)]
    print(f"collected {len(items)} files", flush=True)

    # 2. decode check + resolution + dHash
    good, corrupt, sizes = [], [], Counter()
    for it in items:
        try:
            with Image.open(it["path"]) as im:
                im.load()
                w, h = im.size
                it["dhash"] = dhash(im)
            sizes["<=256" if max(w, h) <= 256 else "<=512" if max(w, h) <= 512 else ">512"] += 1
            good.append(it)
        except Exception:
            corrupt.append(str(it["path"].relative_to(DATA)))
    print(f"decoded {len(good)}, corrupt {len(corrupt)}", flush=True)

    # 3. label conflicts (exact / near-identical image under two classes)
    by_hash = defaultdict(set)
    for it in good:
        by_hash[it["dhash"]].add(it["cls"])
    conflict_hashes = {h for h, c in by_hash.items() if len(c) > 1}
    conflicts = [it for it in good if it["dhash"] in conflict_hashes]
    good = [it for it in good if it["dhash"] not in conflict_hashes]
    print(f"label conflicts dropped: {len(conflicts)}", flush=True)

    # 4. grouping by embedding similarity within class
    device = torch.device("cpu" if debug or not torch.cuda.is_available() else "cuda")
    emb = embed([it["path"] for it in good], device)
    uf = UF(len(good))
    by_cls = defaultdict(list)
    for i, it in enumerate(good):
        by_cls[it["cls"]].append(i)
    photo_first = {}
    for i, it in enumerate(good):
        pid = photo_id(it["path"])
        if pid:
            if pid in photo_first:
                uf.union(photo_first[pid], i)
            else:
                photo_first[pid] = i
    for cls, idx in by_cls.items():
        E = emb[idx]
        for a in range(0, len(idx), 2048):
            sim = E[a:a + 2048] @ E.T
            ii, jj = torch.nonzero(sim >= GROUP_COS, as_tuple=True)
            for x, y in zip(ii.tolist(), jj.tolist()):
                if a + x < y:
                    uf.union(idx[a + x], idx[y])
    for i, it in enumerate(good):
        it["group"] = uf.find(i)

    # 5. class size policy
    counts = Counter(it["cls"] for it in good)
    excluded = {c: n for c, n in counts.items() if n < MIN_IMAGES}
    good = [it for it in good if it["cls"] not in excluded]
    classes = sorted({it["cls"] for it in good})
    cidx = {c: i for i, c in enumerate(classes)}

    # 6. grouped split
    split = {"train": [], "val": [], "test": []}
    per_class = {}
    for cls in classes:
        groups = defaultdict(list)
        for it in (x for x in good if x["cls"] == cls):
            groups[it["group"]].append(it)
        gl = list(groups.values())
        rnd.shuffle(gl)
        n_total = sum(map(len, gl))
        kept, budget = [], min(n_total, CAP)
        for g in gl:                               # subsample whole groups to CAP
            if sum(map(len, kept)) >= budget:
                break
            kept.append(g)
        n = sum(map(len, kept))
        acc = {"test": 0, "val": 0, "train": 0}
        for g in kept:
            tgt = "test" if acc["test"] < 0.15 * n else "val" if acc["val"] < 0.15 * n else "train"
            acc[tgt] += len(g)
            split[tgt] += [(str(it["path"].relative_to(DATA)), cidx[cls], it["src"]) for it in g]
        per_class[cls] = {"available": n_total, "used": n, **acc, "groups": len(gl),
                          "sources": dict(Counter(it["src"] for g in kept for it in g))}

    # leakage proof: no group in two splits, no dHash in two splits
    grp_of = {str(it["path"].relative_to(DATA)): it["group"] for it in good}
    hash_of = {str(it["path"].relative_to(DATA)): it["dhash"] for it in good}
    gsets = {k: {grp_of[f] for f, _, _ in v} for k, v in split.items()}
    hsets = {k: {hash_of[f] for f, _, _ in v} for k, v in split.items()}
    leak = {"shared_groups_train_test": len(gsets["train"] & gsets["test"]),
            "shared_groups_train_val": len(gsets["train"] & gsets["val"]),
            "shared_dhash_train_test": len(hsets["train"] & hsets["test"])}

    srcs = Counter(it["src"] for it in good)
    audit = {
        "generated": time.strftime("%Y-%m-%d %H:%M"), "seed": SEED, "files_found": len(items),
        "corrupt_dropped": len(corrupt), "corrupt_examples": corrupt[:20],
        "label_conflicts_dropped": len(conflicts), "resolution": dict(sizes),
        "group_cosine_threshold": GROUP_COS, "groups": len({it["group"] for it in good}),
        "images_after_cleaning": len(good), "classes": len(classes), "crops": len({c.split("___")[0] for c in classes}),
        "excluded_small_classes": excluded, "merged": MERGE, "renamed": RENAME, "cap_per_class": CAP,
        "split_sizes": {k: len(v) for k, v in split.items()}, "leakage_check": leak,
        "sources": dict(srcs), "plantvillage_share": round(srcs.get("plantvillage", 0) / len(good), 3),
        "healthy_share": round(sum(1 for it in good if it["cls"].endswith("healthy")) / len(good), 3),
        "imbalance_after_cap": round(max(v["used"] for v in per_class.values()) / min(v["used"] for v in per_class.values()), 1),
        "per_class": per_class, "minutes": round((time.time() - t0) / 60, 1),
    }
    (OUT / "dataset_audit.json").write_text(json.dumps(audit, indent=1))
    (OUT / "split.json").write_text(json.dumps({"classes": classes, "data_dir": str(DATA), **split,
                                                "sha": hashlib.sha256(json.dumps(split).encode()).hexdigest()[:16]}))
    md = [f"# Dataset audit (v3) — {audit['generated']}", "",
          f"- Files found: {len(items)}; corrupt dropped: {len(corrupt)}; label conflicts dropped: {len(conflicts)}",
          f"- After cleaning: {len(good)} images, {len(classes)} classes, {audit['crops']} crops, {audit['groups']} near-duplicate groups",
          f"- PlantVillage (lab) share: {audit['plantvillage_share']:.0%}; healthy share: {audit['healthy_share']:.0%}",
          f"- Split (grouped, seed {SEED}): {audit['split_sizes']}; cap {CAP}/class; imbalance after cap {audit['imbalance_after_cap']}x",
          f"- Leakage check: {leak}", f"- Excluded (< {MIN_IMAGES} images): {excluded or 'none'}", "",
          "| class | available | used | train | val | test | groups |", "|---|---|---|---|---|---|---|"]
    md += [f"| {c} | {v['available']} | {v['used']} | {v['train']} | {v['val']} | {v['test']} | {v['groups']} |" for c, v in per_class.items()]
    (OUT / "dataset_audit.md").write_text("\n".join(md))
    print(json.dumps({k: audit[k] for k in ("images_after_cleaning", "classes", "groups", "split_sizes", "leakage_check",
                                            "excluded_small_classes", "minutes")}, indent=1))


if __name__ == "__main__":
    main()
