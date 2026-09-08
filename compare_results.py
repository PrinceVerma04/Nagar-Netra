"""
Compares training runs on the held-out test split - both across balancing methods
within one taxonomy, and across the 2026-09-04 taxonomy change (old 7-class runs
vs new 16-class runs).

The taxonomy change makes a naive side-by-side dishonest, so this script refuses
to print one. Classes fall into three buckets:

  SAME        garbage_pile, pothole, encroachment, billboard_hoarding
              Same name, same meaning, same label definition. Directly comparable;
              a delta here is a real signal about the retrain.

  NARROWED    cattle -> cow
              Same class id lineage but the MEANING changed: old `cattle` was one
              bucket holding cows, buffalo, goats and horses; `cow` is now cows
              only, with the rest split into their own classes. A cow-vs-cattle
              delta mixes "the model got better" with "the class got easier/harder
              because its definition changed". Reported, but flagged, never summed
              into a headline number.

  SPLIT       manhole_open_broken -> manhole_closed + manhole_open + manhole_broken
              streetlight_pole    -> streetlight_working + streetlight_not_working
              A 3-way and a 2-way split of what used to be one class each. The new
              classes have no single old counterpart; a per-class delta is
              undefined. Reported as new territory with no baseline.

Overall mAP50 across a 7-class and a 16-class run is likewise NOT comparable - the
mean is taken over a different, harder set of classes - so it is printed in
separate blocks rather than as a delta.

Usage:
    python compare_results.py                       # new runs only
    python compare_results.py --vs-archive training_results/archive_7class_20260904
    python compare_results.py --vs-archive <dir> --metric map50-95
"""
import argparse
import json
from pathlib import Path

BASE = Path(__file__).resolve().parent
RESULTS = BASE / "training_results"
METHODS = ["unbalanced", "oversampled", "undersampled", "augmented"]

SAME = ["garbage_pile", "pothole", "encroachment", "billboard_hoarding"]
NARROWED = {"cow": "cattle"}
SPLIT = {
    "manhole_open_broken": ["manhole_closed", "manhole_open", "manhole_broken"],
    "streetlight_pole": ["streetlight_working", "streetlight_not_working"],
}


def load(run_dir: Path):
    """Reads test_metrics.json in either the old (positional arrays) or new
    (per_class dict) format and normalises to {class_name: {metric: value}}."""
    f = run_dir / "test_metrics.json"
    if not f.is_file():
        return None
    d = json.loads(f.read_text())

    if "per_class" in d:                       # new format
        per_class = d["per_class"]
    else:                                      # legacy format
        # Legacy runs stored p/r/ap50 as arrays assumed to align with class_names
        # in order. That assumption held for those runs (all 7 classes had test
        # labels), so decoding them positionally is correct HERE - but it is the
        # exact bug fixed in train_one_method.py, so never reuse this path for
        # new runs.
        names = [d["class_names"][k] for k in sorted(d["class_names"], key=int)]
        per_class = {}
        for i, name in enumerate(names):
            if i < len(d.get("map50_per_class", [])):
                per_class[name] = {
                    "precision": d["precision_per_class"][i],
                    "recall": d["recall_per_class"][i],
                    "map50": d["map50_per_class"][i],
                }
    return {
        "overall": {k: d[k] for k in ("map50", "map50-95", "map75") if k in d},
        "per_class": per_class,
        "n_classes": len(d.get("class_names", {})),
        "absent": d.get("classes_absent_from_test_split", []),
    }


def load_all(root: Path):
    runs = {}
    for m in METHODS:
        r = load(root / f"civic_services_{m}")
        if r:
            runs[m] = r
    return runs


def fmt(v, width=7):
    return f"{v:{width}.4f}" if isinstance(v, (int, float)) else " " * (width - 1) + "-"


def print_overall(title, runs, metric):
    print(f"\n{title}")
    print(f"  {'method':16s} {'map50':>8} {'map50-95':>9} {'map75':>8} {'classes':>8}")
    for m, r in runs.items():
        o = r["overall"]
        print(f"  {m:16s} {fmt(o.get('map50'), 8)} {fmt(o.get('map50-95'), 9)} "
              f"{fmt(o.get('map75'), 8)} {r['n_classes']:>8}")
    if runs:
        best = max(runs, key=lambda m: runs[m]["overall"].get(metric, -1))
        print(f"  -> best by {metric}: {best} "
              f"({runs[best]['overall'].get(metric, float('nan')):.4f})")


def print_per_class(runs, metric):
    if not runs:
        return
    all_classes = []
    for r in runs.values():
        for c in r["per_class"]:
            if c not in all_classes:
                all_classes.append(c)
    print(f"\n  per-class {metric}")
    header = "  " + f"{'class':26s}" + "".join(f"{m[:10]:>11}" for m in runs)
    print(header)
    for c in all_classes:
        row = "  " + f"{c:26s}"
        for r in runs.values():
            v = r["per_class"].get(c, {}).get(metric)
            row += f"{v:>11.4f}" if v is not None else f"{'-':>11}"
        print(row)


def compare_taxonomies(old_runs, new_runs, metric):
    print(f"\n{'=' * 78}")
    print(f"OLD (7-class) vs NEW (16-class)   metric: {metric}")
    print(f"{'=' * 78}")

    common = [m for m in METHODS if m in old_runs and m in new_runs]
    if not common:
        print("  No method was trained in both taxonomies - nothing to compare.")
        return

    print(f"\n--- DIRECTLY COMPARABLE (same class, same definition) ---")
    print("  " + f"{'class':26s}" + "".join(f"{m[:9]:>22}" for m in common))
    print("  " + " " * 26 + "".join(f"{'old':>10}{'new':>7}{'Δ':>5}" for _ in common))
    for c in SAME:
        row = "  " + f"{c:26s}"
        for m in common:
            o = old_runs[m]["per_class"].get(c, {}).get(metric)
            n = new_runs[m]["per_class"].get(c, {}).get(metric)
            if o is None or n is None:
                row += f"{'-':>22}"
            else:
                row += f"{o:>10.4f}{n:>7.4f}{n - o:>+5.2f}"
        print(row)

    print(f"\n--- NARROWED (class meaning changed - delta is NOT pure model quality) ---")
    for new_c, old_c in NARROWED.items():
        row = "  " + f"{old_c} -> {new_c:<18}"
        for m in common:
            o = old_runs[m]["per_class"].get(old_c, {}).get(metric)
            n = new_runs[m]["per_class"].get(new_c, {}).get(metric)
            if o is None or n is None:
                row += f"{'-':>22}"
            else:
                row += f"{o:>10.4f}{n:>7.4f}{n - o:>+5.2f}"
        print(row)
    print("    ^ old 'cattle' bundled cow+buffalo+goat+horse; 'cow' is cows only.")

    print(f"\n--- SPLIT (new classes, no single old baseline) ---")
    for old_c, new_cs in SPLIT.items():
        base = {m: old_runs[m]["per_class"].get(old_c, {}).get(metric) for m in common}
        base_s = "  ".join(f"{m}={base[m]:.4f}" for m in common if base[m] is not None)
        print(f"  was '{old_c}':  {base_s}")
        for nc in new_cs:
            row = "    -> " + f"{nc:<24}"
            for m in common:
                v = new_runs[m]["per_class"].get(nc, {}).get(metric)
                row += f"{v:>11.4f}" if v is not None else f"{'unscored':>11}"
            print(row)
        print()

    brand_new = ["cat", "horse", "dog", "buffalo", "goat", "camel"]
    print(f"--- BRAND NEW CLASSES (did not exist in the 7-class taxonomy) ---")
    for nc in brand_new:
        row = "  " + f"{nc:26s}"
        for m in common:
            v = new_runs[m]["per_class"].get(nc, {}).get(metric)
            row += f"{v:>11.4f}" if v is not None else f"{'unscored':>11}"
        print(row)

    absent = new_runs[common[0]].get("absent") or []
    if absent:
        print(f"\n  NOTE: {absent} have no labels in the test split - "
              f"they are unscored, not zero. Fix by rebalancing the split before "
              f"treating their absence as a result.")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--results", default=str(RESULTS),
                    help="directory holding civic_services_<method>/ for the NEW runs")
    ap.add_argument("--vs-archive", default=None,
                    help="directory holding the archived OLD 7-class runs")
    ap.add_argument("--metric", default="map50", choices=["map50", "map50-95", "precision", "recall"])
    args = ap.parse_args()

    new_runs = load_all(Path(args.results))
    if not new_runs:
        raise SystemExit(f"No test_metrics.json found under {args.results} - "
                         f"has anything finished training yet?")

    print(f"{'=' * 78}\nNEW RUNS  ({args.results})\n{'=' * 78}")
    print_overall("overall (test split)", new_runs, args.metric if args.metric in
                  ("map50", "map50-95") else "map50")
    print_per_class(new_runs, args.metric)

    if args.vs_archive:
        old_runs = load_all(Path(args.vs_archive))
        if not old_runs:
            raise SystemExit(f"No runs found in archive {args.vs_archive}")
        print(f"\n{'=' * 78}\nARCHIVED RUNS  ({args.vs_archive})\n{'=' * 78}")
        print_overall("overall (test split)", old_runs, args.metric if args.metric in
                      ("map50", "map50-95") else "map50")
        print("\n  Overall mAP above is averaged over 7 classes vs 16 for the new "
              "runs - \n  different denominators, so do NOT read a headline delta "
              "from these two blocks.")
        compare_taxonomies(old_runs, new_runs, args.metric)


if __name__ == "__main__":
    main()
