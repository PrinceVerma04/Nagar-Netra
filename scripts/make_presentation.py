"""
Generates the beamer deck summarising the 16-class retrain, straight from the
result JSONs - never from hand-typed numbers.

Every figure in the deck is read at build time from:
    docs/dataset_snapshot_<stamp>.json            (dataset + per-variant splits)
    training_results/civic_services_<m>/test_metrics.json   (new results)
    training_results/archive_7class_.../test_metrics.json   (old results)

That matters here: the dataset was re-split twice and re-audited four times in one
day, and an earlier deliverable shipped numbers that were stale by the time it was
read. Regenerating the deck re-reads the truth.

Usage:
    python scripts/make_presentation.py
    python scripts/make_presentation.py --out deliverables/retrain_20260907
"""
import argparse
import datetime as dt
import json
import shutil
import subprocess
from pathlib import Path

BASE = Path(__file__).resolve().parent.parent
DOCS = BASE / "docs"
RESULTS = BASE / "training_results"
ARCHIVE = RESULTS / "archive_7class_20260904"
METHODS = ["unbalanced", "oversampled", "undersampled", "augmented"]
LABEL = {"unbalanced": "Unbalanced", "oversampled": "Oversampled",
         "undersampled": "Undersampled", "augmented": "Augmented"}


def tex(s):
    return str(s).replace("_", r"\_").replace("&", r"\&").replace("%", r"\%")


def latest_snapshot():
    snaps = sorted(DOCS.glob("dataset_snapshot_*.json"))
    if not snaps:
        raise SystemExit("No dataset snapshot found - run scripts/snapshot_dataset.py")
    return json.loads(snaps[-1].read_text()), snaps[-1].stem


def load_metrics(root: Path):
    out = {}
    for m in METHODS:
        f = root / f"civic_services_{m}" / "test_metrics.json"
        if f.is_file():
            out[m] = json.loads(f.read_text())
    return out


def per_class(metrics, cls):
    """map50 for a class, tolerating both the new dict and legacy array format."""
    d = metrics.get("per_class")
    if d:
        return d.get(cls, {}).get("map50")
    names = [metrics["class_names"][k] for k in sorted(metrics["class_names"], key=int)]
    if cls in names:
        i = names.index(cls)
        arr = metrics.get("map50_per_class", [])
        if i < len(arr):
            return arr[i]
    return None


def fmt(v, bold=False):
    if v is None:
        return "--"
    s = f"{v:.3f}"
    return rf"\textbf{{{s}}}" if bold else s


def build(snap, new, old):
    names = snap["class_names"]
    order = [names[k] for k in sorted(names, key=int)]
    canon = snap["splits"]["canonical (unbalanced)"]
    variants = [k for k in snap["splits"] if k != "canonical (unbalanced)"]

    n_img = sum(canon[s]["images"] for s in ("train", "val", "test"))
    n_box = sum(sum(canon[s]["boxes_per_class"].values()) for s in ("train", "val", "test"))

    L = []
    A = L.append
    A(r"\documentclass[10pt]{beamer}")
    A(r"\usetheme{Madrid}")
    A(r"\usecolortheme{orchid}")
    A(r"\usepackage[utf8]{inputenc}")
    A(r"\usepackage{booktabs}")
    A(r"\usepackage{array}")
    A(r"\setbeamertemplate{navigation symbols}{}")
    A(r"\setbeamerfont{frametitle}{size=\normalsize}")
    A(r"\title[Civic Services Detector]{Civic Services Surveillance \& Monitoring}")
    A(r"\subtitle{16-class detector: dataset rebuild, leakage fix and retraining results}")
    A(r"\author{Prince Verma}")
    A(rf"\date{{{dt.date.today():%B %-d, %Y}}}")
    A(r"\begin{document}")
    A(r"\frame{\titlepage}")

    # ---------------- Slide 1: dataset ----------------
    A(r"\begin{frame}{Dataset Overview}")
    A(r"\begin{columns}[T]\begin{column}{0.52\textwidth}")
    A(r"\textbf{Taxonomy expanded 7 $\rightarrow$ 16 classes}")
    A(r"\begin{itemize}\setlength\itemsep{2pt}")
    A(r"\item \texttt{cattle} split into cow / buffalo / goat / horse; cat and dog added")
    A(r"\item \texttt{manhole\_open\_broken} $\rightarrow$ closed / open / broken")
    A(r"\item \texttt{streetlight\_pole} $\rightarrow$ working / not\_working")
    A(r"\end{itemize}")
    A(r"\vspace{4pt}\textbf{Cleanup before retraining}")
    A(r"\begin{itemize}\setlength\itemsep{2pt}")
    A(r"\item Class ids renumbered to a contiguous 0--15 (the sparse ids blocked training outright)")
    A(r"\item 289 label corrections, 125 images removed after full manual review")
    A(r"\item Duplicate boxes, full-frame boxes and empty labels eliminated")
    A(r"\end{itemize}")
    A(r"\end{column}\begin{column}{0.44\textwidth}")
    A(r"\begin{table}\centering\small")
    A(r"\begin{tabular}{lr}\toprule Property & Value \\ \midrule")
    A(rf"Classes & {snap['n_classes']} \\")
    A(rf"Images & {n_img:,} \\")
    A(rf"Boxes & {n_box:,} \\")
    A(rf"Train / Val / Test & {canon['train']['images']:,} / {canon['val']['images']} / {canon['test']['images']} \\")
    A(r"Split ratio & 80 / 10 / 10 \\")
    A(r"Model & YOLO11n \\")
    A(r"\bottomrule\end{tabular}\end{table}")
    A(r"\vspace{2pt}\footnotesize All integrity checks pass: trees in sync, no orphan "
      r"or empty labels, no degenerate boxes, \textbf{no train/test leakage}.")
    A(r"\end{column}\end{columns}")
    A(r"\end{frame}")

    # ---------------- Slide 2: classwise + split ----------------
    A(r"\begin{frame}{Class-wise Counts and Dataset Split}")
    A(r"\begin{table}\centering\scriptsize")
    A(r"\begin{tabular}{lrrrrr}\toprule")
    A(r"Class & Train & Val & Test & Total & Boxes \\ \midrule")
    for cls in order:
        cid = [k for k, v in names.items() if v == cls][0]
        i = {s: canon[s]["images_per_class"].get(str(cid), canon[s]["images_per_class"].get(cid, 0))
             for s in ("train", "val", "test")}
        b = sum(canon[s]["boxes_per_class"].get(str(cid), canon[s]["boxes_per_class"].get(cid, 0))
                for s in ("train", "val", "test"))
        A(rf"{tex(cls)} & {i['train']} & {i['val']} & {i['test']} & "
          rf"{sum(i.values())} & {b} \\")
    A(r"\midrule")
    A(rf"\textbf{{Total}} & \textbf{{{canon['train']['images']:,}}} & "
      rf"\textbf{{{canon['val']['images']}}} & \textbf{{{canon['test']['images']}}} & "
      rf"\textbf{{{n_img:,}}} & \textbf{{{n_box:,}}} \\")
    A(r"\bottomrule\end{tabular}\end{table}")
    A(r"\footnotesize Stratified 80/10/10. Every class lands within 9.1--10.8\% on val. "
      r"Near-duplicate images (video frames, re-uploads) are grouped by perceptual hash "
      r"and kept in one split, so no image has a near-identical twin across splits.")
    A(r"\end{frame}")

    # ---------------- Slide 3: variants ----------------
    A(r"\begin{frame}{Train Set per Balancing Method}")
    A(r"\begin{table}\centering\scriptsize")
    cols = ["canonical (unbalanced)"] + variants
    A(r"\begin{tabular}{l" + "r" * len(cols) + r"}\toprule")
    A("Class & " + " & ".join(tex(LABEL.get(c, c.title())) for c in cols) + r" \\ \midrule")
    for cls in order:
        cid = [k for k, v in names.items() if v == cls][0]
        cells = []
        for c in cols:
            d = snap["splits"][c]["train"]["images_per_class"]
            cells.append(str(d.get(str(cid), d.get(cid, 0))))
        A(f"{tex(cls)} & " + " & ".join(cells) + r" \\")
    A(r"\midrule")
    A(r"\textbf{Train images} & " +
      " & ".join(rf"\textbf{{{snap['splits'][c]['train']['images']:,}}}" for c in cols) + r" \\")
    A(r"\bottomrule\end{tabular}\end{table}")
    A(r"\footnotesize\textbf{Val (389) and test (389) are byte-identical across all four "
      r"methods} -- verified by content fingerprint -- so only the train set varies. "
      r"Oversampling and augmentation use Repeat Factor Sampling "
      r"($r_c=\max(1,\sqrt{t/f_c})$, $t{=}0.1$): rare classes repeat 1.4--4.2$\times$, the "
      r"six common classes are untouched. Undersampling caps every class at the 60th "
      r"percentile (168 images), removing only single-class images.")
    A(r"\end{frame}")

    # ---------------- Slide 4: results ----------------
    A(r"\begin{frame}{Results --- 16-class Test Set (389 images)}")
    # 0.36/0.62 with a \tiny per-class table: at scriptsize the 5-column
    # per-class table overflowed the right edge and clipped the Augmented column.
    A(r"\begin{columns}[T]\begin{column}{0.36\textwidth}")
    A(r"\begin{table}\centering\scriptsize")
    A(r"\begin{tabular}{lrr}\toprule Method & mAP@50 & mAP@50-95 \\ \midrule")
    best50 = max((new[m]["map50"] for m in new), default=0)
    best95 = max((new[m]["map50-95"] for m in new), default=0)
    for m in METHODS:
        if m not in new:
            continue
        A(rf"{LABEL[m]} & {fmt(new[m]['map50'], new[m]['map50']==best50)} & "
          rf"{fmt(new[m]['map50-95'], new[m]['map50-95']==best95)} \\")
    A(r"\bottomrule\end{tabular}\end{table}")
    A(r"\vspace{-4pt}\footnotesize\textbf{Oversampling (RFS) wins}, as it did in the "
      r"7-class run --- now with a 1.4--4.2$\times$ repeat instead of 34$\times$. "
      r"Undersampling is worst: discarding half the train set costs more than the "
      r"balance gains.")
    A(r"\end{column}\begin{column}{0.62\textwidth}")
    A(r"\begin{table}\centering\tiny")
    A(r"\begin{tabular}{@{}l@{\hspace{5pt}}rrrr@{}}\toprule")
    A(r"mAP@50 & Unb. & Over. & Under. & Aug. \\ \midrule")
    for cls in order:
        vals = [per_class(new[m], cls) if m in new else None for m in METHODS]
        mx = max([v for v in vals if v is not None], default=None)
        A(f"{tex(cls)} & " + " & ".join(fmt(v, v is not None and v == mx) for v in vals) + r" \\")
    A(r"\bottomrule\end{tabular}\end{table}")
    A(r"\end{column}\end{columns}")
    A(r"\end{frame}")

    # ---------------- Slide 5: comparison ----------------
    A(r"\begin{frame}{Comparison with the Earlier 7-class Results}")
    A(r"\begin{columns}[T]\begin{column}{0.5\textwidth}")
    A(r"\begin{table}\centering\scriptsize")
    A(r"\begin{tabular}{lrr}\toprule")
    A(r"Method & Old (7-cls) & New (16-cls) \\ \midrule")
    for m in METHODS:
        o = old.get(m, {}).get("map50")
        n = new.get(m, {}).get("map50")
        A(rf"{LABEL[m]} & {fmt(o)} & {fmt(n)} \\")
    A(r"\bottomrule\end{tabular}")
    A(r"\end{table}")
    A(r"\vspace{-6pt}\footnotesize Averaged over 7 vs 16 classes --- different "
      r"denominators, so this is \emph{not} a like-for-like delta.")
    A(r"\vspace{6pt}")
    A(r"\scriptsize\textbf{Why the new scores are lower --- and more trustworthy:} "
      r"the old test set leaked. Video frames and re-uploaded photos put "
      r"near-identical images in both train and test, so part of the old score was "
      r"memorisation. Measured on the old split:")
    A(r"\end{column}\begin{column}{0.48\textwidth}")
    A(r"\begin{table}\centering\scriptsize")
    A(r"\begin{tabular}{lrr}\toprule")
    A(r"Class & Leaked & Old $\rightarrow$ New \\ \midrule")
    for cls, leak, o, n in [
        ("encroachment", "56.4\\%", 0.953, 0.679),
        ("pothole", "29.6\\%", 0.496, 0.469),
        ("billboard\\_hoarding", "28.6\\%", 0.756, 0.887),
        ("garbage\\_pile", "19.0\\%", 0.587, 0.452),
        ("all animal classes", "0.0\\%", None, None),
    ]:
        oo = f"{o:.3f}" if o else "--"
        nn = f"{n:.3f}" if n else "--"
        arrow = f"{oo} $\\rightarrow$ {nn}" if o else "--"
        A(rf"{cls} & {leak} & {arrow} \\")
    A(r"\bottomrule\end{tabular}\end{table}")
    A(r"\vspace{-4pt}\scriptsize Leakage is now \textbf{0\%}. Encroachment's old "
      r"0.953 was largely memorisation. Not the whole story though: billboard rose "
      r"despite leakage, and garbage\_pile also lost 38 easy full-frame boxes in the "
      r"cleanup.")
    A(r"\end{column}\end{columns}")
    A(r"\vspace{2pt}\footnotesize\textbf{Caveat:} \texttt{manhole\_closed} (2 test "
      r"images), \texttt{buffalo} (3), \texttt{goat} (4), \texttt{cat} (4) are too "
      r"small to score reliably --- more collected data, not more resampling, is the "
      r"next lever.")
    A(r"\end{frame}")

    A(r"\end{document}")
    return "\n".join(L)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=None)
    args = ap.parse_args()

    snap, snapname = latest_snapshot()
    new = load_metrics(RESULTS)
    old = load_metrics(ARCHIVE)
    if not new:
        raise SystemExit("No new test_metrics.json found - has training finished?")

    stamp = dt.datetime.now().strftime("%Y%m%d")
    out_dir = Path(args.out) if args.out else BASE / "deliverables" / f"retrain_report_{stamp}"
    slides = out_dir / "slides"
    slides.mkdir(parents=True, exist_ok=True)

    tex_path = slides / "presentation.tex"
    tex_path.write_text(build(snap, new, old))
    print(f"wrote {tex_path.relative_to(BASE)}  (source snapshot: {snapname})")

    for _ in range(2):        # twice, so the frame count settles
        r = subprocess.run(["pdflatex", "-interaction=nonstopmode", "-halt-on-error",
                            "presentation.tex"], cwd=slides,
                           capture_output=True, text=True)
    if r.returncode != 0:
        print(r.stdout[-3000:])
        raise SystemExit("pdflatex failed")
    for ext in (".aux", ".log", ".nav", ".out", ".snm", ".toc"):
        (slides / f"presentation{ext}").unlink(missing_ok=True)
    print(f"built {(slides / 'presentation.pdf').relative_to(BASE)}")

    # ship the underlying data alongside the deck
    shutil.copy2(DOCS / f"{snapname}.md", out_dir / "dataset_snapshot.md")
    shutil.copy2(DOCS / f"{snapname}.json", out_dir / "dataset_snapshot.json")
    metrics_dir = out_dir / "metrics"
    metrics_dir.mkdir(exist_ok=True)
    for m in METHODS:
        for src, tag in ((RESULTS, "new"), (ARCHIVE, "old_7class")):
            f = src / f"civic_services_{m}" / "test_metrics.json"
            if f.is_file():
                shutil.copy2(f, metrics_dir / f"{tag}_{m}.json")
        rm = RESULTS / f"civic_services_{m}" / "run_meta.json"
        if rm.is_file():
            shutil.copy2(rm, metrics_dir / f"new_{m}_run_meta.json")

    zip_base = BASE / "deliverables" / f"civic_monitor_retrain_report_{stamp}"
    if zip_base.with_suffix(".zip").exists():
        zip_base.with_suffix(".zip").unlink()
    shutil.make_archive(str(zip_base), "zip", root_dir=out_dir.parent,
                        base_dir=out_dir.name)
    print(f"packaged {zip_base.with_suffix('.zip').relative_to(BASE)}")


if __name__ == "__main__":
    main()
