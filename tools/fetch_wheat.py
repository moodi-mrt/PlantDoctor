"""Prepare wheat disease images.

1. NWRD — NUST Wheat Rust Disease dataset (Pakistan; CC BY 4.0; Zenodo 10.5281/zenodo.21672928).
   102 high-resolution field photos with pixel masks of stripe (yellow) rust. Each photo is cut
   into square tiles; a tile is labelled Wheat___Yellow_rust if >= 1.5 % of it is masked rust and
   Wheat___healthy if it has no rust at all (tiles in between are ambiguous and skipped).
   Tile names keep the source photo id (nwrd_<photo>_<tile>.jpg) so the grouped split never
   puts tiles of one photo into different splits.

2. JIC — John Innes Centre "Wheat disease images (small dataset)" (CC BY 4.0; Zenodo 7573133):
   yellow rust, brown rust, septoria, mildew, healthy. Folder names are mapped below.

    .venv/bin/python tools/fetch_wheat.py nwrd jic
"""
import io
import json
import re
import sys
import time
import zipfile
from pathlib import Path

import numpy as np
from PIL import Image, ImageOps

ROOT = Path(__file__).resolve().parent.parent
DL = ROOT / "data" / "downloads"
OUT = ROOT / "data" / "extra"
Image.MAX_IMAGE_PIXELS = 80_000_000
TILE_OUT = 512


def save(img: Image.Image, cls: str, name: str):
    d = OUT / cls
    d.mkdir(parents=True, exist_ok=True)
    img = img.convert("RGB")
    img.thumbnail((TILE_OUT, TILE_OUT))
    img.save(d / name, quality=90)


def nwrd():
    z = zipfile.ZipFile(DL / "wheat_nwrd" / "NWRD.zip")
    names = set(z.namelist())
    counts = {"Wheat___Yellow_rust": 0, "Wheat___healthy": 0}
    skipped = 0
    for n in sorted(names):
        m = re.match(r"(train|test)/images/(\d+)\.jpg$", n)
        if not m:
            continue
        split, pid = m.groups()
        mask_name = f"{split}/masks/{pid}.png"
        if mask_name not in names:
            continue
        img = ImageOps.exif_transpose(Image.open(io.BytesIO(z.read(n)))).convert("RGB")
        mask = np.asarray(Image.open(io.BytesIO(z.read(mask_name))).convert("L").resize(img.size, Image.NEAREST)) > 127
        W, H = img.size
        t = max(384, min(W, H) // 4)                 # ~4 tiles across the short side
        healthy_here = 0
        for y in range(0, H - t + 1, t):
            for x in range(0, W - t + 1, t):
                frac = float(mask[y:y + t, x:x + t].mean())
                tile = img.crop((x, y, x + t, y + t))
                a = np.asarray(tile.resize((64, 64)), dtype=np.float32)
                green = ((a[..., 1] > a[..., 0]) & (a[..., 1] > a[..., 2])).mean()
                if frac >= 0.015:
                    save(tile, "Wheat___Yellow_rust", f"nwrd_{pid}_{x}_{y}.jpg")
                    counts["Wheat___Yellow_rust"] += 1
                elif frac == 0 and green > 0.35 and healthy_here < 6:
                    save(tile, "Wheat___healthy", f"nwrd_{pid}_{x}_{y}.jpg")
                    counts["Wheat___healthy"] += 1
                    healthy_here += 1
                else:
                    skipped += 1
    meta("nwrd", "CC BY 4.0", "NUST Wheat Rust Disease Dataset (NWRD), National University of Sciences and "
         "Technology, Pakistan — Zenodo", "https://doi.org/10.5281/zenodo.21672928", counts,
         {"tiling": "square tiles ~1/4 of the short side; rust if >=1.5% masked, healthy if 0% and mostly green "
                    "(max 6 healthy tiles per photo); grouped by source photo for splitting", "ambiguous_tiles_skipped": skipped})
    print("nwrd", counts, "skipped", skipped)


JIC_MAP = {"yellow": "Wheat___Yellow_rust", "stripe": "Wheat___Yellow_rust", "brown": "Wheat___Brown_rust",
           "leaf rust": "Wheat___Brown_rust", "septoria": "Wheat___Septoria", "mildew": "Wheat___Powdery_mildew",
           "healthy": "Wheat___healthy"}


def jic():
    z = zipfile.ZipFile(DL / "wheat_jic" / "jic.zip")
    counts, unmapped = {}, set()
    for n in sorted(z.namelist()):
        if not n.lower().endswith((".jpg", ".jpeg", ".png")) or "__MACOSX" in n:
            continue
        key = n.lower()
        cls = next((v for k, v in JIC_MAP.items() if k in key), None)
        if cls is None:
            unmapped.add(str(Path(n).parent))
            continue
        try:
            img = ImageOps.exif_transpose(Image.open(io.BytesIO(z.read(n))))
        except Exception:
            continue
        save(img, cls, f"jic_{re.sub(r'[^A-Za-z0-9]+', '_', Path(n).stem)[-40:]}.jpg")
        counts[cls] = counts.get(cls, 0) + 1
    meta("jic", "CC BY 4.0", "Long et al. 2023, wheat disease images (small dataset), John Innes Centre — Zenodo",
         "https://doi.org/10.5281/zenodo.7573133", counts, {"unmapped_folders": sorted(unmapped)})
    print("jic", counts, "unmapped", sorted(unmapped)[:10])


def meta(key, lic, citation, origin, counts, extra):
    d = OUT / "_sources"
    d.mkdir(parents=True, exist_ok=True)
    (d / f"{key}.json").write_text(json.dumps({"key": key, "origin": origin, "license": lic, "citation": citation,
                                               "images_kept": counts, "max_side_px": TILE_OUT,
                                               "fetched": time.strftime("%Y-%m-%d"), **extra}, indent=1))


if __name__ == "__main__":
    for k in sys.argv[1:] or ["nwrd", "jic"]:
        {"nwrd": nwrd, "jic": jic}[k]()
