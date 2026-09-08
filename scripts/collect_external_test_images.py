"""
Collects fresh, never-seen-before test images for each of the 16 classes.

WHY NOT GOOGLE IMAGES: there is no API for it, scraping the results page breaks
Google's terms, and the images it surfaces are mostly all-rights-reserved stock
photos with no usable licence. Wikimedia Commons is used instead - a real API, and
everything on it is freely licensed with attribution recorded per file.

THE POINT OF THIS SET: these images must not already be in the model's train, val or
test splits, or they prove nothing. Every candidate is perceptually hashed (dHash,
the same method that exposed 25% leakage in the old split) and rejected if it matches
anything in data/re-training_data within a Hamming distance of 6. Exact-hash checking
would not be enough - a re-encoded or resized copy of a training image would sail
through it.

Per the project's standing sourcing rules (docs/DATASET_UPDATE_LOG.md), a filename or
search hit is NOT evidence of Indian road context - Commons returns potholes in Kyiv
and Montreal for "pothole". Queries below lead with India-specific terms, but the
result still has to be eyeballed before anyone trusts it. Every image's source URL and
licence is written to manifest.json alongside, so provenance is never lost.

Usage:
    python scripts/collect_external_test_images.py
    python scripts/collect_external_test_images.py --per-class 10 --classes cow,goat
"""
import argparse
import json
import time
import urllib.parse
import urllib.request
from collections import defaultdict
from io import BytesIO
from pathlib import Path

import yaml
from PIL import Image

BASE = Path(__file__).resolve().parent.parent
RETRAIN = BASE / "data/re-training_data"
OUT = BASE / "data/external_test_images"
API = "https://commons.wikimedia.org/w/api.php"
UA = "CivicMonitorResearch/1.0 (held-out model evaluation; non-commercial research)"
EXTS = (".jpg", ".jpeg", ".png")

NAMES = {int(k): v for k, v in
         yaml.safe_load((BASE / "configs/data.yaml").read_text())["names"].items()}

# India-first, then a generic fallback so a class can still be filled.
QUERIES = {
    "garbage_pile": ["garbage pile India street", "waste dump road India",
                     "rubbish heap street", "garbage dump roadside"],
    # Refined 2026-09-07 after a first pass: the generic terms returned a bird, a
    # framed portrait and the Bandra-Worli Sealink for "pothole", closed covers for
    # "open manhole", and festival lights for "street light". Terms below name the
    # defect itself rather than the setting.
    "pothole": ["pothole asphalt close up", "road pothole repair", "potholes damaged asphalt",
                "pothole water filled road", "chuckhole road"],
    "encroachment": ["street vendors footpath India", "roadside stall India street",
                     "street hawkers India", "pavement shops India", "footpath market India"],
    "billboard_hoarding": ["billboard India road", "hoarding advertisement India",
                           "advertising billboard street", "roadside billboard"],
    "cow": ["cow on road India", "cattle street India", "cow street town",
            "indian cow road"],
    "manhole_closed": ["manhole cover street", "manhole cover road",
                       "drain cover pavement", "sewer cover street"],
    "manhole_open": ["manhole without cover", "missing manhole cover", "open manhole shaft",
                     "uncovered drain hole street", "manhole cover removed"],
    "manhole_broken": ["cracked manhole cover", "manhole cover damaged broken",
                       "collapsed drain cover", "broken grate street", "sunken manhole road"],
    "streetlight_working": ["sodium street lamp night road", "street lighting highway night",
                            "illuminated street lamp post night", "road lit street lights night"],
    "streetlight_not_working": ["street lamp post daytime road", "lamp standard road daylight",
                                "street light column road", "unlit street lamp daytime"],
    "cat": ["stray cat street India", "cat sitting pavement", "cat on road town",
            "feral cat street", "cat walking street"],
    "horse": ["tonga horse cart India", "horse drawn cart road India", "horse walking road town",
              "pony road India", "horse rider street town"],
    "dog": ["street dog India", "stray dog road India", "dog on street",
            "stray dog street"],
    "buffalo": ["water buffalo India village", "buffalo herd road India",
                "buffalo grazing India", "bubalus bubalis India"],
    "goat": ["goats road village India", "goat herd street", "goats grazing roadside",
             "goat standing road", "goats walking street town"],
    "camel": ["camel road India", "camel Rajasthan street", "camel cart road India",
              "camel walking road"],
}


def dhash(img, s=8):
    g = img.convert("L").resize((s + 1, s), Image.LANCZOS)
    px = list(g.getdata())
    bits = 0
    for r in range(s):
        for c in range(s):
            bits = (bits << 1) | (px[r * (s + 1) + c] < px[r * (s + 1) + c + 1])
    return bits


def dataset_hashes():
    """Every hash already in the model's train/val/test - the exclusion set."""
    hashes = []
    for split in ("train", "val", "test"):
        d = RETRAIN / "images" / split
        if not d.is_dir():
            continue
        for p in d.iterdir():
            if p.suffix.lower() in EXTS:
                try:
                    with Image.open(p) as im:
                        hashes.append(dhash(im))
                except Exception:
                    pass
    return hashes


def api_get(params):
    url = f"{API}?{urllib.parse.urlencode(params)}"
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=40) as r:
        return json.loads(r.read().decode())


def search(query, limit=30):
    try:
        d = api_get({
            "action": "query", "format": "json", "generator": "search",
            "gsrsearch": query, "gsrnamespace": 6, "gsrlimit": limit,
            "prop": "imageinfo", "iiprop": "url|mime|size|extmetadata",
            "iiurlwidth": 1280,
        })
    except Exception as e:
        print(f"      search failed: {e}")
        return []
    out = []
    for p in d.get("query", {}).get("pages", {}).values():
        ii = (p.get("imageinfo") or [{}])[0]
        if not ii or ii.get("mime") not in ("image/jpeg", "image/png"):
            continue
        meta = ii.get("extmetadata", {})
        out.append({
            "title": p["title"],
            "url": ii.get("thumburl") or ii.get("url"),
            "descriptionurl": ii.get("descriptionurl"),
            "license": meta.get("LicenseShortName", {}).get("value", "unknown"),
            "artist": meta.get("Artist", {}).get("value", "")[:200],
        })
    return out


def fetch(url):
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=60) as r:
        return r.read()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--per-class", type=int, default=10)
    ap.add_argument("--classes", default=None, help="comma-separated subset")
    args = ap.parse_args()

    wanted = ([c.strip() for c in args.classes.split(",")] if args.classes
              else list(NAMES.values()))

    print("Hashing the existing dataset to build the exclusion set...")
    known = dataset_hashes()
    print(f"  {len(known)} images in train/val/test will be excluded\n")

    OUT.mkdir(parents=True, exist_ok=True)
    manifest_path = OUT / "manifest.json"
    manifest = json.loads(manifest_path.read_text()) if manifest_path.is_file() else {}
    stats = defaultdict(lambda: {"kept": 0, "dup_dataset": 0, "dup_self": 0, "failed": 0})

    for cls in wanted:
        cid = [k for k, v in NAMES.items() if v == cls]
        if not cid:
            print(f"skip unknown class {cls}")
            continue
        cid = cid[0]
        cdir = OUT / f"{cid:02d}_{cls}"
        cdir.mkdir(parents=True, exist_ok=True)
        have = [p for p in cdir.iterdir() if p.suffix.lower() in EXTS]
        kept_hashes = []
        for p in have:
            try:
                with Image.open(p) as im:
                    kept_hashes.append(dhash(im))
            except Exception:
                pass
        need = args.per_class - len(have)
        print(f"[{cid:02d}] {cls}: have {len(have)}, need {need}")
        if need <= 0:
            continue

        # Titles a human already rejected. Without this, pruning a bad image also
        # dropped its manifest entry, which made it eligible again — several
        # rejected images came straight back on the next top-up run.
        rej_path = OUT / "rejected_titles.json"
        rejected = json.loads(rej_path.read_text()) if rej_path.is_file() else {}
        seen_titles = {v.get("title") for v in manifest.get(cls, [])}
        seen_titles |= set(rejected.get(cls, []))
        entries = manifest.setdefault(cls, [])

        for q in QUERIES.get(cls, [cls.replace("_", " ")]):
            if need <= 0:
                break
            print(f"    query: {q!r}")
            for hit in search(q):
                if need <= 0:
                    break
                if hit["title"] in seen_titles or not hit["url"]:
                    continue
                seen_titles.add(hit["title"])
                try:
                    raw = fetch(hit["url"])
                    im = Image.open(BytesIO(raw)).convert("RGB")
                except Exception:
                    stats[cls]["failed"] += 1
                    continue
                if min(im.size) < 200:
                    stats[cls]["failed"] += 1
                    continue
                h = dhash(im)
                if any(bin(h ^ k).count("1") <= 6 for k in known):
                    stats[cls]["dup_dataset"] += 1
                    print(f"      SKIP (already in dataset): {hit['title'][:60]}")
                    continue
                if any(bin(h ^ k).count("1") <= 6 for k in kept_hashes):
                    stats[cls]["dup_self"] += 1
                    continue
                # Next FREE index, not count+1: after a pruning pass the numbering has
                # gaps (e.g. 02,03,05,09,10), and count+1 would silently overwrite an
                # image that is already there.
                idx = 1
                while (cdir / f"{cls}_{idx:02d}.jpg").exists():
                    idx += 1
                fname = f"{cls}_{idx:02d}.jpg"
                im.save(cdir / fname, "JPEG", quality=92)
                kept_hashes.append(h)
                entries.append({
                    "file": fname, "title": hit["title"],
                    "source": hit["descriptionurl"], "license": hit["license"],
                    "artist": hit["artist"],
                })
                stats[cls]["kept"] += 1
                need -= 1
                time.sleep(0.35)          # be polite to the API
        manifest_path.write_text(json.dumps(manifest, indent=2))

    print(f"\n{'class':26s}{'kept':>6}{'in-dataset':>12}{'self-dup':>10}{'failed':>8}")
    print("-" * 62)
    for cls in wanted:
        s = stats[cls]
        print(f"{cls:26s}{s['kept']:>6}{s['dup_dataset']:>12}{s['dup_self']:>10}{s['failed']:>8}")
    print(f"\nImages in {OUT.relative_to(BASE)}, provenance in manifest.json")


if __name__ == "__main__":
    main()
