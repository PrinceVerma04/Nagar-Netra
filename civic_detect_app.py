"""
Streamlit demo for the 16-class civic-issue detector.

Upload images (one or many), point it at a folder on disk, or upload a video clip;
it runs the trained YOLO11n model and reports what it found, per file and in
aggregate.

Deliberate choices worth knowing about:

* Any of the four trained variants can be selected. `oversampled` is the default
  because it won the 2026-09-07 comparison (mAP@50 0.604), but being able to switch
  matters - the whole point of that experiment was that the methods differ per class.

* Detections are split into ISSUES and HEALTHY STATES. `manhole_closed` and
  `streetlight_working` are things the model is supposed to find and then NOT report:
  a working streetlight is not a civic incident. The Android app makes the same
  distinction, and mixing them would make the counts meaningless.

* Video is sampled every Nth frame rather than decoded frame-by-frame. At 30fps a
  10-second clip is 300 nearly identical frames; sampling keeps it responsive and
  loses almost nothing, since consecutive frames are near-duplicates.

* The confidence slider defaults to 0.25 for exploration, but the phone app ships
  0.40. There is a note in the UI about this, because a demo that looks great at 0.25
  and then underperforms on the phone is a trap.

Run:
    streamlit run civic_detect_app.py
    streamlit run civic_detect_app.py --server.address 0.0.0.0 --server.port 8501
"""
import json
import tempfile
from collections import Counter
from pathlib import Path

import cv2
import numpy as np
import streamlit as st
from PIL import Image

BASE = Path(__file__).resolve().parent
RESULTS = BASE / "training_results"
IMG_EXTS = (".jpg", ".jpeg", ".png", ".bmp", ".webp")
VID_EXTS = (".mp4", ".mov", ".avi", ".mkv", ".webm")

# Healthy states: detected on purpose, never an incident.
OK_CLASSES = {"manhole_closed", "streetlight_working"}

MODELS = {
    "oversampled  (best — mAP@50 0.604)": "civic_services_oversampled",
    "unbalanced  (baseline — 0.596)": "civic_services_unbalanced",
    "augmented  (0.568)": "civic_services_augmented",
    "undersampled  (0.532)": "civic_services_undersampled",
}

st.set_page_config(page_title="Civic Issue Detector", page_icon="🛣️", layout="wide")


@st.cache_resource(show_spinner=False)
def load_model(weights_path: str):
    from ultralytics import YOLO
    return YOLO(weights_path)


def available_models():
    out = {}
    for label, folder in MODELS.items():
        w = RESULTS / folder / "weights" / "best.pt"
        if w.is_file():
            out[label] = str(w)
    return out


def run_one(model, image_bgr, conf, iou):
    """-> (original RGB, annotated RGB, [(label, confidence), ...])

    The original is returned too so the UI can show before/after together - with only
    the annotated frame you cannot tell a missed detection from an image that never
    contained the object, which is exactly the distinction that matters when judging
    the model.
    """
    r = model.predict(image_bgr, conf=conf, iou=iou, verbose=False)[0]
    dets = [(model.names[int(c)], float(s))
            for c, s in zip(r.boxes.cls.tolist(), r.boxes.conf.tolist())]
    dets.sort(key=lambda t: -t[1])
    return (cv2.cvtColor(image_bgr, cv2.COLOR_BGR2RGB),
            cv2.cvtColor(r.plot(), cv2.COLOR_BGR2RGB),
            dets)


def render_pair(name, original, annotated, dets):
    """One result: original on the left, model output on the right."""
    st.markdown(f"**`{name}`** — {det_caption(dets)}")
    c1, c2 = st.columns(2)
    c1.image(original, caption="Original", width='stretch')
    c2.image(annotated,
             caption=("Detected" if dets else "Detected — nothing found"),
             width='stretch')
    if dets:
        st.dataframe(
            [{"#": i + 1, "class": l, "confidence": round(c, 3),
              "type": "healthy state" if l in OK_CLASSES else "civic issue"}
             for i, (l, c) in enumerate(dets)],
            hide_index=True, width='stretch')
    st.divider()


def summarise(rows):
    """rows: list of (name, dets). Renders the aggregate panel."""
    issues, healthy = Counter(), Counter()
    empty = 0
    for _, dets in rows:
        if not dets:
            empty += 1
        for lbl, _ in dets:
            (healthy if lbl in OK_CLASSES else issues)[lbl] += 1

    c1, c2, c3 = st.columns(3)
    c1.metric("Files processed", len(rows))
    c2.metric("Issue detections", sum(issues.values()))
    c3.metric("Nothing detected", f"{empty} / {len(rows)}")

    if issues:
        st.markdown("**Civic issues found**")
        st.dataframe(
            [{"class": k, "detections": v} for k, v in issues.most_common()],
            hide_index=True, width='stretch')
    if healthy:
        st.markdown("**Healthy states** (detected, but not incidents)")
        st.dataframe(
            [{"class": k, "detections": v} for k, v in healthy.most_common()],
            hide_index=True, width='stretch')
    if not issues and not healthy:
        st.info("No detections at any confidence above the threshold. "
                "Try lowering the slider in the sidebar.")


def det_caption(dets):
    if not dets:
        return "— nothing detected"
    return " · ".join(f"**{l}** {c:.2f}" for l, c in dets[:4]) + \
           (f" · +{len(dets) - 4} more" if len(dets) > 4 else "")


# --------------------------------------------------------------------- sidebar

st.sidebar.title("Settings")
models = available_models()
if not models:
    st.error(f"No trained weights found under {RESULTS}. Train a model first.")
    st.stop()

model_label = st.sidebar.selectbox("Model", list(models))
model = load_model(models[model_label])

conf = st.sidebar.slider("Confidence threshold", 0.05, 0.95, 0.25, 0.05)
iou = st.sidebar.slider("NMS IoU", 0.1, 0.9, 0.45, 0.05)
if conf < 0.40:
    st.sidebar.caption("⚠️ The Android app ships a 0.40 threshold. Results below that "
                       "will look better here than they do on the phone.")

st.sidebar.markdown("---")
st.sidebar.caption(f"**{len(model.names)} classes**")
st.sidebar.caption(", ".join(model.names[i] for i in sorted(model.names)))

# ------------------------------------------------------------------- main page

st.title("🛣️ Civic Issue Detector")
st.caption("YOLO11n · 16 classes · trained on 3,118 images · runs fully offline")

tab_img, tab_folder, tab_vid = st.tabs(
    ["📤 Upload images", "📁 Folder on disk", "🎬 Video clip"])

# ---- images -----------------------------------------------------------------
with tab_img:
    ups = st.file_uploader("Choose one or more images", type=[e[1:] for e in IMG_EXTS],
                           accept_multiple_files=True, key="imgs")
    if ups:
        rows = []
        with st.spinner(f"Running the detector on {len(ups)} image(s)…"):
            results = []
            for f in ups:
                arr = np.frombuffer(f.getvalue(), np.uint8)
                img = cv2.imdecode(arr, cv2.IMREAD_COLOR)
                if img is None:
                    continue
                orig, vis, dets = run_one(model, img, conf, iou)
                results.append((f.name, orig, vis, dets))
                rows.append((f.name, dets))
        summarise(rows)
        st.markdown("### Original vs detected")
        for name, orig, vis, dets in results:
            render_pair(name, orig, vis, dets)
        st.download_button(
            "Download results as JSON",
            json.dumps([{"file": n, "detections": [{"class": l, "conf": round(c, 3)}
                                                   for l, c in d]} for n, d in rows],
                       indent=2),
            file_name="detections.json", mime="application/json")

# ---- folder -----------------------------------------------------------------
with tab_folder:
    st.write("Point at a folder already on this machine — useful for a whole "
             "collection without re-uploading.")
    default = str(BASE / "data for test/external_test_images")
    folder = st.text_input("Folder path", value=default)
    recursive = st.checkbox("Include sub-folders", value=True)
    limit = st.number_input("Max images to process", 1, 2000, 60,
                            help="Guard against pointing at the whole dataset by accident.")
    if st.button("Run on folder", type="primary"):
        p = Path(folder).expanduser()
        if not p.is_dir():
            st.error(f"Not a folder: {p}")
        else:
            files = sorted([f for f in (p.rglob("*") if recursive else p.iterdir())
                            if f.suffix.lower() in IMG_EXTS])
            if not files:
                st.warning("No images found there.")
            else:
                shown = files[:int(limit)]
                if len(files) > len(shown):
                    st.info(f"{len(files)} images found; processing the first {len(shown)}.")
                rows, results = [], []
                bar = st.progress(0.0, text="Running…")
                for i, f in enumerate(shown, 1):
                    img = cv2.imread(str(f))
                    if img is None:
                        continue
                    orig, vis, dets = run_one(model, img, conf, iou)
                    results.append((str(f.relative_to(p)), orig, vis, dets))
                    rows.append((str(f.relative_to(p)), dets))
                    bar.progress(i / len(shown), text=f"{i}/{len(shown)}  {f.name}")
                bar.empty()
                summarise(rows)
                st.markdown("### Summary table")
                st.dataframe(
                    [{"file": n, "top": d[0][0] if d else "—",
                      "conf": round(d[0][1], 3) if d else None,
                      "all": ", ".join(sorted({l for l, _ in d})) or "—"}
                     for n, d in rows],
                    hide_index=True, width='stretch')
                st.markdown("### Original vs detected")
                for name, orig, vis, dets in results:
                    render_pair(name, orig, vis, dets)

# ---- video ------------------------------------------------------------------
with tab_vid:
    vid = st.file_uploader("Choose a video clip", type=[e[1:] for e in VID_EXTS],
                           key="vid")
    every = st.slider("Analyse every Nth frame", 1, 60, 15,
                      help="Consecutive frames are near-identical; sampling keeps this "
                           "fast without losing detections.")
    max_frames = st.number_input("Max frames to analyse", 1, 600, 60)
    if vid is not None and st.button("Run on video", type="primary"):
        with tempfile.NamedTemporaryFile(delete=False,
                                         suffix=Path(vid.name).suffix) as tf:
            tf.write(vid.getvalue())
            tmp_path = tf.name
        cap = cv2.VideoCapture(tmp_path)
        if not cap.isOpened():
            st.error("Could not open that video.")
        else:
            fps = cap.get(cv2.CAP_PROP_FPS) or 25.0
            total = int(cap.get(cv2.CAP_PROP_FRAME_COUNT) or 0)
            st.caption(f"{total} frames @ {fps:.0f} fps — analysing every {every}th, "
                       f"up to {max_frames}.")
            rows, results = [], []
            bar = st.progress(0.0, text="Decoding…")
            idx = analysed = 0
            while analysed < max_frames:
                ok, frame = cap.read()
                if not ok:
                    break
                if idx % every == 0:
                    orig, vis, dets = run_one(model, frame, conf, iou)
                    ts = idx / fps
                    label = f"t={ts:5.1f}s (frame {idx})"
                    rows.append((label, dets))
                    if dets:
                        results.append((label, orig, vis, dets))
                    analysed += 1
                    if total:
                        bar.progress(min(idx / total, 1.0),
                                     text=f"{analysed} frames analysed")
                idx += 1
            cap.release()
            bar.empty()
            Path(tmp_path).unlink(missing_ok=True)

            summarise(rows)
            st.markdown("---")
            if results:
                st.markdown(f"### Frames with detections "
                            f"({len(results)} of {len(rows)} analysed)")
                for label, orig, vis, dets in results:
                    render_pair(label, orig, vis, dets)
            else:
                st.info("No frames produced a detection above the threshold.")
