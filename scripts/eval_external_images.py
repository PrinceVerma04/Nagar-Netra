"""
Runs the trained detector over data/external_test_images and reports what it predicts.

These images have NO ground-truth boxes, so this is deliberately not an mAP run. The
question it answers is narrower and more useful for a sanity check: given an image
that definitely contains class X and that the model has definitely never seen, does
it fire, and does it name X?

Two numbers per class:
  hit@any  - the correct class appears somewhere in the detections
  hit@top  - the correct class is the single highest-confidence detection

hit@any is the fairer one for these images: a street scene holding a goat also holds
a road, a wall and often a dog, so the top box legitimately might not be the goat.

Confusions are printed because they are the interesting failure mode - e.g. cow
predicted on a buffalo image tells you something a bare accuracy number does not.

Usage:
    python scripts/eval_external_images.py
    python scripts/eval_external_images.py --conf 0.25 --annotate
"""
import argparse
import json
from collections import Counter, defaultdict
from pathlib import Path

BASE = Path(__file__).resolve().parent.parent
# The collection folder has been moved once already; look in both known spots rather
# than hard-failing on a stale path.
CANDIDATES = [BASE / "data for test/external_test_images",
              BASE / "data/external_test_images"]
IMAGES = next((p for p in CANDIDATES if p.is_dir()), CANDIDATES[0])
WEIGHTS = BASE / "training_results/civic_services_oversampled/weights/best.pt"
OUT = BASE / "docs/external_eval"
EXTS = (".jpg", ".jpeg", ".png")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--conf", type=float, default=0.25)
    ap.add_argument("--weights", default=str(WEIGHTS))
    ap.add_argument("--annotate", action="store_true", default=True)
    ap.add_argument("--images", default=str(IMAGES))
    args = ap.parse_args()

    images_dir = Path(args.images)
    if not images_dir.is_dir():
        raise SystemExit(f"image folder not found: {images_dir}")

    from ultralytics import YOLO
    model = YOLO(args.weights)
    names = model.names

    folders = sorted([d for d in images_dir.iterdir() if d.is_dir()])
    if args.annotate:
        OUT.mkdir(parents=True, exist_ok=True)

    per_class = {}
    all_rows = []
    confusion = defaultdict(Counter)

    for d in folders:
        true_cls = d.name.split("_", 1)[1]
        files = sorted([p for p in d.iterdir() if p.suffix.lower() in EXTS])
        if not files:
            continue
        hit_any = hit_top = no_det = 0
        confs = []
        for p in files:
            r = model.predict(str(p), conf=args.conf, verbose=False)[0]
            labels = [names[int(c)] for c in r.boxes.cls.tolist()]
            scores = r.boxes.conf.tolist()
            if not labels:
                no_det += 1
                confusion[true_cls]["<no detection>"] += 1
                all_rows.append({"true": true_cls, "file": p.name, "preds": [],
                                 "top": None, "top_conf": None})
                # Save these too. Skipping them hid the most important failures:
                # billboard_hoarding produced 9 misses and therefore zero output
                # images, which looked like the class had not been evaluated at all.
                if args.annotate:
                    r.save(filename=str(OUT / f"{d.name}__{p.stem}__NODET.jpg"))
                continue
            order = sorted(range(len(labels)), key=lambda i: -scores[i])
            top = labels[order[0]]
            if true_cls in labels:
                hit_any += 1
                confs.append(max(s for l, s in zip(labels, scores) if l == true_cls))
            if top == true_cls:
                hit_top += 1
            else:
                confusion[true_cls][top] += 1
            all_rows.append({"true": true_cls, "file": p.name,
                             "preds": sorted(set(labels)), "top": top,
                             "top_conf": round(scores[order[0]], 3)})
            if args.annotate:
                r.save(filename=str(OUT / f"{d.name}__{p.stem}.jpg"))
        n = len(files)
        per_class[true_cls] = {
            "n": n, "hit_any": hit_any, "hit_top": hit_top, "no_detection": no_det,
            "mean_conf_when_hit": round(sum(confs) / len(confs), 3) if confs else None,
        }

    print(f"\nModel: {Path(args.weights).parent.parent.name}   conf>={args.conf}")
    print("=" * 76)
    print(f"{'class':26s}{'n':>4}{'hit@any':>9}{'hit@top':>9}{'no det':>8}{'conf':>8}")
    print("-" * 76)
    tn = ta = tt = td = 0
    for cls, s in per_class.items():
        pct = f"{s['hit_any']}/{s['n']}"
        top = f"{s['hit_top']}/{s['n']}"
        c = f"{s['mean_conf_when_hit']:.2f}" if s["mean_conf_when_hit"] else "  -"
        print(f"{cls:26s}{s['n']:>4}{pct:>9}{top:>9}{s['no_detection']:>8}{c:>8}")
        tn += s["n"]; ta += s["hit_any"]; tt += s["hit_top"]; td += s["no_detection"]
    print("-" * 76)
    print(f"{'TOTAL':26s}{tn:>4}{f'{ta}/{tn}':>9}{f'{tt}/{tn}':>9}{td:>8}")
    print(f"{'':26s}{'':4}{ta/tn*100:>8.0f}%{tt/tn*100:>8.0f}%")
    print("=" * 76)

    print("\nWhat it said instead (top prediction when it was not the true class):")
    for cls in per_class:
        wrong = confusion.get(cls)
        if not wrong:
            continue
        items = ", ".join(f"{k}×{v}" for k, v in wrong.most_common(4))
        print(f"  {cls:26s} {items}")

    (OUT / "results.json").write_text(json.dumps(
        {"per_class": per_class, "rows": all_rows,
         "confusion": {k: dict(v) for k, v in confusion.items()},
         "conf_threshold": args.conf, "weights": str(args.weights)}, indent=2))
    print(f"\nAnnotated images + results.json in {OUT.relative_to(BASE)}")


if __name__ == "__main__":
    main()
