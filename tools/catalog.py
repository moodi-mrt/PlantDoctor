"""Write data/catalog.json + docs/datasets.md: every dataset with source, licence, image count and
actual on-disk size (stored, resized copies) and the volume downloaded to build it."""
import json
import time
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"


def du(paths):
    return sum(p.stat().st_size for p in paths if p.is_file())


def main():
    rows = []
    pv = DATA / "raw" / "Plant_leave_diseases_dataset_without_augmentation"
    files = list(pv.rglob("*.*"))
    rows.append({"key": "plantvillage", "name": "PlantVillage (Hughes & Salathé 2015) — lab photos, 38 classes + background",
                 "license": "CC0 / public (Mendeley Data mirror)", "origin": "https://data.mendeley.com/datasets/tywbtsjrjv/1",
                 "images": len(files), "stored_mb": round(du(files) / 1e6, 1), "use": "training (disease model)"})
    by_src = defaultdict(list)
    for f in (DATA / "extra").rglob("*.jpg"):
        by_src[f.name.split("_", 1)[0]].append(f)
    metas = {json.loads(p.read_text())["key"]: json.loads(p.read_text()) for p in (DATA / "extra" / "_sources").glob("*.json")}
    alias = {"cotton": "cotton", "nwrd": "nwrd", "jic": "jic"}
    for src, fs in sorted(by_src.items()):
        m = metas.get(alias.get(src, src), {})
        rows.append({"key": src, "name": m.get("citation", src), "license": m.get("license"),
                     "origin": m.get("origin") or m.get("mirror"), "images": len(fs),
                     "classes": len({f.parent.name for f in fs}), "stored_mb": round(du(fs) / 1e6, 1),
                     "duplicates_removed": m.get("duplicates_skipped"), "use": "training (disease model)"})
    pf = list((DATA / "pests").rglob("*.jpg"))
    pm = json.loads((DATA / "pests" / "metadata.json").read_text()) if (DATA / "pests" / "metadata.json").exists() else {}
    rows.append({"key": "ip102", "name": pm.get("citation", "IP102"), "license": pm.get("license"), "origin": pm.get("origin"),
                 "images": len(pf), "classes": 102, "stored_mb": round(du(pf) / 1e6, 1), "use": "training (insect-pest model)"})
    pt = [f for f in (DATA / "plantdoc_test").rglob("*") if f.is_file()]
    rows.append({"key": "plantdoc_test", "name": "PlantDoc test split (Singh et al. 2020) — real field photos",
                 "license": "CC BY 4.0", "origin": "https://github.com/pratikkayal/PlantDoc-Dataset", "images": len(pt),
                 "stored_mb": round(du(pt) / 1e6, 1), "use": "external evaluation only (never trained on)"})
    dl = list((DATA / "downloads").rglob("*.zip"))
    totals = {"datasets": len(rows), "images": sum(r["images"] for r in rows),
              "stored_gb": round(sum(r["stored_mb"] for r in rows) / 1e3, 2),
              "archives_kept_gb": round(du(dl) / 1e9, 2),
              "note": "Images are stored resized (<= 384-512 px), so stored size is far below the downloaded volume. "
                      "Downloaded parquet shards were streamed and deleted after conversion."}
    out = {"generated": time.strftime("%Y-%m-%d %H:%M"), "totals": totals, "datasets": rows}
    (DATA / "catalog.json").write_text(json.dumps(out, indent=1))
    (ROOT / "docs").mkdir(exist_ok=True)
    md = [f"# Datasets\n\nGenerated {out['generated']} by `tools/catalog.py`.\n",
          f"**Total: {totals['images']:,} images in {totals['datasets']} datasets, {totals['stored_gb']} GB stored** "
          f"(+ {totals['archives_kept_gb']} GB of original archives kept for wheat).\n\n{totals['note']}\n",
          "| Dataset | Licence | Images | Classes | Stored (MB) | Duplicates removed | Use |", "|---|---|---:|---:|---:|---:|---|"]
    for r in rows:
        md.append(f"| [{r['name']}]({r['origin']}) | {r['license'] or 'not stated — see origin'} | {r['images']:,} | "
                  f"{r.get('classes', '')} | {r['stored_mb']} | {r.get('duplicates_removed') or ''} | {r['use']} |")
    (ROOT / "docs" / "datasets.md").write_text("\n".join(md) + "\n")
    print(json.dumps(totals, indent=1))


if __name__ == "__main__":
    main()
