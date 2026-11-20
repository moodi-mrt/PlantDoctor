"""Download the IP102 insect-pest dataset (102 classes, ~75k images) for the pest model.

Source: Wu et al., "IP102: A Large-Scale Benchmark Dataset for Insect Pest Recognition", CVPR 2019,
https://github.com/xpwu95/IP102 . Original terms: free for ACADEMIC use; other uses need the
authors' permission. We read the Hugging Face parquet mirror (EnmmmmOvO/insect-pest-dataset,
labels 0..101 = classes.txt order) and keep the official train / val / test split so the test
numbers stay comparable with the paper.

Images are shrunk to <= 384 px and written to data/pests/<split>/<NNN_name>/.

    .venv/bin/python tools/fetch_pests.py
"""
import io
import json
import re
import sys
import time
import urllib.request
from pathlib import Path

import pyarrow.parquet as pq
from PIL import Image, ImageOps

sys.path.insert(0, str(Path(__file__).resolve().parent))
from fetch_extra import download  # noqa: E402  (curl with resume + stall detection)

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "data" / "pests"
REPO = "EnmmmmOvO/insect-pest-dataset"
HF = "https://huggingface.co"
CLASSES_URL = "https://raw.githubusercontent.com/xpwu95/IP102/master/classes.txt"
MAX_SIDE = 384
UA = {"User-Agent": "plantdoctor-fetch"}


def get(url):
    return urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=60).read()


def class_names():
    names = []
    for line in get(CLASSES_URL).decode().splitlines():
        m = re.match(r"\s*(\d+)\s+(.+?)\s*$", line)
        if m:
            names.append(m.group(2).strip())
    assert len(names) == 102, len(names)
    return names


def main():
    names = class_names()
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "classes.json").write_text(json.dumps(names, indent=1))
    tree = json.loads(get(f"{HF}/api/datasets/{REPO}/tree/main/data"))
    shards = sorted(f["path"] for f in tree if f["path"].endswith(".parquet"))
    done = OUT / ".done"
    done.mkdir(exist_ok=True)
    counts, bad = {}, 0
    for path in shards:
        split = Path(path).name.split("-")[0]           # train / validation / test
        split = "val" if split == "validation" else split
        marker = done / Path(path).name
        if marker.exists():
            continue
        tmp = OUT / f".part_{Path(path).name}"
        download(f"{HF}/datasets/{REPO}/resolve/main/{path}", tmp)
        try:
            pf = pq.ParquetFile(tmp)
            for rg in range(pf.num_row_groups):
                for i, row in enumerate(pf.read_row_group(rg).to_pylist()):
                    y = int(row["label"])
                    d = OUT / split / f"{y:03d}_{re.sub(r'[^A-Za-z0-9]+', '_', names[y]).strip('_')}"
                    out = d / f"{Path(path).stem[-14:]}_{rg}_{i}.jpg"
                    if out.exists():
                        continue
                    try:
                        img = ImageOps.exif_transpose(Image.open(io.BytesIO(row["image"]["bytes"]))).convert("RGB")
                    except Exception:
                        bad += 1
                        continue
                    d.mkdir(parents=True, exist_ok=True)
                    img.thumbnail((MAX_SIDE, MAX_SIDE))
                    img.save(out, quality=90)
                    counts[split] = counts.get(split, 0) + 1
        finally:
            tmp.unlink(missing_ok=True)
        marker.touch()
        print(f"{path} done  {counts}  corrupt={bad}", flush=True)
    (OUT / "metadata.json").write_text(json.dumps({
        "name": "IP102", "citation": "Wu, Zhan, Lai, Cheng, Yang. IP102: A Large-Scale Benchmark Dataset for "
                                     "Insect Pest Recognition. CVPR 2019.",
        "origin": "https://github.com/xpwu95/IP102", "mirror": f"{HF}/datasets/{REPO}",
        "license": "Free for academic use; other uses require permission from the authors "
                   "(the mirror's MIT tag does not override the original terms).",
        "images": {s: sum(1 for _ in (OUT / s).rglob("*.jpg")) for s in ("train", "val", "test") if (OUT / s).exists()},
        "corrupt_skipped": bad, "max_side_px": MAX_SIDE, "fetched": time.strftime("%Y-%m-%d")}, indent=1))


if __name__ == "__main__":
    main()
