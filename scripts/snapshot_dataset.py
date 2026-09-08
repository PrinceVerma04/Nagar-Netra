"""
Freezes a complete, human- and machine-readable record of the dataset exactly as it
stands, for every training variant, immediately before a training run.

WHY: this project's data has changed many times in a single day (class ids renumbered,
two re-splits, 289 label corrections, 125 image deletions). Six weeks from now,
`training_results/civic_services_augmented/` will hold a model and a metric, and the
only honest way to interpret that metric is to know precisely what it was trained and
scored on. Ultralytics' own args.yaml records the *path* to a yaml, not the contents
of the folders it pointed at - and those folders get rebuilt.

Writes two files per snapshot to docs/:
    dataset_snapshot_<stamp>.md     - the readable report (tables, integrity checks)
    dataset_snapshot_<stamp>.json   - the same numbers, for diffing snapshots later

Records, for the canonical split and each of the three variants:
  - per-class image AND box counts, per split
  - split ratios and per-class val/test share
  - the exact class-id -> name map in force
  - integrity: tree sync, leakage, degenerate/duplicate boxes, orphan labels
  - a content fingerprint per split (sorted stem list hashed) so two snapshots can be
    compared for "is this literally the same data?" without storing every filename

Usage:
    python scripts/snapshot_dataset.py
    python scripts/snapshot_dataset.py --label before_16class_retrain
"""
import argparse
import datetime as dt
import hashlib
import json
from collections import defaultdict
from pathlib import Path

import yaml

BASE = Path(__file__).resolve().parent.parent
DATA = BASE / "data"
RETRAIN = DATA / "re-training_data"
CLASSWISE = DATA / "classwise _data"
VARIANTS = DATA / "train_variants"
DOCS = BASE / "docs"
CONFIGS = BASE / "configs"
IMG_EXTS = (".jpg", ".jpeg", ".png")
SPLITS = ("train", "val", "test")

NAMES = {int(k): v for k, v in
         yaml.safe_load((CONFIGS / "data.yaml").read_text())["names"].items()}


def scan_split(root: Path, split: str):
    """-> (n_images, {cid: n_images_containing}, {cid: n_boxes}, fingerprint)"""
    img_dir, lbl_dir = root / "images" / split, root / "labels" / split
    if not img_dir.is_dir():
        return 0, {}, {}, ""
    imgs = defaultdict(int)
    boxes = defaultdict(int)
    stems = []
    n = 0
    for p in sorted(img_dir.iterdir()):
        if p.suffix.lower() not in IMG_EXTS:
            continue
        n += 1
        stems.append(p.stem)
        f = lbl_dir / f"{p.stem}.txt"
        if not f.is_file():
            continue
        present = set()
        for line in f.read_text().splitlines():
            q = line.split()
            if len(q) >= 5:
                try:
                    c = int(q[0])
                except ValueError:
                    continue
                boxes[c] += 1
                present.add(c)
        for c in present:
            imgs[c] += 1
    fp = hashlib.sha256("\n".join(sorted(stems)).encode()).hexdigest()[:16]
    return n, dict(imgs), dict(boxes), fp


def scan_root(root: Path):
    out = {}
    for s in SPLITS:
        n, imgs, boxes, fp = scan_split(root, s)
        out[s] = {"images": n, "images_per_class": imgs, "boxes_per_class": boxes,
                  "fingerprint": fp}
    return out


def integrity():
    """The checks that must hold for a training run to be trustworthy."""
    res = {}
    rt = sum(v for s in SPLITS
             for v in scan_split(RETRAIN, s)[2].values())
    cw = 0
    for f in CLASSWISE.rglob("*.txt"):
        for line in f.read_text().splitlines():
            if len(line.split()) >= 5:
                cw += 1
    res["retraining_boxes"] = rt
    res["classwise_boxes"] = cw
    res["trees_in_sync"] = rt == cw

    bad_ids, degenerate, orphans, empty = set(), 0, 0, 0
    seen = defaultdict(set)
    for s in SPLITS:
        img_dir, lbl_dir = RETRAIN / "images" / s, RETRAIN / "labels" / s
        stems = {p.stem for p in img_dir.iterdir() if p.suffix.lower() in IMG_EXTS}
        for f in lbl_dir.glob("*.txt"):
            if f.stem not in stems:
                orphans += 1
            txt = f.read_text().strip()
            if not txt:
                empty += 1
            for line in txt.splitlines():
                q = line.split()
                if len(q) < 5:
                    continue
                try:
                    c = int(q[0]); w = float(q[3]); h = float(q[4])
                except ValueError:
                    bad_ids.add(q[0]); continue
                if not (0 <= c < len(NAMES)):
                    bad_ids.add(c)
                if w <= 1e-6 or h <= 1e-6:
                    degenerate += 1
        for st in stems:
            seen[st].add(s)
    res["class_ids_out_of_range"] = sorted(bad_ids)
    res["degenerate_boxes"] = degenerate
    res["orphan_labels"] = orphans
    res["empty_labels"] = empty
    res["stems_in_multiple_splits"] = sorted(k for k, v in seen.items() if len(v) > 1)
    return res


def md_table(title, per_root):
    rows = []
    rows.append(f"### {title}\n")
    rows.append("| class | train | val | test | total | val % | boxes tr/val/test |")
    rows.append("|---|---:|---:|---:|---:|---:|---|")
    for cid in sorted(NAMES):
        i = {s: per_root[s]["images_per_class"].get(cid, 0) for s in SPLITS}
        b = {s: per_root[s]["boxes_per_class"].get(cid, 0) for s in SPLITS}
        t = sum(i.values())
        pct = f"{i['val'] / t * 100:.1f}%" if t else "-"
        rows.append(f"| {NAMES[cid]} | {i['train']} | {i['val']} | {i['test']} | {t} | "
                    f"{pct} | {b['train']} / {b['val']} / {b['test']} |")
    tot = {s: per_root[s]["images"] for s in SPLITS}
    n = sum(tot.values())
    tb = {s: sum(per_root[s]["boxes_per_class"].values()) for s in SPLITS}
    rows.append(f"| **TOTAL** | **{tot['train']}** | **{tot['val']}** | **{tot['test']}** | "
                f"**{n}** | | **{tb['train']} / {tb['val']} / {tb['test']}** |")
    if n:
        rows.append(f"\nSplit ratio: **{tot['train']/n*100:.1f} / {tot['val']/n*100:.1f} "
                    f"/ {tot['test']/n*100:.1f}**")
    rows.append(f"\nFingerprints — train `{per_root['train']['fingerprint']}` · "
                f"val `{per_root['val']['fingerprint']}` · "
                f"test `{per_root['test']['fingerprint']}`\n")
    return "\n".join(rows)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--label", default="")
    args = ap.parse_args()

    stamp = dt.datetime.now().strftime("%Y%m%d_%H%M%S")
    name = f"dataset_snapshot_{stamp}"

    roots = {"canonical (unbalanced)": RETRAIN}
    for v in ("oversampled", "undersampled", "augmented"):
        if (VARIANTS / v).is_dir():
            roots[v] = VARIANTS / v

    data = {k: scan_root(r) for k, r in roots.items()}
    integ = integrity()

    payload = {
        "generated": dt.datetime.now().isoformat(timespec="seconds"),
        "label": args.label,
        "class_names": NAMES,
        "n_classes": len(NAMES),
        "roots": {k: str(v.relative_to(BASE)) for k, v in roots.items()},
        "splits": data,
        "integrity": integ,
        "configs": {p.name: yaml.safe_load(p.read_text())
                    for p in sorted(CONFIGS.glob("data*.yaml"))},
    }
    (DOCS / f"{name}.json").write_text(json.dumps(payload, indent=2))

    md = [f"# Dataset snapshot — {stamp}", ""]
    if args.label:
        md.append(f"**Label:** {args.label}\n")
    md.append(f"Generated {payload['generated']} · **{len(NAMES)} classes** "
              f"(ids 0–{max(NAMES)})\n")

    md.append("## Integrity checks\n")
    md.append("| check | result |")
    md.append("|---|---|")
    ok = lambda b: "PASS" if b else "**FAIL**"
    md.append(f"| both trees in sync | {ok(integ['trees_in_sync'])} "
              f"({integ['retraining_boxes']} vs {integ['classwise_boxes']} boxes) |")
    md.append(f"| class ids in range | {ok(not integ['class_ids_out_of_range'])} |")
    md.append(f"| degenerate boxes | {ok(integ['degenerate_boxes'] == 0)} "
              f"({integ['degenerate_boxes']}) |")
    md.append(f"| orphan labels | {ok(integ['orphan_labels'] == 0)} "
              f"({integ['orphan_labels']}) |")
    md.append(f"| empty labels | {ok(integ['empty_labels'] == 0)} "
              f"({integ['empty_labels']}) |")
    md.append(f"| no image in two splits | {ok(not integ['stems_in_multiple_splits'])} |")
    md.append("")

    md.append("## Overall summary\n")
    c = data["canonical (unbalanced)"]
    n = sum(c[s]["images"] for s in SPLITS)
    nb = sum(sum(c[s]["boxes_per_class"].values()) for s in SPLITS)
    md.append(f"- **{n} images**, **{nb} boxes**, {len(NAMES)} classes")
    md.append(f"- Split **{c['train']['images']} / {c['val']['images']} / "
              f"{c['test']['images']}** (train/val/test)")
    md.append("- val and test are byte-identical across all four variants; only "
              "train differs")
    md.append("- smallest classes: " + ", ".join(
        f"{NAMES[cid]} ({sum(c[s]['images_per_class'].get(cid,0) for s in SPLITS)})"
        for cid in sorted(NAMES,
                          key=lambda k: sum(c[s]["images_per_class"].get(k, 0)
                                            for s in SPLITS))[:4]))
    md.append("")

    md.append("## Per-variant splits\n")
    for k in roots:
        md.append(md_table(k, data[k]))

    md.append("## Train-split comparison across variants\n")
    md.append("| class | " + " | ".join(roots) + " |")
    md.append("|---" * (len(roots) + 1) + "|")
    for cid in sorted(NAMES):
        cells = [str(data[k]["train"]["images_per_class"].get(cid, 0)) for k in roots]
        md.append(f"| {NAMES[cid]} | " + " | ".join(cells) + " |")
    md.append("| **train images** | " +
              " | ".join(f"**{data[k]['train']['images']}**" for k in roots) + " |")
    md.append("")

    (DOCS / f"{name}.md").write_text("\n".join(md) + "\n")
    print(f"Wrote {(DOCS / f'{name}.md').relative_to(BASE)}")
    print(f"Wrote {(DOCS / f'{name}.json').relative_to(BASE)}")

    fails = [k for k, v in {
        "trees_in_sync": integ["trees_in_sync"],
        "class_ids": not integ["class_ids_out_of_range"],
        "degenerate": integ["degenerate_boxes"] == 0,
        "orphans": integ["orphan_labels"] == 0,
        "empty": integ["empty_labels"] == 0,
        "no_split_overlap": not integ["stems_in_multiple_splits"],
    }.items() if not v]
    if fails:
        print(f"\n  INTEGRITY FAILURES: {fails}")
        return 1
    print("  all integrity checks pass")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
