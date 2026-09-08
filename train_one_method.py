"""
Trains YOLO11n for exactly ONE data-balancing method and evaluates it on the held-
out test split. Called by train_compare.py as a subprocess (never run this
directly unless debugging a single method) - keeping training in its own process
means its DataLoader workers are children of THIS process, not of a log-teeing
wrapper, so there's no fd-inheritance/pipe-never-closes hazard.

Writes into training_results/civic_services_<method>/:
    weights/best.pt, weights/last.pt, results.csv, results.png, confusion_matrix.png, ...
    run_meta.json      - method, hyperparameters, per-split image counts used
    test_metrics.json  - final evaluation on the held-out test split
"""
import argparse
import json
from pathlib import Path

from ultralytics import YOLO

BASE = Path(__file__).resolve().parent
RESULTS = BASE / "training_results"

DATA_YAML = {
    "unbalanced": BASE / "configs" / "data.yaml",
    "oversampled": BASE / "configs" / "data_oversampled.yaml",
    "undersampled": BASE / "configs" / "data_undersampled.yaml",
    "augmented": BASE / "configs" / "data_augmented.yaml",
}
IMG_EXTS = (".jpg", ".jpeg", ".png")


def count_images(d: Path) -> int:
    return sum(1 for p in d.iterdir() if p.suffix.lower() in IMG_EXTS) if d.is_dir() else 0


def split_counts(data_yaml_path: Path):
    import yaml
    cfg = yaml.safe_load(data_yaml_path.read_text())
    root = Path(cfg["path"])
    return {split: count_images(root / cfg[split]) for split in ("train", "val", "test")}


def per_class_counts(data_yaml_path: Path):
    """Per-class image and box counts for the exact folders this run trains on.

    Stored next to the weights because the folders themselves are rebuilt whenever
    the split or the variants are regenerated - a path in args.yaml does not tell
    you later what the model actually saw.
    """
    import yaml
    from collections import defaultdict
    cfg = yaml.safe_load(data_yaml_path.read_text())
    root = Path(cfg["path"])
    names = {int(k): v for k, v in cfg["names"].items()}
    out = {}
    for split in ("train", "val", "test"):
        img_dir = root / cfg[split]
        lbl_dir = root / "labels" / split
        imgs, boxes = defaultdict(int), defaultdict(int)
        if img_dir.is_dir():
            for p in img_dir.iterdir():
                if p.suffix.lower() not in IMG_EXTS:
                    continue
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
        out[split] = {names[c]: {"images": imgs.get(c, 0), "boxes": boxes.get(c, 0)}
                      for c in sorted(names)}
    return out


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--method", required=True, choices=list(DATA_YAML))
    parser.add_argument("--epochs", type=int, default=100)
    parser.add_argument("--imgsz", type=int, default=640)
    parser.add_argument("--batch", type=int, default=16)
    parser.add_argument("--robust", action="store_true",
                        help="geometry/viewpoint augmentation preset - see below")
    parser.add_argument("--suffix", default="",
                        help="append to the result dir name, so a variant run does not "
                             "overwrite the baseline it is being compared against")
    args = parser.parse_args()

    # The 2026-09-07 runs left multi_scale, shear and perspective at 0 and degrees at
    # 5. That turned out to matter: the training images are almost all 640x640 squares
    # (Roboflow exports), and on real 4:3 photos the model lost ~9 points purely to
    # that geometry mismatch - letterboxing inputs to square at inference recovered
    # 34% -> 43% on unseen images with no retraining. These settings try to teach the
    # invariance instead of patching it at inference. degrees=15 also targets the
    # measured tilt curve, where 15 degrees of camera tilt already costs 15% mAP.
    AUG = dict(degrees=5.0, scale=0.5, shear=0.0, perspective=0.0, multi_scale=False)
    if args.robust:
        AUG = dict(degrees=15.0, scale=0.6, shear=3.0, perspective=0.0005,
                   multi_scale=True)

    data_yaml = DATA_YAML[args.method]
    result_dir = RESULTS / f"civic_services_{args.method}{args.suffix}"

    counts = split_counts(data_yaml)
    (result_dir).mkdir(parents=True, exist_ok=True)
    (result_dir / "run_meta.json").write_text(json.dumps({
        "method": args.method, "data_yaml": str(data_yaml),
        "robust_augmentation": args.robust, "augmentation": AUG, "suffix": args.suffix,
        "started": __import__("datetime").datetime.now().isoformat(timespec="seconds"),
        "epochs": args.epochs, "imgsz": args.imgsz, "batch": args.batch,
        "model": "yolo11n.pt",
        "image_counts": counts,
        "per_class_counts": per_class_counts(data_yaml),
        "data_yaml_contents": __import__("yaml").safe_load(data_yaml.read_text()),
    }, indent=2))

    print(f"\n{'='*80}\nSTARTING '{args.method}'  data={data_yaml}  images(train/val/test)="
          f"{counts['train']}/{counts['val']}/{counts['test']}\n{'='*80}\n", flush=True)

    model = YOLO("yolo11n.pt")
    model.train(
        data=str(data_yaml),
        epochs=args.epochs,
        imgsz=args.imgsz,
        batch=args.batch,
        project=str(RESULTS),
        name=f"civic_services_{args.method}{args.suffix}",
        exist_ok=True,
        patience=20,
        mosaic=1.0,
        fliplr=0.5,
        copy_paste=0.1,
        cos_lr=True,
        **AUG,
    )
    test_metrics = model.val(data=str(data_yaml), split="test")

    # box.p / box.r / box.ap50 are indexed by ap_class_index (ONLY the classes that
    # actually have labels in this split), not by class id. Zipping them against
    # names.values() positionally - as this file used to - silently shifts every
    # per-class number as soon as one class is absent. That is not hypothetical
    # here: streetlight_working currently has 0 test images, so the arrays are
    # short and every class after it would have been mislabelled. Key the output
    # by class name instead, and record which ids were actually evaluated.
    idx = test_metrics.box.ap_class_index.tolist()
    names = test_metrics.names
    per_class = {
        names[c]: {
            "class_id": int(c),
            "precision": float(test_metrics.box.p[i]),
            "recall": float(test_metrics.box.r[i]),
            "map50": float(test_metrics.box.ap50[i]),
            "map50-95": float(test_metrics.box.ap[i]),
        }
        for i, c in enumerate(idx)
    }
    not_evaluated = [names[c] for c in names if c not in idx]

    metrics_out = {
        "map50-95": float(test_metrics.box.map),
        "map50": float(test_metrics.box.map50),
        "map75": float(test_metrics.box.map75),
        "per_class": per_class,
        "classes_absent_from_test_split": not_evaluated,
        "class_names": names,
    }
    if not_evaluated:
        print(f"\nNOTE: no test-split labels for {not_evaluated} - "
              f"these classes are unscored, not scored zero.", flush=True)
    (result_dir / "test_metrics.json").write_text(json.dumps(metrics_out, indent=2))
    print(f"\nDone: {args.method}. Results in {result_dir}", flush=True)


if __name__ == "__main__":
    main()
