"""Mirror curated reference data (knowledge base, products, sources, datasets) into the DB.

Idempotent: safe to run on every start. The YAML/JSON files stay the source of truth.
"""
import json
import logging

from sqlalchemy import delete

from ..config import DATA_DIR, ROOT
from ..db import Crop, DatasetMeta, Disease, ExternalSource, Product, SessionLocal, Treatment
from ..knowledge import kb

log = logging.getLogger("plantdoctor.seed")


def sync(model_classes: set | None = None, model_crops: set | None = None):
    with SessionLocal() as s:
        for key, p in kb.plants().items():
            prefix = "Citrus" if p["model"] in ("Citrus", "Orange") else p["model"]
            s.merge(Crop(key=key, name=p["name"], scientific=p.get("scientific"), family=p.get("family"),
                         type=p.get("type"), model_prefix=p["model"], supported=bool(model_crops and prefix in model_crops),
                         data={"aliases": p.get("aliases", []), "about": p.get("about"), "care": p.get("care", {})}))
        s.flush()
        s.execute(delete(Treatment))
        for label in kb.disease_keys():
            e = kb.entry(label)
            s.merge(Disease(label=label, crop_key=e["crop_key"], name=e["name"], kind=e["kind"],
                            pathogen=(e["pathogen"] or "")[:255], data=e, in_model=bool(model_classes and label in model_classes)))
            t = e["treatment"]
            for cat in ("immediate", "organic", "preventive"):
                for txt in t[cat]:
                    s.add(Treatment(disease_label=label, category=cat, text=txt))
            for c in t["chemical"]:
                s.add(Treatment(disease_label=label, category="chemical", text=c.get("note") or c["ai"],
                                active_ingredient=c["ai"][:160], resistance_group=c.get("group")))
        for sid, src in kb.sources().items():
            s.merge(ExternalSource(id=sid, title=src["title"], publisher=src.get("publisher"), url=src["url"],
                                   kind="reference", checked=str(src.get("checked", ""))))
        for sid, title, url in [("open_meteo", "Open-Meteo weather API", "https://open-meteo.com/"),
                                ("anthropic", "Claude API (explanations, assistant)", "https://www.anthropic.com/"),
                                ("kissanghar", "Kissan Ghar (agri-input store, Pakistan)", "https://www.kissanghar.pk/"),
                                ("daraz", "Daraz.pk (marketplace search links)", "https://www.daraz.pk/")]:
            s.merge(ExternalSource(id=sid, title=title, url=url, kind="api" if sid in ("open_meteo", "anthropic") else "marketplace"))
        pf = ROOT / "app" / "knowledge" / "products.json"
        if pf.exists():
            s.execute(delete(Product))
            for p in json.loads(pf.read_text())["products"]:
                s.add(Product(id=p["id"], title=p["title"][:255], company=p.get("company"), active_ingredient=p["active_ingredient"][:255],
                              matches_ai=p.get("matches_ai"), pack_size=p.get("pack_size"), price_pkr=p.get("price_pkr"),
                              store=p["store"], url=p["url"], verified_on=p["verified_on"]))
        for f in sorted((DATA_DIR / "extra" / "_sources").glob("*.json")):
            d = json.loads(f.read_text())
            s.merge(DatasetMeta(key=d["key"], name=d.get("citation") or d["key"], license=d.get("license"), data=d))
        pm = DATA_DIR / "pests" / "metadata.json"
        if pm.exists():
            d = json.loads(pm.read_text())
            s.merge(DatasetMeta(key="ip102", name=d["citation"], license=d["license"], data=d))
        s.commit()
    log.info("reference data synced")
