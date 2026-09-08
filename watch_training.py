"""
Live view of training progress, reading runs/detect/runs/civic_services*/results.csv
(the same file Ultralytics appends to after every epoch) instead of the raw log's
carriage-return progress bars.

Usage:
    python watch_training.py
"""
import csv
import glob
import os
import time

REFRESH_SECONDS = 5


def find_latest_run():
    candidates = sorted(glob.glob("runs/detect/runs/civic_services*"), key=os.path.getmtime)
    return candidates[-1] if candidates else None


def main():
    run_dir = find_latest_run()
    if not run_dir:
        raise SystemExit("No training run found under runs/detect/runs/")
    results_path = os.path.join(run_dir, "results.csv")
    print(f"Watching {results_path} (Ctrl+C to stop)\n")

    last_row_count = 0
    while True:
        if os.path.isfile(results_path):
            with open(results_path) as f:
                rows = list(csv.DictReader(f))
            if len(rows) > last_row_count:
                for row in rows[last_row_count:]:
                    epoch = row.get("epoch", "?")
                    map50 = row.get("metrics/mAP50(B)", "?")
                    map5095 = row.get("metrics/mAP50-95(B)", "?")
                    box_loss = row.get("train/box_loss", "?")
                    print(f"epoch {epoch:>4}  mAP50={float(map50):.3f}  mAP50-95={float(map5095):.3f}  box_loss={float(box_loss):.3f}")
                last_row_count = len(rows)

        weights_path = os.path.join(run_dir, "weights", "best.pt")
        if os.path.isfile(weights_path):
            mtime = time.strftime("%H:%M:%S", time.localtime(os.path.getmtime(weights_path)))
            print(f"  (best.pt last updated {mtime})", end="\r")

        time.sleep(REFRESH_SECONDS)


if __name__ == "__main__":
    main()
