"""Curated agricultural knowledge base.

Loads plants.yaml, sources.yaml and diseases/*.yaml once and builds a complete, source-cited
treatment plan for any model class label. Nothing here is generated: every sentence comes from
the YAML files, which are reviewed by hand.
"""
import difflib
import re
import unicodedata
from functools import lru_cache
from pathlib import Path

import yaml

HERE = Path(__file__).resolve().parent
SEVERITY_LEVELS = ["Low", "Moderate", "High", "Critical"]

# Advice that depends on the *type* of problem rather than the specific disease.
KIND_ADVICE = {
    "fungal": {
        "watering": "Water at the base of the plant early in the day so leaves dry quickly; avoid sprinklers and overhead watering while the disease is active.",
        "soil": "Remove fallen infected leaves and debris from the soil surface; a mulch layer stops spores splashing up from the soil.",
        "fertilizer": "Keep nutrition balanced — excess nitrogen produces soft, dense growth that stays wet and is more susceptible. Do not stop feeding entirely: starved plants are also more susceptible.",
        "long_term": ["Rotate fungicide groups (different FRAC numbers) — never rely on one group.", "Keep a spray / scouting record so you can see what worked.", "Choose resistant or tolerant varieties next season."],
    },
    "oomycete": {
        "watering": "Avoid overhead irrigation and do not irrigate just before or during cool, wet, high-risk weather; improve field drainage.",
        "soil": "Improve drainage; never leave cull piles or infected plant material in or near the field.",
        "fertilizer": "Avoid late, heavy nitrogen; balanced potassium supports tissue strength.",
        "long_term": ["Follow weather-based blight warnings and protect before wet spells, not after.", "Rotate FRAC groups — resistance to single-site products (e.g. metalaxyl) is common.", "Use certified, disease-free seed or transplants."],
    },
    "bacterial": {
        "watering": "Switch to drip or furrow irrigation; splashing water spreads bacteria from plant to plant.",
        "soil": "Remove and destroy infected plant debris; do not work in the crop while leaves are wet.",
        "fertilizer": "Avoid excess nitrogen, which produces lush, susceptible growth.",
        "long_term": ["Use certified seed / clean nursery stock — many bacteria are seed-borne.", "Disinfect tools when moving between plants or fields.", "Rotate away from susceptible host crops for 2–3 seasons."],
    },
    "viral": {
        "watering": "Keep plants evenly watered to reduce stress; watering does not affect the virus itself.",
        "soil": "Remove weeds in and around the field — they shelter both the virus and its insect vectors.",
        "fertilizer": "Balanced feeding helps tolerant plants yield, but no fertilizer cures a virus.",
        "long_term": ["There is no chemical cure for plant viruses — manage the insect vector and remove infected plants early.", "Use resistant varieties and virus-free planting material.", "Use insect-proof nursery netting and yellow sticky traps for monitoring."],
    },
    "phytoplasma": {
        "watering": "Normal irrigation; avoid stress.",
        "soil": "Remove infected plants with their roots.",
        "fertilizer": "No fertilizer cures phytoplasma infection.",
        "long_term": ["Use healthy, treated planting material.", "Manage leafhopper vectors.", "Do not keep ratoon crops from infected fields."],
    },
    "pest": {
        "watering": "Water normally; drought-stressed plants suffer more from sap-sucking pests and mites (spraying leaf undersides with water also dislodges mites and aphids).",
        "soil": "Remove crop residues and weeds that shelter pests between seasons; deep ploughing exposes soil-dwelling stages.",
        "fertilizer": "Avoid excess nitrogen — it attracts aphids, whiteflies, jassids and leaf feeders.",
        "long_term": ["Scout weekly and spray only above the economic threshold your extension service uses.", "Protect natural enemies: prefer selective products and avoid broad-spectrum sprays early in the season.", "Rotate insecticide groups (different IRAC numbers)."],
    },
    "abiotic": {
        "watering": "Check irrigation first — uneven, insufficient or excessive watering is the most common cause of non-infectious problems.",
        "soil": "Have the soil tested for pH, salinity and nutrients before adding anything.",
        "fertilizer": "Apply only the nutrient a soil or leaf test shows is lacking; over-correcting can cause new problems.",
        "long_term": ["Test soil every 2–3 years.", "Keep records of weather, irrigation and fertilizer so causes can be traced.", "Add organic matter to improve soil structure and nutrient supply."],
    },
}

HEALTHY = {
    "name": "Healthy", "kind": "healthy", "pathogen": "—", "parts": [],
    "symptoms": "No disease symptoms recognised. The image looks like the healthy examples the model was trained on.",
    "causes": "—", "conditions": "—",
    "immediate": ["No treatment needed."],
    "organic": [], "chemical": [],
    "preventive": ["Keep monitoring weekly, especially after warm, wet weather.", "Water at the base and keep good airflow.", "Check leaf undersides for early pests."],
}

NO_PLANT = {
    "name": "No plant detected", "kind": "none", "pathogen": "—", "parts": [],
    "symptoms": "No plant leaf or fruit was detected in this image.",
    "causes": "—", "conditions": "—",
    "immediate": ["Photograph a single leaf or fruit filling most of the frame.", "Use even daylight and avoid harsh shadows.", "Keep the symptoms in sharp focus."],
    "organic": [], "chemical": [], "preventive": [],
}


def _norm(s: str) -> str:
    s = unicodedata.normalize("NFKC", s).lower()
    return re.sub(r"[^a-z0-9؀-ۿ]", "", s)


def _crop_prefix(label: str) -> str:
    return label.split("___", 1)[0] if "___" in label else ""


@lru_cache(maxsize=1)
def _load():
    plants = yaml.safe_load((HERE / "plants.yaml").read_text())
    src = yaml.safe_load((HERE / "sources.yaml").read_text())
    diseases = {}
    for f in sorted((HERE / "diseases").glob("*.yaml")):
        for k, v in (yaml.safe_load(f.read_text()) or {}).items():
            if k in diseases:
                raise ValueError(f"duplicate disease key {k} in {f.name}")
            diseases[k] = v
    by_prefix = {p["model"]: key for key, p in plants.items()}
    # Legacy PlantVillage prefix: the v2 model called citrus "Orange".
    by_prefix.setdefault("Orange", "citrus")
    return plants, src, diseases, by_prefix


def plants() -> dict:
    return _load()[0]


def sources() -> dict:
    return _load()[1]["sources"]


def disease_keys() -> list:
    return [k for k, v in _load()[2].items() if "alias_of" not in v]


def plant_key_for_label(label: str) -> str | None:
    return _load()[3].get(_crop_prefix(label))


def plant_info(key: str) -> dict | None:
    p = plants().get(key)
    if not p:
        return None
    return {"key": key, **{k: p.get(k) for k in ("name", "scientific", "family", "type", "about", "aliases", "care", "model")}}


def find_plant(text: str, limit: int = 5) -> list:
    """Match free text ('tamatar', 'Kinnow', 'Solanum lycopersicum') to plant keys."""
    q = _norm(text)
    if not q:
        return []
    scored = []
    for key, p in plants().items():
        names = [key, p["name"], p.get("scientific", ""), p.get("model", ""), *p.get("aliases", [])]
        names += re.split(r"[()/,]", p["name"])
        best = 0.0
        for n in names:
            nn = _norm(n)
            if not nn:
                continue
            if nn == q:
                best = 1.0
                break
            if len(q) >= 3 and (nn.startswith(q) or q.startswith(nn) and len(nn) >= 4):
                best = max(best, 0.9)
            best = max(best, difflib.SequenceMatcher(None, q, nn).ratio())
        if best >= 0.72:
            scored.append((best, key))
    scored.sort(reverse=True)
    return [{"key": k, "score": round(s, 2), **plant_info(k)} for s, k in scored[:limit]]


def _resolve(label: str) -> tuple[str, dict | None]:
    d = _load()[2]
    e = d.get(label)
    seen = set()
    while e and "alias_of" in e and label not in seen:
        seen.add(label)
        label = e["alias_of"]
        e = d.get(label)
    return label, e


def _ref_list(ids, crop_key):
    srcs = sources()
    out, seen = [], set()
    crop_refs = _load()[1].get("crop_refs", {}).get(crop_key, [])
    for rid in [*(ids or []), *crop_refs]:
        if rid in seen or rid not in srcs:
            continue
        seen.add(rid)
        s = srcs[rid]
        out.append({"id": rid, "title": s["title"], "publisher": s.get("publisher"), "url": s["url"],
                    "checked": str(s.get("checked", ""))})
    return out


def entry(label: str) -> dict:
    """Full treatment plan for a model class label (always returns a dict)."""
    crop_key = plant_key_for_label(label)
    plant = plants().get(crop_key, {}) if crop_key else {}
    if label.startswith("Background"):
        base, canon = dict(NO_PLANT), label
    elif label.endswith("healthy"):
        base, canon = dict(HEALTHY), label
    else:
        canon, e = _resolve(label)
        base = dict(e) if e else {
            "name": label.split("___")[-1].replace("_", " "), "kind": "unknown", "pathogen": "—", "parts": [],
            "symptoms": "", "causes": "", "conditions": "", "immediate": [], "organic": [], "chemical": [],
            "preventive": [], "_missing": True}
    kind = base.get("kind", "unknown")
    adv = KIND_ADVICE.get(kind, {})
    care = plant.get("care", {})
    out = {
        "label": canon,
        "crop_key": crop_key,
        "crop": plant.get("name"),
        "name": base.get("name"),
        "kind": kind,
        "pathogen": base.get("pathogen", "—"),
        "affected_parts": base.get("parts", []),
        "symptoms": base.get("symptoms", ""),
        "causes": base.get("causes", ""),
        "conditions": base.get("conditions", ""),
        "risk": base.get("risk"),
        "treatment": {
            "immediate": base.get("immediate", []),
            "organic": base.get("organic", []),
            "chemical": [dict(c) for c in base.get("chemical", [])],
            "preventive": base.get("preventive", []),
            "watering": " ".join(x for x in [adv.get("watering"), care.get("watering")] if x),
            "soil": " ".join(x for x in [adv.get("soil"), care.get("soil")] if x),
            "fertilizer": " ".join(x for x in [adv.get("fertilizer"), care.get("fertilizer")] if x),
            "long_term": [*base.get("long_term", []), *adv.get("long_term", [])],
        },
        "chemical_notice": _load()[1]["chemical_notice"] if base.get("chemical") else None,
        "references": _ref_list(base.get("refs"), crop_key),
        "kb_complete": not base.get("_missing", False),
    }
    if out["treatment"]["chemical"]:
        out["references"] += [r for r in _ref_list(["frac", "irac"], None) if r["id"] not in {x["id"] for x in out["references"]}]
    return out


def expert_help() -> list:
    return _load()[1].get("expert_help", [])


def lookup(label: str) -> dict:
    """Backwards-compatible short form used by the v1 API (/api/predict)."""
    e = entry(label)
    t = e["treatment"]
    actions = [*t["immediate"], *t["organic"][:1], *t["preventive"][:2]]
    if t["chemical"]:
        actions.append("Chemical options (active ingredients): " + ", ".join(c["ai"] for c in t["chemical"][:3])
                       + " — use a product registered for this crop and follow its label.")
    return {"cause": e["pathogen"], "symptoms": e["symptoms"], "actions": actions}


def all_chemical_ais() -> set:
    """Every active-ingredient string in the KB (used by the LLM output validator)."""
    out = set()
    for e in _load()[2].values():
        for c in e.get("chemical", []) or []:
            out.add(c["ai"].lower())
    return out
