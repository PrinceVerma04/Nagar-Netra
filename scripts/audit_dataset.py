"""
Full annotation + integrity audit of the canonical dataset.

Written 2026-09-07 after two BOOKKEEPING failures (sparse class ids, stale
train_variants) were mistaken for possible data-quality failures. Those two were
not annotation problems at all - so this script exists to answer the separate,
legitimate question: are the ANNOTATIONS themselves actually sound?

It reports, and writes a machine-readable list of every flagged image so a review
dashboard can queue exactly those for human correction.

Checks:
  A. Label parse errors        - malformed lines, non-integer/out-of-range class ids
  B. Out-of-frame boxes        - box extends past the image edge
  C. Degenerate boxes          - zero/near-zero width or height
  D. Tiny boxes                - < 0.15% of image area (often stray clicks)
  E. Full-frame boxes          - > 95% of image area (often "whole image" mislabels)
  F. Extreme aspect ratios     - > 20:1 either way
  G. Duplicate boxes           - same class, IoU > 0.9 (double-annotated)
  H. Empty / missing labels    - image with no boxes (real negative, or forgotten?)
  I. Orphan labels             - label file with no matching image
  J. Unreadable images         - corrupt / truncated / not decodable
  K. Cross-split leakage       - identical image content in two different splits
  L. Intra-split duplicates    - identical image content twice in one split
  M. classwise vs re-training  - the two canonical trees disagreeing
  N. Split coverage            - classes with too few val/test images to score

Usage:
    python scripts/audit_dataset.py
    python scripts/audit_dataset.py --json docs/annotation_audit_20260907.json
"""
import argparse
import hashlib
import json
from collections import defaultdict
from pathlib import Path

import yaml
from PIL import Image

BASE = Path(__file__).resolve().parent.parent
DATA = BASE / "data"
RETRAIN = DATA / "re-training_data"
CLASSWISE = DATA / "classwise _data"
DATA_YAML = BASE / "configs" / "data.yaml"
IMG_EXTS = (".jpg", ".jpeg", ".png")
SPLITS = ("train", "val", "test")

NAMES = {int(k): v for k, v in yaml.safe_load(DATA_YAML.read_text())["names"].items()}
NC = len(NAMES)

TINY_AREA = 0.0015      # 0.15% of the frame
FULL_AREA = 0.95
ASPECT_MAX = 20.0
IOU_DUP = 0.90


def iou(a, b):
    ax1, ay1, ax2, ay2 = a[0] - a[2] / 2, a[1] - a[3] / 2, a[0] + a[2] / 2, a[1] + a[3] / 2
    bx1, by1, bx2, by2 = b[0] - b[2] / 2, b[1] - b[3] / 2, b[0] + b[2] / 2, b[1] + b[3] / 2
    ix1, iy1 = max(ax1, bx1), max(ay1, by1)
    ix2, iy2 = min(ax2, bx2), min(ay2, by2)
    iw, ih = max(0.0, ix2 - ix1), max(0.0, iy2 - iy1)
    inter = iw * ih
    union = a[2] * a[3] + b[2] * b[3] - inter
    return inter / union if union > 0 else 0.0


def audit():
    flags = defaultdict(list)     # check -> [ {split, stem, detail} ]
    per_image = defaultdict(set)  # "split/stem" -> {check codes}
    hashes = defaultdict(list)    # content hash -> [ "split/stem" ]
    stats = {"images": 0, "boxes": 0, "empty_labels": 0}
    class_split_imgs = defaultdict(lambda: defaultdict(int))

    for split in SPLITS:
        img_dir = RETRAIN / "images" / split
        lbl_dir = RETRAIN / "labels" / split
        if not img_dir.is_dir():
            continue

        img_stems = {}
        for p in sorted(img_dir.iterdir()):
            if p.suffix.lower() not in IMG_EXTS:
                continue
            img_stems[p.stem] = p
            stats["images"] += 1
            key = f"{split}/{p.stem}"

            # --- J: readable? + content hash for K/L
            try:
                with Image.open(p) as im:
                    im.verify()
                with Image.open(p) as im:
                    im.load()
                    w_px, h_px = im.size
                hashes[hashlib.md5(p.read_bytes()).hexdigest()].append(key)
            except Exception as e:
                flags["J_unreadable_image"].append(
                    {"split": split, "stem": p.stem, "detail": f"{type(e).__name__}: {e}"})
                per_image[key].add("J")
                continue

            # --- labels
            lbl = lbl_dir / f"{p.stem}.txt"
            if not lbl.is_file() or not lbl.read_text().strip():
                stats["empty_labels"] += 1
                flags["H_empty_or_missing_label"].append(
                    {"split": split, "stem": p.stem,
                     "detail": "no label file" if not lbl.is_file() else "label file is empty"})
                per_image[key].add("H")
                continue

            boxes = []
            for ln, line in enumerate(lbl.read_text().splitlines(), 1):
                parts = line.split()
                if not parts:
                    continue
                if len(parts) < 5:
                    flags["A_parse_error"].append(
                        {"split": split, "stem": p.stem,
                         "detail": f"line {ln}: only {len(parts)} fields: {line!r}"})
                    per_image[key].add("A")
                    continue
                try:
                    cid = int(parts[0])
                    cx, cy, bw, bh = map(float, parts[1:5])
                except ValueError:
                    flags["A_parse_error"].append(
                        {"split": split, "stem": p.stem, "detail": f"line {ln}: {line!r}"})
                    per_image[key].add("A")
                    continue
                if not (0 <= cid < NC):
                    flags["A_parse_error"].append(
                        {"split": split, "stem": p.stem,
                         "detail": f"line {ln}: class id {cid} outside 0..{NC - 1}"})
                    per_image[key].add("A")
                    continue

                stats["boxes"] += 1
                boxes.append((cid, cx, cy, bw, bh))

                x1, y1, x2, y2 = cx - bw / 2, cy - bh / 2, cx + bw / 2, cy + bh / 2
                over = max(-x1, -y1, x2 - 1.0, y2 - 1.0)
                if over > 1e-6:
                    flags["B_out_of_frame"].append(
                        {"split": split, "stem": p.stem, "class": NAMES[cid],
                         "detail": f"line {ln}: extends {over:.4f} beyond the edge"})
                    per_image[key].add("B")
                if bw <= 1e-6 or bh <= 1e-6:
                    flags["C_degenerate"].append(
                        {"split": split, "stem": p.stem, "class": NAMES[cid],
                         "detail": f"line {ln}: w={bw:.6f} h={bh:.6f}"})
                    per_image[key].add("C")
                    continue

                area = bw * bh
                if area < TINY_AREA:
                    flags["D_tiny_box"].append(
                        {"split": split, "stem": p.stem, "class": NAMES[cid],
                         "detail": f"line {ln}: {area * 100:.3f}% of frame "
                                   f"(~{bw * w_px:.0f}x{bh * h_px:.0f}px)"})
                    per_image[key].add("D")
                if area > FULL_AREA:
                    flags["E_full_frame_box"].append(
                        {"split": split, "stem": p.stem, "class": NAMES[cid],
                         "detail": f"line {ln}: {area * 100:.1f}% of frame"})
                    per_image[key].add("E")
                ar = (bw * w_px) / (bh * h_px) if bh > 0 else 0
                if ar > ASPECT_MAX or (ar and 1 / ar > ASPECT_MAX):
                    flags["F_extreme_aspect"].append(
                        {"split": split, "stem": p.stem, "class": NAMES[cid],
                         "detail": f"line {ln}: aspect {ar:.1f}:1"})
                    per_image[key].add("F")

            for cid in {b[0] for b in boxes}:
                class_split_imgs[cid][split] += 1

            # --- G: duplicate boxes
            for i in range(len(boxes)):
                for j in range(i + 1, len(boxes)):
                    if boxes[i][0] == boxes[j][0] and iou(boxes[i][1:], boxes[j][1:]) > IOU_DUP:
                        flags["G_duplicate_box"].append(
                            {"split": split, "stem": p.stem, "class": NAMES[boxes[i][0]],
                             "detail": f"lines {i + 1} & {j + 1} overlap "
                                       f"IoU={iou(boxes[i][1:], boxes[j][1:]):.3f}"})
                        per_image[key].add("G")

        # --- I: orphan labels
        for lp in sorted(lbl_dir.glob("*.txt")):
            if lp.stem not in img_stems:
                flags["I_orphan_label"].append(
                    {"split": split, "stem": lp.stem, "detail": "label with no image"})

    # --- K/L: duplicate image content
    for h, keys in hashes.items():
        if len(keys) < 2:
            continue
        splits = {k.split("/")[0] for k in keys}
        if len(splits) > 1:
            flags["K_cross_split_leakage"].append(
                {"split": "-", "stem": keys[0].split("/", 1)[1],
                 "detail": f"identical image in {sorted(splits)}: {keys}"})
            for k in keys:
                per_image[k].add("K")
        else:
            flags["L_intra_split_duplicate"].append(
                {"split": keys[0].split("/")[0], "stem": keys[0].split("/", 1)[1],
                 "detail": f"{len(keys)} identical copies: {keys}"})
            for k in keys[1:]:
                per_image[k].add("L")

    # --- M: classwise vs re-training_data
    cw_boxes = defaultdict(int)
    if CLASSWISE.is_dir():
        for f in CLASSWISE.rglob("*.txt"):
            for line in f.read_text().splitlines():
                parts = line.split()
                if len(parts) >= 5:
                    try:
                        cw_boxes[int(parts[0])] += 1
                    except ValueError:
                        pass
    rt_boxes = defaultdict(int)
    for split in SPLITS:
        d = RETRAIN / "labels" / split
        if d.is_dir():
            for f in d.glob("*.txt"):
                for line in f.read_text().splitlines():
                    parts = line.split()
                    if len(parts) >= 5:
                        try:
                            rt_boxes[int(parts[0])] += 1
                        except ValueError:
                            pass
    sync = []
    for cid in sorted(NAMES):
        if cw_boxes.get(cid, 0) != rt_boxes.get(cid, 0):
            sync.append({"class": NAMES[cid], "classwise": cw_boxes.get(cid, 0),
                         "re_training": rt_boxes.get(cid, 0)})

    return flags, per_image, stats, class_split_imgs, sync


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--json", default=str(BASE / "docs" / "annotation_audit_20260907.json"))
    args = ap.parse_args()

    flags, per_image, stats, class_split_imgs, sync = audit()

    print("=" * 78)
    print("ANNOTATION + INTEGRITY AUDIT")
    print("=" * 78)
    print(f"Scanned {stats['images']} images / {stats['boxes']} boxes "
          f"in {RETRAIN.relative_to(BASE)}")

    titles = {
        "A_parse_error": "Malformed label lines / bad class ids",
        "B_out_of_frame": "Boxes extending past the image edge",
        "C_degenerate": "Zero-area boxes",
        "D_tiny_box": f"Suspiciously tiny boxes (<{TINY_AREA * 100}% of frame)",
        "E_full_frame_box": f"Boxes covering >{FULL_AREA * 100:.0f}% of the frame",
        "F_extreme_aspect": f"Extreme aspect ratios (>{ASPECT_MAX:.0f}:1)",
        "G_duplicate_box": f"Duplicate boxes (same class, IoU>{IOU_DUP})",
        "H_empty_or_missing_label": "Images with no boxes at all",
        "I_orphan_label": "Label files with no image",
        "J_unreadable_image": "Corrupt / unreadable images",
        "K_cross_split_leakage": "SAME IMAGE IN TWO SPLITS (train/val/test leakage)",
        "L_intra_split_duplicate": "Duplicate images within one split",
    }

    print(f"\n{'code':28s} {'count':>7}  issue")
    print("-" * 78)
    total = 0
    for code, title in titles.items():
        n = len(flags.get(code, []))
        total += n
        mark = "  <-- " if n and code in ("A_parse_error", "C_degenerate",
                                          "J_unreadable_image", "K_cross_split_leakage") else ""
        print(f"{code:28s} {n:>7}  {title}{mark}")
    print("-" * 78)
    print(f"{'TOTAL findings':28s} {total:>7}")
    print(f"{'images flagged (unique)':28s} {len(per_image):>7}  "
          f"({len(per_image) / max(stats['images'], 1) * 100:.1f}% of the dataset)")

    for code in titles:
        items = flags.get(code, [])
        if not items:
            continue
        print(f"\n--- {code}: {titles[code]} ({len(items)}) ---")
        by_class = defaultdict(int)
        for it in items:
            by_class[it.get("class", "-")] += 1
        for c, n in sorted(by_class.items(), key=lambda kv: -kv[1]):
            print(f"    {c:26s} {n:>5}")
        for it in items[:4]:
            print(f"      e.g. {it['split']}/{it['stem']}: {it['detail'][:110]}")
        if len(items) > 4:
            print(f"      ... and {len(items) - 4} more")

    print(f"\n--- M: classwise _data vs re-training_data box counts ---")
    if sync:
        for s in sync:
            print(f"    MISMATCH {s['class']:24s} classwise={s['classwise']} "
                  f"re_training={s['re_training']}")
    else:
        print("    in sync for all 16 classes")

    print(f"\n--- N: per-class split coverage ---")
    print(f"    {'class':26s} {'train':>7} {'val':>6} {'test':>6}   note")
    for cid in sorted(NAMES):
        c = class_split_imgs[cid]
        note = ""
        if c.get("test", 0) == 0:
            note = "CANNOT BE SCORED - no test images"
        elif c.get("test", 0) < 5 or c.get("val", 0) < 5:
            note = "too few val/test to be meaningful"
        print(f"    {NAMES[cid]:26s} {c.get('train', 0):>7} {c.get('val', 0):>6} "
              f"{c.get('test', 0):>6}   {note}")

    out = {
        "generated": "2026-09-07",
        "stats": stats,
        "findings": {k: v for k, v in flags.items()},
        "flagged_images": {k: sorted(v) for k, v in sorted(per_image.items())},
        "classwise_vs_retraining": sync,
    }
    Path(args.json).write_text(json.dumps(out, indent=2))
    print(f"\nWrote {args.json}")
    print(f"  {len(per_image)} unique images flagged for human review.")


if __name__ == "__main__":
    main()
