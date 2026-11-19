"""Cross-domain test: PlantVillage-trained model on PlantDoc field photos.

Reports class accuracy, top-5 accuracy, crop-level accuracy and how often the
app's confidence gate would have warned the user. Writes reports/field_metrics.json.
"""
import json
import re
import sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from PIL import Image  # noqa: E402

from app.inference import CONFIDENT, Predictor, pretty  # noqa: E402

# PlantDoc folder -> keywords that must all appear in the PlantVillage label
MAP = {
    "Apple Scab Leaf": ("apple", "scab"), "Apple leaf": ("apple", "healthy"),
    "Apple rust leaf": ("apple", "rust"), "Bell_pepper leaf spot": ("pepper", "bacterial"),
    "Bell_pepper leaf": ("pepper", "healthy"), "Blueberry leaf": ("blueberry", "healthy"),
    "Cherry leaf": ("cherry", "healthy"), "Corn Gray leaf spot": ("corn", "cercospora"),
    "Corn leaf blight": ("corn", "northern"), "Corn rust leaf": ("corn", "commonrust"),
    "Peach leaf": ("peach", "healthy"), "Potato leaf early blight": ("potato", "early"),
    "Potato leaf late blight": ("potato", "late"), "Raspberry leaf": ("raspberry", "healthy"),
    "Soyabean leaf": ("soybean", "healthy"), "Squash Powdery mildew leaf": ("squash", "mildew"),
    "Strawberry leaf": ("strawberry", "healthy"), "Tomato Early blight leaf": ("tomato", "early"),
    "Tomato Septoria leaf spot": ("tomato", "septoria"), "Tomato leaf bacterial spot": ("tomato", "bacterial"),
    "Tomato leaf late blight": ("tomato", "late"), "Tomato leaf mosaic virus": ("tomato", "mosaic"),
    "Tomato leaf yellow virus": ("tomato", "yellow"), "Tomato leaf": ("tomato", "healthy"),
    "Tomato mold leaf": ("tomato", "mold"), "grape leaf black rot": ("grape", "blackrot"),
    "grape leaf": ("grape", "healthy"),
}
norm = lambda s: re.sub(r"[^a-z]", "", s.lower())


def main():
    pr = Predictor()
    idx = {}
    for k, keys in MAP.items():
        hits = [i for i, c in enumerate(pr.classes) if all(x in norm(c) for x in keys)]
        assert len(hits) == 1, (k, hits)
        idx[k] = hits[0]

    data = ROOT / "data" / "plantdoc_test"
    tot = defaultdict(int); per = defaultdict(lambda: defaultdict(int)); confusions = defaultdict(int)
    for folder, ti in idx.items():
        for f in sorted((data / folder).glob("*")):
            try:
                img = Image.open(f).convert("RGB")
            except Exception:
                continue
            r = pr.predict(img)
            labels = [p["label"] for p in r["top"]]
            true = pr.classes[ti]
            ok = labels[0] == true
            confident = r["top"][0]["prob"] >= CONFIDENT
            s = per[folder]
            s["n"] += 1; s["top1"] += ok; s["top5"] += true in labels
            s["crop"] += pretty(labels[0])[0] == pretty(true)[0]
            tot["n"] += 1; tot["top1"] += ok; tot["top5"] += true in labels
            tot["crop"] += pretty(labels[0])[0] == pretty(true)[0]
            tot["confident"] += confident; tot["confident_wrong"] += confident and not ok
            tot["confident_right"] += confident and ok
            if not ok:
                confusions[f"{pretty(true)[0]}: {pretty(true)[1]}  ›  {pretty(labels[0])[0]}: {pretty(labels[0])[1]}"] += 1

    n = tot["n"]
    out = {
        "n_images": n,
        "top1_acc": tot["top1"] / n, "top5_acc": tot["top5"] / n, "crop_acc": tot["crop"] / n,
        "share_flagged_low_conf": 1 - tot["confident"] / n,
        "acc_when_confident": tot["confident_right"] / max(tot["confident"], 1),
        "acc_when_flagged": (tot["top1"] - tot["confident_right"]) / max(n - tot["confident"], 1),
        "per_class": {k: {"n": v["n"], "top1": v["top1"] / v["n"], "top5": v["top5"] / v["n"], "crop": v["crop"] / v["n"]}
                      for k, v in per.items() if v["n"]},
        "top_confusions": sorted(confusions.items(), key=lambda kv: -kv[1])[:12],
    }
    (ROOT / "reports" / "field_metrics.json").write_text(json.dumps(out, indent=1))
    print(json.dumps({k: v for k, v in out.items() if k not in ("per_class",)}, indent=1))


if __name__ == "__main__":
    main()
