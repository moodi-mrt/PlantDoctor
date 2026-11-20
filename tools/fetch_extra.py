"""Download extra training data: real field photos, fruits, vegetables, pests.

Sources are Hugging Face mirrors (Project-AgML) of open datasets; the license
and citation of each are in META below and are written next to the images
(data/extra/_sources/<key>.json). Each parquet shard is streamed, images are
shrunk to <= 384 px and written to data/extra/<Crop___Condition>/, then the
shard is deleted. Near-duplicate photos (dHash) within a class are skipped
across all sources. PlantDoc images that duplicate the held-out field test set
(data/plantdoc_test) are skipped so the field evaluation stays honest.

    .venv/bin/python tools/fetch_extra.py            # all sources
    .venv/bin/python tools/fetch_extra.py mango bean # just some
"""
import io
import json
import subprocess
import sys
import threading
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
DUP_BITS = 4       # dHash distance treated as the same photo (cross-source dedup)
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
    # ---- v3: Pakistan staple crops, citrus, vegetables and pests (added 2026-11) ----
    "cotton": ("cotton_leaf_disease_classification", "raw", {
        "Alternaria_Leaf": "Cotton___Alternaria_leaf_spot", "Bacterial_Blight": "Cotton___Bacterial_blight",
        "Fusarium_Wilt": "Cotton___Fusarium_wilt", "Healthy_Leaf": "Cotton___healthy",
        "Verticillium_Wilt": "Cotton___Verticillium_wilt"}),
    "cotton_bd": ("cotton_leaf_disease_classification_bangladesh_2", "raw", {
        "Bacterial Blight": "Cotton___Bacterial_blight", "Curl Virus": "Cotton___Leaf_curl_virus",
        "Healthy Leaf": "Cotton___healthy", "Herbicide Growth Damage": "Cotton___Herbicide_damage",
        "Leaf Hopper Jassids": "Cotton___Jassid_damage", "Leaf Redding": "Cotton___Leaf_reddening",
        "Leaf Variegation": None}),
    "paddy": ("paddy_disease_classification", "data", {
        "bacterial_leaf_blight": "Rice___Bacterial_leaf_blight", "bacterial_leaf_streak": "Rice___Bacterial_leaf_streak",
        "bacterial_panicle_blight": "Rice___Bacterial_panicle_blight", "blast": "Rice___Blast",
        "brown_spot": "Rice___Brown_spot", "dead_heart": "Rice___Stem_borer_dead_heart",
        "downy_mildew": "Rice___Downy_mildew", "hispa": "Rice___Hispa", "normal": "Rice___healthy",
        "tungro": "Rice___Tungro"}),
    "rice_leaf": ("rice_leaf_disease_classification", "data", {
        "Bacterial_Leaf_Blight": "Rice___Bacterial_leaf_blight", "Brown_Spot": "Rice___Brown_spot",
        "Healthy_Rice_Leaf": "Rice___healthy", "Leaf_Blast": "Rice___Blast", "Leaf_Scald": "Rice___Leaf_scald",
        "Sheath_Blight": "Rice___Sheath_blight"}),
    "rice_bd": ("rice_disease_classification_bangladesh", "raw", {
        "Healthy": "Rice___healthy", "Leaf scald": "Rice___Leaf_scald", "Rice Blast": "Rice___Blast",
        "Rice Leaffolder": "Rice___Leaf_folder", "Rice Tungro": "Rice___Tungro",
        "Insect": None, "Rice": None, "Rice Stripes": None}),
    "rice_in": ("rice_leaf_disease_classification_india", "data", {
        "Bacterialblight": "Rice___Bacterial_leaf_blight", "Blast": "Rice___Blast",
        "Brownspot": "Rice___Brown_spot", "Tungro": "Rice___Tungro"}),
    "sugarcane": ("sugarcane_leaf_disease_classification", "data", {
        "Banded Chlorosis": "Sugarcane___Banded_chlorosis", "Brown Spot": "Sugarcane___Brown_spot",
        "BrownRust": "Sugarcane___Brown_rust", "Grassy shoot": "Sugarcane___Grassy_shoot",
        "Healthy": "Sugarcane___healthy", "Pokkah Boeng": "Sugarcane___Pokkah_boeng",
        "Sett Rot": "Sugarcane___Sett_rot", "Smut": "Sugarcane___Smut", "Viral Disease": "Sugarcane___Mosaic_virus",
        "Yellow Leaf": "Sugarcane___Yellow_leaf", "Dried": None}),
    "citrus_uat": ("citrusuat_disease_classification", "data", {
        "Citrus_leafminer": "Citrus___Leafminer", "Greasy_spot": "Citrus___Greasy_spot",
        "HLB": "Citrus___Huanglongbing", "Healthy": "Citrus___healthy", "Red_scale": "Citrus___Scale_insects",
        "Texas_mite": "Citrus___Mites", "Fe": "Citrus___Nutrient_deficiency", "Mg": "Citrus___Nutrient_deficiency",
        "Mn": "Citrus___Nutrient_deficiency", "N": "Citrus___Nutrient_deficiency", "Zn": "Citrus___Nutrient_deficiency",
        "Red_scale_sequelae": None}),
    "lemon": ("lemon_leaf_disease_classification", "raw", {
        "Anthracnose": "Citrus___Anthracnose", "Citrus Canker": "Citrus___Canker", "Curl Virus": "Citrus___Leaf_curl",
        "Deficiency Leaf": "Citrus___Nutrient_deficiency", "Healthy Leaf": "Citrus___healthy",
        "Sooty Mould": "Citrus___Sooty_mould", "Spider Mites": "Citrus___Mites",
        "Bacterial Blight": None, "Dry Leaf": None}),
    "orange": ("orange_leaf_disease_classification", "data", {
        "citrus_canker": "Citrus___Canker", "citrus_greening": "Citrus___Huanglongbing",
        "yellow_dragon": "Citrus___Huanglongbing", "citrus_mealybugs": "Citrus___Mealybugs",
        "die_back": "Citrus___Dieback", "healthy_leaf": "Citrus___healthy", "powdery_mildew": "Citrus___Powdery_mildew",
        "spiny_whitefly": "Citrus___Whitefly", "shot_hole": None, "foliage_damaged": None, "yellow_leaves": None}),
    "corn_pest": ("corn_leaf_pest_classification", "raw", {
        "healthy": "Corn___healthy", "helminthosporium_leaf_blight": "Corn___Northern_Leaf_Blight",
        "spodoptera_frugiperda": "Corn___Fall_armyworm", "zonocerus_variegatus": None}),
    "potato": ("potato_leaf_disease_classification", "data", {
        "Healthy": "Potato___healthy", "Phytopthora": "Potato___Late_blight",
        "Bacteria": None, "Fungi": None, "Nematode": None, "Pest": None, "Virus": None}),
    "onion": ("COLD_onion_leaf_disease_classification", "raw", {
        "Iris yellow virus": "Onion___Iris_yellow_spot_virus",
        "Stemphylium leaf blight and collectrichum leaf blight": "Onion___Stemphylium_leaf_blight",
        "healthy": "Onion___healthy", "purple blotch": "Onion___Purple_blotch"}),
    "banana": ("banana_leaf_disease_classification", "data", {
        "healthy": "Banana___healthy", "segatoka": "Banana___Sigatoka", "xamthomonas": "Banana___Xanthomonas_wilt"}),
    "papaya": ("papaya_leaf_disease_classification_bangladesh", "raw", {
        "Healthy Leaf": "Papaya___healthy", "Leaf Curl": "Papaya___Leaf_curl", "Mealybug": "Papaya___Mealybug",
        "Mite Disease": "Papaya___Mites", "Mosaic": "Papaya___Mosaic_virus", "Ring Spot": "Papaya___Ringspot_virus"}),
    "date_palm": ("date_palm_leaf_disease_classification", "data", {
        "Black Scorch": "Date_palm___Black_scorch", "Fusarium Wilt": "Date_palm___Fusarium_wilt",
        "Healthy sample": "Date_palm___healthy", "Leaf Spots": "Date_palm___Leaf_spot",
        "Magnesium Deficiency": "Date_palm___Nutrient_deficiency", "Manganese Deficiency": "Date_palm___Nutrient_deficiency",
        "Potassium Deficiency": "Date_palm___Nutrient_deficiency", "Parlatoria Blanchardi": "Date_palm___Scale_insect",
        "Rachis Blight": "Date_palm___Rachis_blight"}),
    "cucumber": ("cucumber_disease_classification", "data", {
        "Anthracnose": "Cucumber___Anthracnose", "Bacterial_Wilt": "Cucumber___Bacterial_wilt",
        "Belly_Rot": "Cucumber___Belly_rot", "Downy_Mildew": "Cucumber___Downy_mildew",
        "Fresh_Cucumber": "Cucumber___healthy", "Fresh_Leaf": "Cucumber___healthy",
        "Gummy_Stem_Blight": "Cucumber___Gummy_stem_blight", "Pythium_Fruit_Rot": "Cucumber___Pythium_fruit_rot"}),
}

# Attribution per source (written to data/extra/_sources/<key>.json and data/catalog.json).
# "license" is what the dataset card / original page states; None = not stated on the mirror, check the origin.
META = {
    "plantdoc": ("CC BY-SA 4.0", "Singh et al. 2020, PlantDoc", "https://github.com/pratikkayal/PlantDoc-Dataset"),
    "cotton": ("CC BY-NC 4.0", "Cotton leaf disease dataset (AgML mirror)", None),
    "cotton_bd": ("CC BY 4.0", "Cotton leaf disease dataset, Bangladesh (AgML mirror)", None),
    "paddy": (None, "Petchiammal et al. 2022, Paddy Doctor, IEEE Dataport", "https://dx.doi.org/10.21227/hz4v-af08"),
    "rice_leaf": (None, "Rice disease dataset (Kaggle anshulm257)", "https://www.kaggle.com/datasets/anshulm257/rice-disease-dataset"),
    "rice_bd": ("CC BY 4.0", "Rice disease dataset, Bangladesh (AgML mirror)", None),
    "rice_in": ("CC BY 4.0", "Rice leaf disease dataset, India (AgML mirror)", None),
    "sugarcane": ("CC BY 4.0", "Sugarcane leaf disease dataset (AgML mirror)", None),
    "citrus_uat": ("CC BY 4.0", "CitrusUAT, University of Agriculture Faisalabad, Pakistan (AgML mirror)", None),
    "lemon": ("CC BY 4.0", "Lemon leaf disease dataset (AgML mirror)", None),
    "orange": (None, "Emon et al. 2025, sweet orange leaf dataset, Mendeley Data", "https://doi.org/10.17632/f7cr74mwpj.2"),
    "corn_pest": ("CC BY 4.0", "Corn leaf pest dataset (AgML mirror)", None),
    "potato": ("CC BY 4.0", "Potato leaf disease dataset (AgML mirror)", None),
    "onion": ("CC BY 4.0", "COLD onion leaf disease dataset (AgML mirror)", None),
    "banana": ("CC BY 4.0", "Banana leaf disease dataset (AgML mirror)", None),
    "papaya": ("CC BY 4.0", "Papaya leaf disease dataset, Bangladesh (AgML mirror)", None),
    "date_palm": ("CC BY 4.0", "Date palm leaf disease dataset (AgML mirror)", None),
    "cucumber": (None, "Sultana et al. 2022, Cucumber Disease Recognition Dataset, Mendeley Data", "https://doi.org/10.17632/y6d3z6f8z9.1"),
}


def _full(repo):
    return repo if "/" in repo else f"Project-AgML/{repo}"


def get_json(url):
    return json.loads(urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=60).read())


def label_names(repo, config):
    card = get_json(f"{HF}/api/datasets/{_full(repo)}")["cardData"]["dataset_info"]
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


_class_banks, _bank_lock = {}, threading.Lock()


def is_class_dup(target, h):
    """True if a near-identical image is already stored for this class (any source).
    Several mirrors re-publish the same photos, so this keeps the set duplicate-free."""
    with _bank_lock:
        bank = _class_banks.get(target)
        if bank is None:
            bank = []
            for f in (OUT / target).glob("*.jpg") if (OUT / target).is_dir() else []:
                try:
                    bank.append(dhash(Image.open(f)))
                except Exception:
                    pass
            _class_banks[target] = bank
        if bank and (np.unpackbits(np.stack(bank) ^ h, axis=1).sum(1) <= DUP_BITS).any():
            return True
        bank.append(h)
        return False


def write_meta(key, counts, dups):
    repo, config, mapping = SOURCES[key]
    lic, citation, origin = META.get(key, ("CC BY 4.0", repo, None))
    d = OUT / "_sources"
    d.mkdir(exist_ok=True)
    full = repo if "/" in repo else f"Project-AgML/{repo}"
    (d / f"{key}.json").write_text(json.dumps({
        "key": key, "mirror": f"{HF}/datasets/{full}", "config": config, "origin": origin,
        "license": lic, "citation": citation, "label_map": mapping,
        "images_kept": counts, "duplicates_skipped": dups, "max_side_px": MAX_SIDE,
        "cap_per_class": CAP, "fetched": time.strftime("%Y-%m-%d")}, indent=1))


def shards(repo, config):
    tree = get_json(f"{HF}/api/datasets/{_full(repo)}/tree/main/{config}")
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
        download(f"{HF}/datasets/{_full(repo)}/resolve/main/{path}", tmp)
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
                    h = dhash(img)
                    if key == "plantdoc" and is_test_dup(h, bank):
                        dups += 1
                        continue
                    if is_class_dup(target, h):
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
    msg += f"  (skipped {dups} duplicates)"
    print(msg, flush=True)
    write_meta(key, counts, dups)
    return counts


def main():
    keys = sys.argv[1:] or list(SOURCES)
    OUT.mkdir(parents=True, exist_ok=True)
    bank = test_hashes()
    with ThreadPoolExecutor(2) as ex:  # 2: parquet row groups are held in RAM
        for f in [ex.submit(fetch, k, bank) for k in keys]:
            f.result()


if __name__ == "__main__":
    main()
