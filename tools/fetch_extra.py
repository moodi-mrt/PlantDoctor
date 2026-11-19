"""Download extra training data: real field photos, fruits, vegetables, pests.

Sources are Hugging Face mirrors (Project-AgML) of open datasets, all CC BY 4.0
except PlantDoc (CC BY-SA 4.0). Each parquet shard is streamed, images are
shrunk to <= 384 px and written to data/extra/<Crop___Condition>/, then the
shard is deleted. PlantDoc images that duplicate the held-out field test set
(data/plantdoc_test) are skipped so the field evaluation stays honest.

    .venv/bin/python tools/fetch_extra.py            # all sources
    .venv/bin/python tools/fetch_extra.py mango bean # just some
"""
import io
import json
import subprocess
import sys
import time
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import numpy as np
import pyarrow.parquet as pq
from PIL import Image, ImageOps

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "data" / "extra"
HF = "https://huggingface.co"
MAX_SIDE = 384
CAP = 800          # max images per target class per source
UA = {"User-Agent": "plantdoctor-fetch"}

# PlantDoc folder -> existing PlantVillage class (same crops, but real field photos)
PLANTDOC = {
    "Apple Scab Leaf": "Apple___Apple_scab", "Apple leaf": "Apple___healthy",
    "Apple rust leaf": "Apple___Cedar_apple_rust", "Bell_pepper leaf spot": "Pepper,_bell___Bacterial_spot",
    "Bell_pepper leaf": "Pepper,_bell___healthy", "Blueberry leaf": "Blueberry___healthy",
    "Cherry leaf": "Cherry___healthy", "Corn Gray leaf spot": "Corn___Cercospora_leaf_spot Gray_leaf_spot",
    "Corn leaf blight": "Corn___Northern_Leaf_Blight", "Corn rust leaf": "Corn___Common_rust",
    "Peach leaf": "Peach___healthy", "Potato leaf early blight": "Potato___Early_blight",
    "Potato leaf late blight": "Potato___Late_blight", "Raspberry leaf": "Raspberry___healthy",
    "Soyabean leaf": "Soybean___healthy", "Squash Powdery mildew leaf": "Squash___Powdery_mildew",
    "Strawberry leaf": "Strawberry___healthy", "Tomato Early blight leaf": "Tomato___Early_blight",
    "Tomato Septoria leaf spot": "Tomato___Septoria_leaf_spot", "Tomato leaf bacterial spot": "Tomato___Bacterial_spot",
    "Tomato leaf late blight": "Tomato___Late_blight", "Tomato leaf mosaic virus": "Tomato___Tomato_mosaic_virus",
    "Tomato leaf yellow virus": "Tomato___Tomato_Yellow_Leaf_Curl_Virus", "Tomato leaf": "Tomato___healthy",
    "Tomato mold leaf": "Tomato___Leaf_Mold", "grape leaf black rot": "Grape___Black_rot", "grape leaf": "Grape___healthy",
    "Tomato two spotted spider mites leaf": "Tomato___Spider_mites Two-spotted_spider_mite",
}

# key -> (repo, config dir, {source label: target class or None to skip})
SOURCES = {
    "plantdoc": ("plant_doc_classification", "data", PLANTDOC),
    "pomegranate": ("pomegranate_disease_classification", "raw", {
        "Colletotrichum spp": "Pomegranate___Anthracnose", "Ectomyelois ceratoniae": "Pomegranate___Fruit_borer",
        "Healthy": "Pomegranate___healthy", "Sunburn": "Pomegranate___Sunburn"}),
    "guava": ("guava_disease_classification", "raw", {
        "Anthracnose": "Guava___Anthracnose", "Canker": "Guava___Canker", "Healthy": "Guava___healthy",
        "Rust": "Guava___Rust", "Scab": "Guava___Scab", "Styler end root": "Guava___Styler_end_rot"}),
    "brinjal_fruit": ("BrinjalFruitX_disease_classification", "data", {
        "Brinjal Fruit Creaking": "Eggplant___Fruit_cracking", "Healty Brinjal": "Eggplant___healthy",
        "Phomopsis Bright": "Eggplant___Phomopsis_blight", "Shoot and Fruit Borer": "Eggplant___Shoot_and_fruit_borer",
        "Wet Rot": "Eggplant___Wet_rot"}),
    "eggplant_leaf": ("eggplant_disease_classification", "raw", {
        "Healthy Leaf": "Eggplant___healthy", "Insect Pest Disease": "Eggplant___Insect_pest_damage",
        "Leaf Spot Disease": "Eggplant___Leaf_spot", "Mosaic Virus Disease": "Eggplant___Mosaic_virus",
        "White Mold Disease": "Eggplant___White_mold", "Wilt Disease": "Eggplant___Wilt"}),
    "chili": ("COLD_chili_leaf_disease_classification", "raw", {
        "cercospora": "Chili___Cercospora_leaf_spot", "healthy": "Chili___healthy",
        "mites_and_trips": "Chili___Mites_and_thrips", "nutritional": "Chili___Nutrient_deficiency",
        "powdery mildew": "Chili___Powdery_mildew"}),
    "bean": ("bean_disease_uganda", "data", {
        "angular_leaf_spot": "Bean___Angular_leaf_spot", "bean_rust": "Bean___Rust", "healthy": "Bean___healthy"}),
    "soybean_insect": ("soybean_insect_classification", "data", {
        "Caterpillar": "Soybean___Caterpillar_damage", "Diabrotica_speciosa": "Soybean___Diabrotica_beetle_damage",
        "Healthy": "Soybean___healthy"}),
    "mango": ("mango_leaf_disease_classification", "data", {
        "Anthracnose": "Mango___Anthracnose", "Bacterial_Canker": "Mango___Bacterial_canker",
        "Cutting_Weevil": "Mango___Cutting_weevil", "Die_Back": "Mango___Die_back", "Gall_Midge": "Mango___Gall_midge",
        "Healthy": "Mango___healthy", "Powdery_Mildew": "Mango___Powdery_mildew", "Sooty_Mold": "Mango___Sooty_mould"}),
    "carambola": ("carambola_disease_classification", "raw", {
        "Healthy Fruits": "Carambola___healthy", "Healthy Leaves": "Carambola___healthy",
        "Insect Hole leaves": "Carambola___Insect_damage"}),
}


def get_json(url):
    return json.loads(urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=60).read())


def label_names(repo, config):
    card = get_json(f"{HF}/api/datasets/Project-AgML/{repo}")["cardData"]["dataset_info"]
    infos = card if isinstance(card, list) else [card]
    info = next((i for i in infos if i.get("config_name", "default") in (config, "default")), infos[0])
    for f in info["features"]:
        dt = f.get("dtype")
        if isinstance(dt, dict) and "class_label" in dt:
            names = dt["class_label"]["names"]
            return [names[str(i)] for i in range(len(names))]
    raise RuntimeError(f"no class labels for {repo}")


def dhash(img, n=8):
    g = np.asarray(img.convert("L").resize((n + 1, n), Image.BILINEAR), dtype=np.int16)
    return np.packbits((g[:, 1:] > g[:, :-1]).ravel())


def test_hashes():
    hs = []
    for f in (ROOT / "data" / "plantdoc_test").rglob("*"):
        try:
            hs.append(dhash(Image.open(f)))
        except Exception:
            pass
    return np.stack(hs)


def is_test_dup(h, bank):
    return bool((np.unpackbits(bank ^ h, axis=1).sum(1) <= 6).any())


def shards(repo, config):
    tree = get_json(f"{HF}/api/datasets/Project-AgML/{repo}/tree/main/{config}")
    return [f["path"] for f in tree if f["type"] == "file" and f["path"].endswith(".parquet")]


def download(url, dst: Path):
    """curl with resume (-C -) and stall detection: abort if < 20 kB/s for 60 s, then retry."""
    for attempt in range(20):
        r = subprocess.run(["curl", "-sSL", "--fail", "-C", "-", "--speed-limit", "20000", "--speed-time", "60",
                            "--connect-timeout", "30", "-A", UA["User-Agent"], "-o", str(dst), url])
        if r.returncode == 0:
            return
        print(f"  retry {attempt + 1} ({dst.name}, curl exit {r.returncode})", flush=True)
        time.sleep(min(60, 5 * (attempt + 1)))
    raise RuntimeError(f"download failed: {url}")


def fetch(key, bank):
    repo, config, mapping = SOURCES[key]
    names = label_names(repo, config)
    done_dir = OUT / ".done"
    done_dir.mkdir(exist_ok=True)
    # Resume: count images already on disk from this source.
    counts, dups = {}, 0
    for f in OUT.glob(f"*/{key}_*.jpg"):
        counts[f.parent.name] = counts.get(f.parent.name, 0) + 1
    for path in shards(repo, config):
        marker = done_dir / f"{key}__{Path(path).name}"
        if marker.exists():
            continue
        if mapping and all(counts.get(t, 0) >= CAP for t in set(v for v in mapping.values() if v)):
            break
        tmp = OUT / f".part_{key}_{Path(path).name}"
        download(f"{HF}/datasets/Project-AgML/{repo}/resolve/main/{path}", tmp)
        try:
            pf = pq.ParquetFile(tmp)
            for rg in range(pf.num_row_groups):
                for i, row in enumerate(pf.read_row_group(rg).to_pylist()):
                    target = mapping.get(names[row["label"]])
                    if target is None or counts.get(target, 0) >= CAP:
                        continue
                    try:
                        img = ImageOps.exif_transpose(Image.open(io.BytesIO(row["image"]["bytes"]))).convert("RGB")
                    except Exception:
                        continue
                    if key == "plantdoc" and is_test_dup(dhash(img), bank):
                        dups += 1
                        continue
                    d = OUT / target
                    d.mkdir(parents=True, exist_ok=True)
                    out = d / f"{key}_{Path(path).stem[-14:]}_{rg}_{i}.jpg"
                    if out.exists():          # saved by an earlier, interrupted run
                        continue
                    img.thumbnail((MAX_SIDE, MAX_SIDE))
                    img.save(out, quality=90)
                    counts[target] = counts.get(target, 0) + 1
        finally:
            tmp.unlink(missing_ok=True)
        marker.touch()
        print(f"  {key}: {Path(path).name} done ({sum(counts.values())} images so far)", flush=True)
    msg = f"{key}: " + ", ".join(f"{k.split('___')[1]}={v}" for k, v in sorted(counts.items()))
    if key == "plantdoc":
        msg += f"  (skipped {dups} duplicates of the field test set)"
    print(msg, flush=True)
    return counts


def main():
    keys = sys.argv[1:] or list(SOURCES)
    OUT.mkdir(parents=True, exist_ok=True)
    bank = test_hashes()
    with ThreadPoolExecutor(4) as ex:
        for f in [ex.submit(fetch, k, bank) for k in keys]:
            f.result()


if __name__ == "__main__":
    main()
