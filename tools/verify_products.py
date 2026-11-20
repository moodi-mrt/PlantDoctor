"""Verify agricultural product listings against their public product pages and write
app/knowledge/products.json.

Only facts read from the live product page are stored (title, company, active ingredient,
pack size, sale price), with the URL and the date it was checked. Products whose page does not
load or does not state an active ingredient are dropped — nothing is filled in by hand.

Input: a JSON list of candidate listings [{"store": "kissanghar", "id": "96"}, ...]
(see tools/product_candidates.json). The app shows these as "Verified listing (checked
<date>)"; prices change, so the UI always shows the check date and links to the live page.

Kissan Ghar's robots.txt allows search-style use (Content-Signal: search=yes,
use=reference): we store short excerpts + links only, fetch politely (1 request/second)
and never use the content for AI training.

    .venv/bin/python tools/verify_products.py tools/product_candidates.json
"""
import html
import json
import re
import sys
import time
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "app" / "knowledge" / "products.json"
UA = {"User-Agent": "PlantDoctor/3 product-link checker (open-source plant health app)"}

STORES = {
    "kissanghar": {
        "name": "Kissan Ghar", "home": "https://www.kissanghar.pk/",
        "url": "https://www.kissanghar.pk/product-details?c={id}",
        "location": "Sargodha, Pakistan (online store, delivers nationwide)",
    },
}


def text_of(page: str) -> str:
    t = re.sub(r"<script.*?</script>|<style.*?</style>", " ", page, flags=re.S | re.I)
    t = html.unescape(re.sub(r"<[^>]+>", " ", t))
    return re.sub(r"\s+", " ", t)


def field(t: str, label: str, stop: str) -> str | None:
    m = re.search(rf"{label}:\s*(.+?)\s*(?:{stop})", t)
    return m.group(1).strip() if m else None


def parse_kissanghar(page: str) -> dict | None:
    title = re.search(r"<title>(.*?)</title>", page, re.S)
    t = text_of(page)
    ai = field(t, "Active Ingredient", "Pack Size:|Delivery Charges")
    if not title or not ai:
        return None
    price = re.search(r"Sale Price:\s*Rs\.?\s*([\d,]+(?:\.\d+)?)", t)
    return {
        "title": html.unescape(title.group(1)).replace(" - Kissan Ghar", "").strip(),
        "company": field(t, "Company", "Category:"),
        "category": field(t, "Category", "Active Ingredient:"),
        "active_ingredient": ai,
        "pack_size": field(t, "Pack Size", "Delivery Charges|Actual Price"),
        "price_pkr": float(price.group(1).replace(",", "")) if price else None,
    }


def main():
    cands = json.loads(Path(sys.argv[1]).read_text())
    today = time.strftime("%Y-%m-%d")
    out, dropped = [], []
    for c in cands:
        store = STORES[c["store"]]
        url = store["url"].format(id=c["id"])
        try:
            page = urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=30).read().decode("utf-8", "ignore")
            info = parse_kissanghar(page)
        except Exception as e:
            info, err = None, str(e)
        else:
            err = "page has no product details"
        if not info:
            dropped.append({**c, "reason": err})
        else:
            out.append({"id": f"{c['store']}-{c['id']}", "store": store["name"], "store_url": store["home"],
                        "store_location": store["location"], "url": url, **info,
                        "matches_ai": c.get("ai"), "verified_on": today})
            print(f"ok  {info['title'][:70]} | {info['active_ingredient'][:40]} | Rs {info['price_pkr']}", flush=True)
        time.sleep(1.0)
    OUT.write_text(json.dumps({"generated": today, "note": "Listings verified against the live product page on "
                               "verified_on. Prices change — always check the store page before buying.",
                               "products": out, "dropped": dropped}, indent=1, ensure_ascii=False))
    print(f"{len(out)} verified, {len(dropped)} dropped -> {OUT}")


if __name__ == "__main__":
    main()
