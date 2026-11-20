"""Product suggestions for a diagnosis.

Two clearly separated tiers:
  * "verified" — listings whose product page was checked by tools/verify_products.py; we show
    exactly what the page said (title, company, active ingredient, pack size, price) and the date.
  * "search"   — marketplace search links for an active ingredient. These are suggestions to look,
    NOT claims that a specific product exists, is registered, or has a given price.

A product is matched to a diagnosis only through the active ingredients listed in the curated
knowledge base for that disease.
"""
from __future__ import annotations

import json
import re
import urllib.parse
from functools import lru_cache
from pathlib import Path

from ..knowledge import kb

PRODUCTS = Path(__file__).resolve().parent.parent / "knowledge" / "products.json"
ALIASES = {"chlorothalonil": ["chlorothlonil"], "difenoconazole": ["diafenoconazole", "difenconazole"],
           "thiophanate-methyl": ["thiophenate methyl", "thiophanate methyl"], "copper oxychloride": ["copper oxy chloride"],
           "lambda-cyhalothrin": ["lambda cyhalothrin"], "metalaxyl-m": ["metalaxyl m", "mefenoxam"],
           "sulfur": ["sulphur"], "bacillus thuringiensis": ["b.t.", "bt "]}


def _norm(s: str) -> str:
    return re.sub(r"\s+", " ", re.sub(r"[^a-z0-9 ]", " ", s.lower())).strip()


def _parts(ai: str) -> list[str]:
    """'azoxystrobin + propiconazole' -> ['azoxystrobin', 'propiconazole']; strips notes in brackets."""
    ai = re.sub(r"\(.*?\)", "", ai.lower())
    out = []
    for p in re.split(r"\s*(?:\+|/|,| and )\s*", ai):
        p = p.strip()
        if len(p) > 3 and p not in ("nutrient",):
            out.append(p)
    return out


def _contains(text: str, ai: str) -> bool:
    """Whole-word match, so 'metalaxyl m' does not match 'metalaxyl mancozeb'."""
    t = f" {_norm(text)} "
    return any(re.search(rf"(?<![a-z0-9]){re.escape(_norm(v))}(?![a-z0-9])", t) for v in [ai, *ALIASES.get(ai, [])])


@lru_cache(maxsize=1)
def _load() -> dict:
    if not PRODUCTS.exists():
        return {"generated": None, "products": []}
    return json.loads(PRODUCTS.read_text())


@lru_cache(maxsize=1)
def _vocab() -> set:
    v = set()
    for ai in kb.all_chemical_ais():
        v.update(_parts(ai))
    return v


def search_links(ai: str) -> list[dict]:
    q = urllib.parse.quote_plus(ai)
    return [
        {"store": "Daraz.pk", "url": f"https://www.daraz.pk/catalog/?q={q}", "type": "search",
         "label": f"Search Daraz for “{ai}”"},
        {"store": "Kissan Ghar", "url": "https://www.kissanghar.pk/products?category=Pesticides", "type": "search",
         "label": "Browse Kissan Ghar pesticides"},
    ]


def for_label(label: str, limit_per_ai: int = 3) -> dict:
    e = kb.entry(label)
    chem = e["treatment"]["chemical"]
    data = _load()
    groups = []
    for c in chem:
        parts = _parts(c["ai"])
        if not parts or c.get("group") == "nutrient":
            continue
        matches = []
        for p in data["products"]:
            text = p["active_ingredient"] + " " + p["title"]
            if all(_contains(text, x) for x in parts):
                found = {x for x in _vocab() if _contains(p["active_ingredient"], x)}
                # 'metalaxyl' is contained in 'metalaxyl-m' etc. — drop names that are part of a wanted one.
                extra = sorted(x for x in found - set(parts) if not any(x in w for w in parts))
                # Ingredients we don't have in our vocabulary still make it a mixture:
                # several percentages / "+" / "plus" in the active-ingredient text.
                ai_txt = p["active_ingredient"].lower()
                n_listed = max(len(re.findall(r"\d+(?:\.\d+)?\s*(?:%|g/?k?g|g/l|w/w)", ai_txt)),
                               len(re.split(r"\+| plus ", ai_txt)))
                if not extra and n_listed > len(parts):
                    extra = ["another ingredient (see label)"]
                matches.append({**{k: p.get(k) for k in ("id", "title", "company", "active_ingredient", "pack_size",
                                                          "price_pkr", "store", "url", "verified_on")},
                                "type": "verified", "combination": bool(extra), "also_contains": extra,
                                "seed_treatment": "seed treatment" in p["title"].lower() or "seed dressing" in p["title"].lower()})
        # Exact single-ingredient foliar products first; seed treatments and mixtures after.
        matches.sort(key=lambda m: (m["seed_treatment"], m["combination"], m["price_pkr"] is None))
        groups.append({"active_ingredient": c["ai"], "resistance_group": c.get("group"), "note": c.get("note"),
                       "verified": matches[:limit_per_ai], "search": search_links(parts[0] if len(parts) == 1 else c["ai"])})
    return {"label": label, "disease": e["name"], "crop": e["crop"], "groups": groups,
            "notice": e.get("chemical_notice"), "catalog_checked": data.get("generated"),
            "disclaimer": "Verified listings were checked on the date shown; prices and stock change. Search links "
                          "are suggestions only. Confirm the product is registered for your crop and follow its label."}


def flat_verified(label: str) -> list[dict]:
    seen, out = set(), []
    for g in for_label(label)["groups"]:
        for p in g["verified"]:
            if p["id"] not in seen:
                seen.add(p["id"])
                out.append(p)
    return out
