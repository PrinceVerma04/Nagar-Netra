"""
Balances data/re-training_data's TRAIN split (val/test are left untouched — real,
non-duplicated held-out data) by duplicating existing images+labels per class,
round-robin, up to the largest class's current train count.

Every class in data/classwise _data/<class>/train/ is read to find the current
per-class train count. Duplicates are written to BOTH data/classwise _data/<class>/
train/ (so the per-class view stays accurate) and data/re-training_data/images/
train + labels/train (the flat tree train.py actually reads), so the two stay in
sync with each other.

Safe to re-run any time after promoting more reviewed images from the annotation
dashboard (review_annotate_dashboard.py) into re-training_data/classwise_data —
it only ever tops classes up to whatever the current largest class is; it will not
re-duplicate a class that's already at or above target.

Usage:
    source .venv/bin/activate
    python balance_train_data.py
"""
import shutil
from pathlib import Path
import yaml

BASE = Path(__file__).resolve().parent
DATA = BASE / "data"
RETRAIN = DATA / "re-training_data"
CLASSWISE = DATA / "classwise _data"

names = yaml.safe_load((BASE / "configs" / "data.yaml").read_text())["names"]
IMG_EXTS = (".jpg", ".jpeg", ".png")

rt_img_dir = RETRAIN / "images" / "train"
rt_lbl_dir = RETRAIN / "labels" / "train"
rt_img_dir.mkdir(parents=True, exist_ok=True)
rt_lbl_dir.mkdir(parents=True, exist_ok=True)


def main():
    classes = list(names.values())
    per_class_imgs = {}
    for cls in classes:
        img_dir = CLASSWISE / cls / "train" / "images"
        imgs = sorted(p for p in img_dir.iterdir() if p.suffix.lower() in IMG_EXTS) if img_dir.is_dir() else []
        per_class_imgs[cls] = imgs

    target = max(len(v) for v in per_class_imgs.values())
    print(f"Target train count per class: {target}")

    added_total = 0
    for cls in classes:
        imgs = per_class_imgs[cls]
        current = len(imgs)
        need = target - current
        print(f"{cls}: current={current} need={need}")
        if need <= 0 or not imgs:
            continue

        cw_img_dir = CLASSWISE / cls / "train" / "images"
        cw_lbl_dir = CLASSWISE / cls / "train" / "labels"

        i = 0
        dup_n = 1
        added = 0
        while added < need:
            src_img = imgs[i % len(imgs)]
            src_lbl = cw_lbl_dir / f"{src_img.stem}.txt"
            i += 1
            if not src_lbl.is_file():
                continue

            new_stem = f"{src_img.stem}_bal{dup_n}"
            dup_n += 1
            dest_cw_img = cw_img_dir / f"{new_stem}{src_img.suffix}"
            while dest_cw_img.exists():
                new_stem = f"{src_img.stem}_bal{dup_n}"
                dup_n += 1
                dest_cw_img = cw_img_dir / f"{new_stem}{src_img.suffix}"
            dest_cw_lbl = cw_lbl_dir / f"{new_stem}.txt"

            shutil.copy(src_img, dest_cw_img)
            shutil.copy(src_lbl, dest_cw_lbl)

            dest_rt_img = rt_img_dir / f"{new_stem}{src_img.suffix}"
            dest_rt_lbl = rt_lbl_dir / f"{new_stem}.txt"
            shutil.copy(src_img, dest_rt_img)
            shutil.copy(src_lbl, dest_rt_lbl)

            added += 1
            added_total += 1

    print(f"\nTotal duplicate images added to train: {added_total}")


if __name__ == "__main__":
    main()
