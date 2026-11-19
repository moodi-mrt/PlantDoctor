"""Download the PlantDoc *test* split (real field photos) for cross-domain evaluation.
Source: https://github.com/pratikkayal/PlantDoc-Dataset (CC BY 4.0, Singh et al. 2020)."""
import json
import sys
import urllib.parse
import urllib.request
from pathlib import Path

OUT = Path(__file__).resolve().parent.parent / "data" / "plantdoc_test"
API = "https://api.github.com/repos/pratikkayal/PlantDoc-Dataset/contents/test"


def get(url):
    req = urllib.request.Request(url, headers={"User-Agent": "plantdoctor-eval"})
    return urllib.request.urlopen(req, timeout=60).read()


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    n = 0
    for d in json.loads(get(API)):
        if d["type"] != "dir":
            continue
        dst = OUT / d["name"]; dst.mkdir(exist_ok=True)
        for f in json.loads(get(API + "/" + urllib.parse.quote(d["name"]))):
            if f["type"] != "file" or (dst / f["name"]).exists():
                continue
            try:
                (dst / f["name"]).write_bytes(get(f["download_url"])); n += 1
            except Exception as e:  # a few files in the repo are broken links
                print("skip", f["name"], e, file=sys.stderr)
        print(f"{d['name']}: {len(list(dst.iterdir()))}")
    print("downloaded", n)


if __name__ == "__main__":
    main()
