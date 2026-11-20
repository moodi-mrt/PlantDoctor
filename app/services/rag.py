"""Retrieval over the curated knowledge base (BM25, no external dependencies).

Documents: one per disease entry (symptoms, causes, conditions, treatment) and one per plant
(care notes). The assistant only sees retrieved documents, and each carries its reference list
so answers can cite real sources.
"""
from __future__ import annotations

import math
import re
from collections import Counter
from functools import lru_cache

from ..knowledge import kb

TOKEN = re.compile(r"[a-z0-9؀-ۿ]+")
STOP = set("a an and are as at be by can do does for from has have how i if in is it its my of on or should "
           "the their them there these this to was what when where which who why will with you your me we our "
           "plant plants leaf leaves".split())


def tok(s: str) -> list[str]:
    return [t for t in TOKEN.findall(s.lower()) if t not in STOP and len(t) > 1]


def _disease_doc(label: str) -> dict:
    e = kb.entry(label)
    t = e["treatment"]
    text = "\n".join([
        f"{e['name']} of {e['crop']} ({e['kind']}). Cause: {e['pathogen']}.",
        f"Affected parts: {', '.join(e['affected_parts'])}.",
        f"Symptoms: {e['symptoms']}", f"Causes: {e['causes']}", f"Favourable conditions: {e['conditions']}",
        "Immediate actions: " + " ".join(t["immediate"]),
        "Organic / cultural: " + " ".join(t["organic"]),
        "Chemical options (active ingredient — resistance group; no doses): "
        + "; ".join(f"{c['ai']} — {c.get('group', '')}" for c in t["chemical"]),
        "Prevention: " + " ".join(t["preventive"]),
        f"Watering: {t['watering']}", f"Soil: {t['soil']}", f"Fertilizer: {t['fertilizer']}",
        "Long-term: " + " ".join(t["long_term"]),
    ])
    return {"id": label, "type": "disease", "title": f"{e['name']} — {e['crop']}", "text": text,
            "references": e["references"], "chemical": t["chemical"], "notice": e.get("chemical_notice")}


def _plant_doc(key: str) -> dict:
    p = kb.plant_info(key)
    c = p.get("care") or {}
    text = (f"{p['name']} ({p['scientific']}, family {p['family']}), {p['type']}. Also called: "
            f"{', '.join(p.get('aliases') or [])}. {p.get('about', '')}\nWatering: {c.get('watering', '')}\n"
            f"Soil: {c.get('soil', '')}\nFertilizer: {c.get('fertilizer', '')}")
    refs = kb.entry(f"{p['model']}___healthy")["references"]
    return {"id": f"plant:{key}", "type": "plant", "title": f"{p['name']} — growing guide", "text": text,
            "references": refs, "chemical": [], "notice": None}


@lru_cache(maxsize=1)
def index():
    docs = [_disease_doc(l) for l in kb.disease_keys()] + [_plant_doc(k) for k in kb.plants()]
    toks = [tok(d["title"] + " " + d["title"] + " " + d["text"]) for d in docs]
    df = Counter(t for ts in toks for t in set(ts))
    n = len(docs)
    idf = {t: math.log(1 + (n - c + 0.5) / (c + 0.5)) for t, c in df.items()}
    avg = sum(map(len, toks)) / n
    return docs, [Counter(t) for t in toks], [len(t) for t in toks], idf, avg


def search(query: str, k: int = 4, boost: list[str] | None = None) -> list[dict]:
    docs, tfs, lens, idf, avg = index()
    q = tok(query)
    k1, b = 1.4, 0.75
    scores = []
    for i, d in enumerate(docs):
        s = 0.0
        for t in q:
            f = tfs[i].get(t)
            if f:
                s += idf[t] * f * (k1 + 1) / (f + k1 * (1 - b + b * lens[i] / avg))
        if boost and d["id"] in boost:
            s += 50.0
        if s > 0:
            scores.append((s, i))
    scores.sort(reverse=True)
    return [{**docs[i], "score": round(s, 2)} for s, i in scores[:k]]


def get(doc_id: str) -> dict | None:
    for d in index()[0]:
        if d["id"] == doc_id:
            return d
    return None
