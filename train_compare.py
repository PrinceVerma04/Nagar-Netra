"""
Orchestrates the four data-balancing retraining experiments (unbalanced,
oversampled, undersampled, augmented) for later comparison. Each method's actual
training runs in its own subprocess (train_one_method.py) with stdout+stderr
redirected straight to a log file - deliberately NOT an in-process os.dup2/tee
trick, which deadlocks here: Ultralytics' DataLoader workers (num_workers=8)
inherit a dup2'd pipe fd and keep it open after the main process closes its copy,
so `tee` never sees EOF and hangs forever waiting for it. Redirecting a real
subprocess's stdout to an open file has no such hazard - the OS closes the file
once every process (main + its forked DataLoader workers) has actually exited.

Each run overwrites any prior training_results/civic_services_<method>/ (handled
inside train_one_method.py via YOLO's exist_ok=True + our own dir creation), and
writes train_console.log alongside the usual Ultralytics artifacts, run_meta.json,
and test_metrics.json.

Prerequisite: run data/build_train_variants.py first to build the oversampled/
undersampled/augmented dataset copies ("unbalanced" needs no prep).

Usage:
    python train_compare.py --method unbalanced
    python train_compare.py --method oversampled
    python train_compare.py --method undersampled
    python train_compare.py --method augmented
    python train_compare.py --method all            # all four, back to back
    python train_compare.py --method remaining      # oversampled, undersampled, augmented
                                                     # in sequence - skips unbalanced (already done)
    python train_compare.py --method all --epochs 50 --batch 16

Each method trains fully (all epochs + final test-set eval) before the next one
starts - they are never run concurrently, so there's only ever one training job
using the GPU at a time. If a method fails, the sequence stops immediately instead
of silently continuing to the next one.
"""
import argparse
import datetime as dt
import shutil
import subprocess
import sys
import time
from pathlib import Path

BASE = Path(__file__).resolve().parent
RESULTS = BASE / "training_results"
METHODS = ["unbalanced", "oversampled", "undersampled", "augmented"]
DATA_YAML_EXISTS = {
    "unbalanced": BASE / "configs" / "data.yaml",
    "oversampled": BASE / "configs" / "data_oversampled.yaml",
    "undersampled": BASE / "configs" / "data_undersampled.yaml",
    "augmented": BASE / "configs" / "data_augmented.yaml",
}


def run_one(method: str, epochs: int, imgsz: int, batch: int):
    data_yaml = DATA_YAML_EXISTS[method]
    if not data_yaml.is_file():
        raise SystemExit(f"{data_yaml} not found - run data/build_train_variants.py first "
                          f"(not needed for 'unbalanced')")

    result_dir = RESULTS / f"civic_services_{method}"
    if result_dir.exists():
        shutil.rmtree(result_dir)  # explicit overwrite of any prior run with this name
    result_dir.mkdir(parents=True)

    log_path = result_dir / "train_console.log"
    started = dt.datetime.now()
    print(f"\n>>> {method}: started {started:%H:%M:%S}, log -> {log_path}\n", flush=True)

    # The subprocess writes STRAIGHT to the log file (never to a pipe we read).
    # That is deliberate: Ultralytics' DataLoader workers inherit the child's stdout
    # fd, so a pipe read in this parent can block forever waiting for an EOF that
    # never comes once the main child exits but a worker still holds the write end.
    # To still give live console output, we tail the file from this process instead -
    # same effect, none of the fd-lifetime hazard. `-u` keeps the child unbuffered so
    # each line hits the file the instant it is produced.
    with open(log_path, "w") as logf:
        proc = subprocess.Popen(
            [sys.executable, "-u", str(BASE / "train_one_method.py"),
             "--method", method, "--epochs", str(epochs), "--imgsz", str(imgsz),
             "--batch", str(batch)],
            stdout=logf, stderr=subprocess.STDOUT,
        )
        with open(log_path, "r") as tail:
            while True:
                line = tail.readline()
                if line:
                    sys.stdout.write(line)
                    sys.stdout.flush()
                elif proc.poll() is not None:
                    sys.stdout.write(tail.read())    # drain whatever landed last
                    sys.stdout.flush()
                    break
                else:
                    time.sleep(0.2)

    took = dt.datetime.now() - started
    mins = took.total_seconds() / 60
    if proc.returncode != 0:
        print(f"\n>>> {method} FAILED (exit {proc.returncode}) after {mins:.1f} min "
              f"- see {log_path}", flush=True)
    else:
        print(f"\n>>> {method} done in {mins:.1f} min.", flush=True)
    return proc.returncode


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--method", choices=METHODS + ["all", "remaining"], default="all")
    parser.add_argument("--epochs", type=int, default=100)
    parser.add_argument("--imgsz", type=int, default=640)
    parser.add_argument("--batch", type=int, default=16)
    parser.add_argument("--skip-snapshot", action="store_true",
                        help="don't freeze a dataset snapshot first (not recommended)")
    args = parser.parse_args()

    # Freeze what we are about to train on, BEFORE training, and refuse to start if
    # the dataset fails an integrity check. Variants get rebuilt and splits get
    # redone; without this the only record of what a model saw is a path that now
    # points at different files.
    if not args.skip_snapshot:
        print("Freezing dataset snapshot before training...", flush=True)
        rc = subprocess.run(
            [sys.executable, str(BASE / "scripts" / "snapshot_dataset.py"),
             "--label", f"before_{args.method}_retrain"]).returncode
        if rc != 0:
            raise SystemExit("Dataset failed integrity checks - fix before training. "
                             "Override with --skip-snapshot if you really mean to.")

    if args.method == "all":
        methods = METHODS
    elif args.method == "remaining":
        methods = [m for m in METHODS if m != "unbalanced"]
    else:
        methods = [args.method]

    print(f"Sequence to run, one at a time: {methods}\n")
    for i, m in enumerate(methods, 1):
        print(f"\n########## [{i}/{len(methods)}] {m} ##########")
        code = run_one(m, args.epochs, args.imgsz, args.batch)
        if code != 0:
            print(f"Stopping (method '{m}' failed). Fix and re-run just that method with --method {m}.")
            break
    else:
        print(f"\nAll {len(methods)} method(s) finished: {methods}")


if __name__ == "__main__":
    main()
