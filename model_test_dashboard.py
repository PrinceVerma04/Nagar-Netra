"""
Multi-person model testing dashboard, with correction.

Several people on the same WiFi open one URL, feed the detector single photos, whole
folders, or video clips, mark each result right or wrong, and - when it is wrong - draw
the correct boxes themselves. Everything each person contributes is filed under their
own name.

WHY THIS AND NOT THE STREAMLIT DEMO: `civic_detect_app.py` is a single-user demo -
Streamlit reruns the whole script per interaction and has no shared state, so ten
people would each get an isolated session and nothing would aggregate. This follows the
project's own dashboard standard (docs/ANNOTATION_DASHBOARD_STANDARD.md): one Flask
process as the single source of truth, state in JSON flushed on every write, identity in
localStorage, a separate read-only /stats page, and the same canvas box editor.

WHAT THE DESIGN IS TRYING TO GET RIGHT:
  * Testers say what was ACTUALLY there, not just thumbs up/down. Without the true class
    you learn "wrong" and nothing about how - and the direction of the errors is what
    mattered last time (dog->cow, manhole_closed->manhole_broken).
  * "Missed entirely" is its own verdict, not lumped into "wrong". 48 of 119 images in
    the web evaluation produced no detection at all; a miss and a misname need different
    fixes.
  * A wrong result opens the annotator instead of ending there. A corrected box is worth
    far more than a complaint - it is training data for exactly the failure that was
    just found. Labels are written in YOLO format against the ORIGINAL image, ready to
    merge into the dataset.
  * Per-tester folders (data/field_test_images/<name>/images|labels) keep contributions
    attributable, so a person who systematically mislabels can be spotted and their
    batch re-checked rather than silently poisoning the set.
  * Inference letterboxes to square, matching how the model was trained. Stretching
    instead cost ~9 points on real photos - the same bug that was fixed in the Android
    app's Detector.kt.

Phones shoot straight into it: the camera input uses capture="environment".

Run:
    python model_test_dashboard.py
    python model_test_dashboard.py --port 5080 --weights <path to best.pt>
"""
import argparse
import base64
import datetime as dt
import hashlib
import json
import re
import socket
import tempfile
import threading
from collections import Counter, defaultdict
from pathlib import Path

import cv2
import numpy as np
from flask import Flask, jsonify, request, send_file

BASE = Path(__file__).resolve().parent
DEFAULT_WEIGHTS = BASE / "training_results/civic_services_oversampled/weights/best.pt"
STORE = BASE / "data/field_test_images"
RESULTS_PATH = STORE / "field_test_results.json"

OK_CLASSES = {"manhole_closed", "streetlight_working"}
IMG_EXTS = (".jpg", ".jpeg", ".png", ".bmp", ".webp")

_lock = threading.Lock()
app = Flask(__name__)
MODEL = None
NAMES = {}
NAME_TO_ID = {}
RESULTS = []


def safe_name(s: str) -> str:
    """Folder-safe tester name. Never trust a name typed on a phone as a path."""
    s = re.sub(r"[^A-Za-z0-9 _-]", "", (s or "").strip())[:40].strip()
    return re.sub(r"\s+", "_", s) or "anonymous"


def tester_dir(tester: str) -> Path:
    return STORE / safe_name(tester)


def load_results():
    if RESULTS_PATH.is_file():
        try:
            return json.loads(RESULTS_PATH.read_text())
        except json.JSONDecodeError:
            return []
    return []


def save_results():
    RESULTS_PATH.parent.mkdir(parents=True, exist_ok=True)
    RESULTS_PATH.write_text(json.dumps(RESULTS, indent=2))


def letterbox_square(img, size=640):
    h, w = img.shape[:2]
    s = max(h, w)
    canvas = np.full((s, s, 3), 114, dtype=np.uint8)
    canvas[(s - h) // 2:(s - h) // 2 + h, (s - w) // 2:(s - w) // 2 + w] = img
    return cv2.resize(canvas, (size, size), interpolation=cv2.INTER_AREA)


def run_model(img_bgr, conf, iou):
    with _lock:
        r = MODEL.predict(letterbox_square(img_bgr), conf=conf, iou=iou, verbose=False)[0]
        annotated = r.plot()
        dets = [{"cls": NAMES[int(c)], "conf": round(float(s), 3)}
                for c, s in zip(r.boxes.cls.tolist(), r.boxes.conf.tolist())]
    dets.sort(key=lambda d: -d["conf"])
    ok, buf = cv2.imencode(".jpg", annotated, [int(cv2.IMWRITE_JPEG_QUALITY), 82])
    return dets, (base64.b64encode(buf).decode() if ok else "")


def store_image(tester: str, img_bgr, raw_bytes=None, source="upload", orig_name=""):
    """Save under the tester's own folder; return the id used everywhere else."""
    digest = hashlib.md5(raw_bytes if raw_bytes is not None
                         else cv2.imencode(".jpg", img_bgr)[1].tobytes()).hexdigest()[:16]
    d = tester_dir(tester) / "images"
    d.mkdir(parents=True, exist_ok=True)
    p = d / f"{digest}.jpg"
    if not p.exists():
        cv2.imwrite(str(p), img_bgr)
    meta = tester_dir(tester) / "images" / f"{digest}.json"
    if not meta.exists():
        meta.write_text(json.dumps({"source": source, "original_name": orig_name,
                                    "at": dt.datetime.now().isoformat(timespec="seconds")}))
    return digest


def analyse(tester, img_bgr, conf, iou, raw=None, source="upload", orig_name=""):
    dets, annotated = run_model(img_bgr, conf, iou)
    img_id = store_image(tester, img_bgr, raw, source, orig_name)
    h, w = img_bgr.shape[:2]
    return {"id": img_id, "name": orig_name, "source": source,
            "width": int(w), "height": int(h),
            "detections": dets, "annotated": annotated,
            "top": dets[0]["cls"] if dets else None}


# ------------------------------------------------------------------------ api

@app.route("/api/classes")
def api_classes():
    return jsonify({"names": [NAMES[i] for i in sorted(NAMES)],
                    "ok_classes": sorted(OK_CLASSES)})


@app.route("/api/predict", methods=["POST"])
def api_predict():
    """One or many images. Folder upload arrives here as many files."""
    tester = request.form.get("tester", "")
    if not tester:
        return jsonify({"ok": False, "error": "no tester"}), 400
    conf = float(request.form.get("conf", 0.25))
    iou = float(request.form.get("iou", 0.45))
    files = request.files.getlist("images")
    if not files:
        return jsonify({"ok": False, "error": "no images"}), 400

    items, skipped = [], 0
    for f in files:
        if Path(f.filename or "").suffix.lower() not in IMG_EXTS:
            skipped += 1
            continue
        raw = f.read()
        img = cv2.imdecode(np.frombuffer(raw, np.uint8), cv2.IMREAD_COLOR)
        if img is None:
            skipped += 1
            continue
        items.append(analyse(tester, img, conf, iou, raw, "upload", f.filename or ""))
    return jsonify({"ok": True, "items": items, "skipped": skipped})


@app.route("/api/predict_video", methods=["POST"])
def api_predict_video():
    """Sample every Nth frame. Consecutive frames are near-identical, so decoding all
    of them would be slow and add nothing."""
    tester = request.form.get("tester", "")
    if not tester:
        return jsonify({"ok": False, "error": "no tester"}), 400
    f = request.files.get("video")
    if f is None:
        return jsonify({"ok": False, "error": "no video"}), 400
    conf = float(request.form.get("conf", 0.25))
    iou = float(request.form.get("iou", 0.45))
    every = max(1, int(request.form.get("every", 15)))
    max_frames = min(int(request.form.get("max_frames", 30)), 120)

    with tempfile.NamedTemporaryFile(delete=False,
                                     suffix=Path(f.filename or "v.mp4").suffix) as tf:
        tf.write(f.read())
        tmp = tf.name
    cap = cv2.VideoCapture(tmp)
    if not cap.isOpened():
        Path(tmp).unlink(missing_ok=True)
        return jsonify({"ok": False, "error": "could not open that video"}), 400
    fps = cap.get(cv2.CAP_PROP_FPS) or 25.0
    items, idx, taken = [], 0, 0
    while taken < max_frames:
        ok, frame = cap.read()
        if not ok:
            break
        if idx % every == 0:
            it = analyse(tester, frame, conf, iou, None, "video",
                         f"{Path(f.filename or 'clip').stem}_t{idx/fps:06.2f}s")
            items.append(it)
            taken += 1
        idx += 1
    cap.release()
    Path(tmp).unlink(missing_ok=True)
    return jsonify({"ok": True, "items": items, "fps": round(fps, 1), "sampled": taken})


@app.route("/api/verdict", methods=["POST"])
def api_verdict():
    b = request.get_json(force=True)
    if not b.get("tester"):
        return jsonify({"ok": False, "error": "who are you?"}), 400
    if b.get("verdict") not in ("correct", "wrong", "partial", "missed"):
        return jsonify({"ok": False, "error": "bad verdict"}), 400
    row = {
        "id": b.get("id"), "name": b.get("name"), "source": b.get("source"),
        "tester": safe_name(b["tester"]), "tester_raw": b["tester"][:40],
        "verdict": b["verdict"], "true_class": b.get("true_class") or None,
        "detections": b.get("detections", []), "top": b.get("top"),
        "conf_threshold": b.get("conf"), "note": (b.get("note") or "")[:300],
        "corrected_boxes": int(b.get("corrected_boxes") or 0),
        "at": dt.datetime.now().isoformat(timespec="seconds"),
    }
    with _lock:
        RESULTS.append(row)
        save_results()
    return jsonify({"ok": True, "total": len(RESULTS)})


@app.route("/api/annotate", methods=["POST"])
def api_annotate():
    """Save hand-drawn boxes as a YOLO label beside that tester's copy of the image.

    Written against the ORIGINAL image, not the letterboxed 640 one the model saw, so
    the label can be merged into the dataset without any further transformation.
    """
    b = request.get_json(force=True)
    tester, img_id = b.get("tester"), b.get("id")
    if not tester or not img_id:
        return jsonify({"ok": False, "error": "missing tester or id"}), 400
    lines = []
    for box in b.get("boxes", []):
        cname = box.get("cls")
        if cname not in NAME_TO_ID:
            return jsonify({"ok": False, "error": f"unknown class {cname}"}), 400
        cx, cy, w, h = (float(box["cx"]), float(box["cy"]),
                        float(box["w"]), float(box["h"]))
        cx, cy = min(max(cx, 0.0), 1.0), min(max(cy, 0.0), 1.0)
        w, h = min(max(w, 0.0), 1.0), min(max(h, 0.0), 1.0)
        if w <= 0.001 or h <= 0.001:
            continue
        lines.append(f"{NAME_TO_ID[cname]} {cx:.6f} {cy:.6f} {w:.6f} {h:.6f}")
    d = tester_dir(tester) / "labels"
    d.mkdir(parents=True, exist_ok=True)
    (d / f"{img_id}.txt").write_text("\n".join(lines) + ("\n" if lines else ""))
    return jsonify({"ok": True, "saved": len(lines)})


@app.route("/api/boxes/<tester>/<img_id>")
def api_boxes(tester, img_id):
    p = tester_dir(tester) / "labels" / f"{img_id}.txt"
    out = []
    if p.is_file():
        for line in p.read_text().splitlines():
            q = line.split()
            if len(q) >= 5:
                out.append({"cls": NAMES.get(int(q[0]), str(q[0])),
                            "cx": float(q[1]), "cy": float(q[2]),
                            "w": float(q[3]), "h": float(q[4])})
    return jsonify(out)


@app.route("/image/<tester>/<img_id>")
def image(tester, img_id):
    p = tester_dir(tester) / "images" / f"{img_id}.jpg"
    return send_file(p) if p.is_file() else ("", 404)


@app.route("/api/status")
def api_status():
    with _lock:
        rows = list(RESULTS)
    verdicts = Counter(r["verdict"] for r in rows)
    per_tester = defaultdict(lambda: Counter())
    per_class = defaultdict(lambda: Counter())
    per_source = Counter()
    confusion = defaultdict(Counter)
    for r in rows:
        per_tester[r.get("tester_raw") or r["tester"]][r["verdict"]] += 1
        per_source[r.get("source") or "?"] += 1
        tc = r.get("true_class")
        if not tc:
            continue
        per_class[tc][r["verdict"]] += 1
        if r["verdict"] in ("wrong", "partial") and r.get("top"):
            confusion[tc][r["top"]] += 1
        elif r["verdict"] == "missed":
            confusion[tc]["<nothing detected>"] += 1
    scored = sum(verdicts[k] for k in ("correct", "wrong", "partial", "missed"))
    corrections = sum(1 for r in rows if r.get("corrected_boxes"))
    return jsonify({
        "total": len(rows), "verdicts": dict(verdicts),
        "accuracy": round(verdicts["correct"] / scored, 3) if scored else None,
        "per_tester": {k: dict(v) for k, v in per_tester.items()},
        "per_class": {k: dict(v) for k, v in per_class.items()},
        "per_source": dict(per_source),
        "confusion": {k: dict(v) for k, v in confusion.items()},
        "corrected_images": corrections,
    })


@app.route("/api/export")
def api_export():
    with _lock:
        return jsonify(RESULTS)


# ------------------------------------------------------------------------- ui

PAGE = r"""<!doctype html><meta charset=utf-8>
<meta name=viewport content="width=device-width,initial-scale=1">
<title>Model test</title>
<style>
:root{color-scheme:dark}*{box-sizing:border-box}
body{background:#11131a;color:#e8eaf0;font-family:system-ui,-apple-system,sans-serif;
 margin:0;padding:14px;max-width:820px;margin-inline:auto}
h1{font-size:17px;margin:0 0 2px}.sub{color:#8f98ab;font-size:12px;margin-bottom:12px}
.card{background:#191c25;border:1px solid #2b3040;border-radius:10px;padding:13px;margin-bottom:12px}
button{background:#242936;color:#e8eaf0;border:1px solid #333a49;border-radius:8px;
 padding:11px 14px;font-size:14px;cursor:pointer;margin:3px 2px}
.big{display:block;width:100%;padding:14px;font-size:15px;font-weight:600}
.pri{background:#2d6cdf;border-color:#2d6cdf}.good{background:#1f7a44;border-color:#1f7a44}
.bad{background:#8b2b2b;border-color:#8b2b2b}.warn{background:#8a6a1f;border-color:#8a6a1f}
.mute{background:#3a3f4d;border-color:#3a3f4d}
input,select{background:#0f1117;color:#e8eaf0;border:1px solid #333a49;border-radius:8px;
 padding:11px;font-size:15px;width:100%}
img{width:100%;border-radius:8px;display:block;background:#000}
.row{display:grid;grid-template-columns:1fr 1fr;gap:8px}
.small{color:#8f98ab;font-size:12px}.lab{color:#8f98ab;font-size:11px;margin:9px 0 4px}
.det{background:#0f1117;border-radius:6px;padding:7px 9px;margin:4px 0;font-size:13px;
 display:flex;justify-content:space-between}
.pill{font-size:11px;padding:2px 7px;border-radius:20px;background:#2b3040}
.tabs{display:flex;gap:6px;margin-bottom:10px;flex-wrap:wrap}
.tabs button{flex:1;min-width:96px}
.tabs button.on{background:#2d6cdf;border-color:#2d6cdf}
/* The canvas MUST overlay the photo. This selector used to read #cv, which is the
   confidence-threshold <span> - so the canvas was never positioned and rendered
   BELOW the image, making the whole annotator dead to clicks. */
#stage{position:relative;display:block;width:100%;line-height:0}
#stage img{display:block;width:100%}
#cv2{position:absolute;left:0;top:0;cursor:crosshair;touch-action:none;z-index:2}
.chip{display:inline-block;padding:4px 9px;margin:2px;border-radius:6px;background:#242936;
 border:1px solid #333a49;font-size:12px;cursor:pointer}
.chip.on{background:#2d6cdf;border-color:#2d6cdf}
a{color:#7ab0ff}
.bar{height:6px;background:#242936;border-radius:3px;overflow:hidden;margin:8px 0}
.bar>div{height:100%;background:#3ba55d;width:0}
</style>

<div id=who class=card>
  <h1>Who is testing?</h1>
  <div class=sub>Your photos and corrections are filed under this name.</div>
  <input id=name placeholder="your name" autocomplete=off>
  <button class="big pri" onclick=setName()>Start testing</button>
</div>

<div id=app style=display:none>
  <h1>🛣️ Model test <span class=small id=meWho></span></h1>
  <div class=sub>Feed it photos, say if it was right, fix it when it is wrong.
    <a href="/stats" target=_blank>live results →</a>
    &nbsp;<a href="#" onclick="logout();return false">switch person</a></div>

  <div class=card>
    <div class=tabs>
      <button id=t_cam class=on onclick="mode('cam')">📷 Camera</button>
      <button id=t_img onclick="mode('img')">🖼️ Images</button>
      <button id=t_dir onclick="mode('dir')">📁 Folder</button>
      <button id=t_vid onclick="mode('vid')">🎬 Video</button>
    </div>
    <input id=f_cam type=file accept="image/*" capture="environment" style=display:none onchange="up(this.files,'img')">
    <input id=f_img type=file accept="image/*" multiple style=display:none onchange="up(this.files,'img')">
    <input id=f_dir type=file webkitdirectory directory multiple style=display:none onchange="up(this.files,'img')">
    <input id=f_vid type=file accept="video/*" style=display:none onchange="up(this.files,'vid')">
    <button class="big pri" id=pick onclick=pickFile()>📷 Take a photo</button>
    <div id=vidopts style=display:none>
      <div class=lab>Analyse every Nth frame <span id=ev>15</span></div>
      <input id=every type=range min=1 max=60 value=15 oninput="ev.textContent=this.value">
    </div>
    <div class=lab>Confidence threshold <span id=cvval>0.25</span>
      <span class=small>(the phone app uses 0.40)</span></div>
    <input id=conf type=range min=5 max=90 value=25
           oninput="cvval.textContent=(this.value/100).toFixed(2)">
  </div>

  <div id=busy class=card style=display:none>Running the detector…<div class=bar><div id=bfill></div></div></div>

  <div id=res style=display:none>
    <div class=card>
      <div class=lab><span id=qpos></span> <span id=fname class=small></span></div>
      <div class=row>
        <div><img id=orig><div class="small" style=text-align:center>original</div></div>
        <div><img id=ann><div class="small" style=text-align:center>detected</div></div>
      </div>
      <div id=dets></div>
    </div>

    <div class=card id=vpanel>
      <div class=lab>Was it right?</div>
      <button class="big good" onclick="verdict('correct')">✓ Correct</button>
      <button class="big warn" onclick="verdict('partial')">~ Partly right</button>
      <button class="big bad" onclick="verdict('wrong')">✗ Wrong class</button>
      <button class="big mute" onclick="verdict('missed')">∅ Missed it entirely</button>
      <div class=lab>What was actually in the photo?</div>
      <select id=truth><option value="">— not sure / skip —</option></select>
      <div class=lab>Note (optional)</div>
      <input id=note placeholder="e.g. cover was intact, called it broken">
      <button class=mute style="width:100%;margin-top:8px" onclick=skip()>Skip this one →</button>
    </div>

    <div class=card id=apanel style=display:none>
      <div class=lab><b>Draw the correct boxes.</b> Drag on the photo. Tap a box to select,
        then Delete. These are saved as real YOLO labels under your name.</div>
      <div id=stage><img id=aimg><canvas id=cv2></canvas></div>
      <div class=lab>Class for the next / selected box</div>
      <div id=classes></div>
      <div id=blist class=small style=margin-top:6px></div>
      <button class="big good" onclick=saveBoxes()>Save boxes + next</button>
      <button class=mute style=width:100% onclick=skipAnn()>No boxes needed — just record it wrong</button>
    </div>
  </div>
  <div class=card><span class=small id=mine>nothing submitted yet</span></div>
</div>

<script>
let TESTER=localStorage.getItem('tester')||'',Q=[],QI=0,CUR=null,MINE=0,MODE='cam',
    CLASSES=[],curCls=null,boxes=[],sel=-1,drag=null,PENDING=null;
const $=id=>document.getElementById(id);

function setName(){const v=$('name').value.trim(); if(!v)return;
  localStorage.setItem('tester',v);TESTER=v;boot()}
function logout(){localStorage.removeItem('tester');location.reload()}
function boot(){
  if(!TESTER){$('who').style.display='';return}
  $('who').style.display='none';$('app').style.display='';
  $('meWho').textContent='— '+TESTER;
  fetch('/api/classes').then(r=>r.json()).then(d=>{
    CLASSES=d.names;curCls=CLASSES[0];
    const s=$('truth');
    CLASSES.forEach(n=>{const o=document.createElement('option');o.value=n;o.textContent=n;s.appendChild(o)});
    const o=document.createElement('option');o.value='__none__';
    o.textContent='nothing of interest was in the photo';s.appendChild(o);
    $('classes').innerHTML=CLASSES.map(n=>`<span class=chip data-c="${n}" onclick="pick('${n}')">${n}</span>`).join('');
    pick(CLASSES[0]);
  });
}
function mode(m){MODE=m;['cam','img','dir','vid'].forEach(k=>$('t_'+k).classList.toggle('on',k===m));
  $('pick').textContent={cam:'📷 Take a photo',img:'🖼️ Choose image(s)',
    dir:'📁 Choose a folder',vid:'🎬 Choose a video'}[m];
  $('vidopts').style.display = m==='vid'?'':'none'}
function pickFile(){$({cam:'f_cam',img:'f_img',dir:'f_dir',vid:'f_vid'}[MODE]).click()}

async function up(files,kind){
  if(!files||!files.length)return;
  $('res').style.display='none';$('busy').style.display='';$('bfill').style.width='10%';
  const fd=new FormData();
  fd.append('tester',TESTER);
  fd.append('conf',($('conf').value/100).toFixed(2));
  let url='/api/predict';
  if(kind==='vid'){url='/api/predict_video';fd.append('video',files[0]);
    fd.append('every',$('every').value)}
  else{[...files].forEach(f=>fd.append('images',f))}
  $('bfill').style.width='45%';
  let r;
  try{r=await(await fetch(url,{method:'POST',body:fd})).json()}
  catch(e){$('busy').style.display='none';alert('upload failed: '+e);return}
  $('busy').style.display='none';
  if(!r.ok){alert(r.error||'failed');return}
  Q=r.items;QI=0;
  if(!Q.length){alert('No usable images found.');return}
  show();
}
function show(){
  if(QI>=Q.length){$('res').style.display='none';
    $('mine').textContent=MINE+' judged by you — queue finished. Load more above.';return}
  CUR=Q[QI];boxes=[];sel=-1;
  $('qpos').textContent=`${QI+1} of ${Q.length}`;
  $('fname').textContent=CUR.name||'';
  $('orig').src=`/image/${encodeURIComponent(TESTER)}/${CUR.id}`;
  $('ann').src='data:image/jpeg;base64,'+CUR.annotated;
  $('dets').innerHTML=CUR.detections.length
    ? CUR.detections.map(d=>`<div class=det><b>${d.cls}</b><span class=pill>${d.conf}</span></div>`).join('')
    : '<div class=det>nothing detected above the threshold</div>';
  $('truth').value='';$('note').value='';
  $('vpanel').style.display='';$('apanel').style.display='none';
  $('res').style.display='';
  window.scrollTo({top:$('res').offsetTop-10,behavior:'smooth'});
}
async function verdict(v){
  if(!CUR)return;
  PENDING={id:CUR.id,name:CUR.name,source:CUR.source,tester:TESTER,verdict:v,
    detections:CUR.detections,top:CUR.top,true_class:$('truth').value,
    note:$('note').value,conf:($('conf').value/100).toFixed(2),corrected_boxes:0};
  if(v==='correct'){await commit();return}
  // wrong / partial / missed -> offer to draw the right boxes
  $('vpanel').style.display='none';$('apanel').style.display='';
  const im=$('aimg');
  im.onload=sizeCanvas;
  im.src=`/image/${encodeURIComponent(TESTER)}/${CUR.id}`;
  // A cached image fires no load event, and clientWidth is 0 until the panel has
  // actually been laid out - size on the next frame as well, or the canvas ends up
  // 0x0 and every drag silently does nothing.
  if(im.complete) requestAnimationFrame(sizeCanvas);
  if($('truth').value && $('truth').value!=='__none__') pick($('truth').value);
  window.scrollTo({top:$('apanel').offsetTop-10,behavior:'smooth'});
}
async function commit(){
  const r=await(await fetch('/api/verdict',{method:'POST',
    headers:{'Content-Type':'application/json'},body:JSON.stringify(PENDING)})).json();
  if(!r.ok){alert(r.error);return}
  MINE++;$('mine').textContent=`${MINE} judged by you · ${r.total} in total`;
  PENDING=null;QI++;show();
}
function skip(){QI++;show()}
function skipAnn(){commit()}
async function saveBoxes(){
  const c=$('cv2');
  const payload=boxes.map(b=>({cls:b.cls,cx:(b.x+b.w/2)/c.width,cy:(b.y+b.h/2)/c.height,
    w:b.w/c.width,h:b.h/c.height}));
  const r=await(await fetch('/api/annotate',{method:'POST',
    headers:{'Content-Type':'application/json'},
    body:JSON.stringify({tester:TESTER,id:CUR.id,boxes:payload})})).json();
  if(!r.ok){alert(r.error);return}
  PENDING.corrected_boxes=r.saved;
  await commit();
}
function sizeCanvas(){
  const im=$('aimg'),c=$('cv2');
  if(!im.clientWidth){requestAnimationFrame(sizeCanvas);return}
  // Rescale any boxes already drawn, so rotating the phone does not misplace them.
  const ow=c.width||im.clientWidth, oh=c.height||im.clientHeight;
  const sx=im.clientWidth/ow, sy=im.clientHeight/oh;
  if(ow&&oh&&(sx!==1||sy!==1))
    boxes.forEach(b=>{b.x*=sx;b.y*=sy;b.w*=sx;b.h*=sy});
  c.width=im.clientWidth;c.height=im.clientHeight;
  draw();list();
}
window.addEventListener('resize',()=>{if($('apanel').style.display!=='none')sizeCanvas()});
function pick(n){curCls=n;
  document.querySelectorAll('#classes .chip').forEach(e=>e.classList.toggle('on',e.dataset.c===n));
  if(sel>=0){boxes[sel].cls=n;draw();list()}}
function draw(){const c=$('cv2'),x=c.getContext('2d');x.clearRect(0,0,c.width,c.height);
  boxes.forEach((b,i)=>{x.lineWidth=i===sel?3:2;x.strokeStyle=i===sel?'#ffd54a':'#3ba55d';
    x.strokeRect(b.x,b.y,b.w,b.h);x.fillStyle=x.strokeStyle;x.font='12px system-ui';
    x.fillText(b.cls,b.x+3,Math.max(12,b.y-4))});
  if(drag){x.setLineDash([5,4]);x.strokeStyle='#2d6cdf';
    x.strokeRect(drag.x,drag.y,drag.w,drag.h);x.setLineDash([])}}
function list(){$('blist').innerHTML=boxes.length
  ? boxes.map((b,i)=>`<div class=det><span>${i+1}. ${b.cls}</span>
      <span class=pill onclick="sel=${i};pick('${b.cls}');draw();list()">select</span></div>`).join('')
  : 'no boxes drawn yet'}
function pos(e){const c=$('cv2'),r=c.getBoundingClientRect();
  const t=e.touches?e.touches[0]:e;return[t.clientX-r.left,t.clientY-r.top]}
function down(e){const [x,y]=pos(e);
  const hit=boxes.findIndex(b=>x>=b.x&&x<=b.x+b.w&&y>=b.y&&y<=b.y+b.h);
  if(hit>=0){sel=hit;pick(boxes[hit].cls);draw();list();return}
  drag={x0:x,y0:y,x:x,y:y,w:0,h:0};e.preventDefault()}
function move(e){if(!drag)return;const [x,y]=pos(e);
  drag.x=Math.min(x,drag.x0);drag.y=Math.min(y,drag.y0);
  drag.w=Math.abs(x-drag.x0);drag.h=Math.abs(y-drag.y0);draw();e.preventDefault()}
function upE(){if(drag&&drag.w>6&&drag.h>6){
    boxes.push({cls:curCls,x:drag.x,y:drag.y,w:drag.w,h:drag.h});
    // Deselect. If the new box stayed selected, picking a class for the NEXT box
    // would silently relabel the one just drawn - draw a dog, choose "cat" for the
    // second box, and the dog box quietly became a cat. Tap a box to select it when
    // you actually want to change its class.
    sel=-1}
  drag=null;draw();list()}
window.addEventListener('load',()=>{const c=$('cv2');
  c.addEventListener('mousedown',down);c.addEventListener('mousemove',move);
  window.addEventListener('mouseup',upE);
  c.addEventListener('touchstart',down,{passive:false});
  c.addEventListener('touchmove',move,{passive:false});
  window.addEventListener('touchend',upE);});
window.addEventListener('keydown',e=>{
  if(/^(INPUT|TEXTAREA|SELECT)$/.test(document.activeElement.tagName))return;
  if(e.key==='Delete'||e.key==='Backspace'){
    if(sel>=0)boxes.splice(sel,1);else boxes.pop();sel=-1;draw();list();e.preventDefault()}});
boot();
</script>"""


STATS = r"""<!doctype html><meta charset=utf-8>
<meta name=viewport content="width=device-width,initial-scale=1">
<title>Model test results</title><meta http-equiv=refresh content=300>
<style>body{background:#11131a;color:#e8eaf0;font-family:system-ui,sans-serif;padding:18px;
max-width:940px;margin-inline:auto}h2{font-size:18px}h3{font-size:13px;color:#8f98ab;
text-transform:uppercase;letter-spacing:.04em;margin:22px 0 6px}
table{border-collapse:collapse;width:100%}td,th{padding:6px 10px;border-bottom:1px solid #262b38;
text-align:left;font-size:13px}th{color:#8f98ab;font-weight:500;font-size:11px}
.big{font-size:36px;font-weight:700}.small{color:#8f98ab;font-size:12px}
.n{font-variant-numeric:tabular-nums}</style>
<h2>Model test results</h2><div id=o class=small>loading…</div>
<script>
async function tick(){const s=await(await fetch('/api/status')).json();
if(!s.total){document.getElementById('o').innerHTML='No verdicts submitted yet.';return}
const v=s.verdicts||{};
let h=`<div class=big>${s.accuracy!==null?(s.accuracy*100).toFixed(0)+'%':'—'}</div>
<div class=small>correct, over ${s.total} judged photos · ${s.corrected_images||0} hand-corrected</div>
<h3>Verdicts</h3><table><tr><th>verdict<th>count</tr>`;
for(const k of ['correct','partial','wrong','missed'])if(v[k])h+=`<tr><td>${k}<td class=n>${v[k]}</tr>`;
h+='</table><h3>By what was actually in the photo</h3><table><tr><th>true class<th>correct<th>partial<th>wrong<th>missed</tr>';
for(const[k,c]of Object.entries(s.per_class).sort())
 h+=`<tr><td>${k}<td class=n>${c.correct||0}<td class=n>${c.partial||0}<td class=n>${c.wrong||0}<td class=n>${c.missed||0}</tr>`;
h+='</table><h3>What it said instead</h3><table><tr><th>actually was<th>model said</tr>';
for(const[k,c]of Object.entries(s.confusion).sort()){
 const it=Object.entries(c).sort((a,b)=>b[1]-a[1]).map(([n,x])=>`${n} ×${x}`).join(', ');
 h+=`<tr><td>${k}<td>${it}</tr>`}
h+='</table><h3>Testers</h3><table><tr><th>person<th>correct<th>partial<th>wrong<th>missed<th>total</tr>';
for(const[k,c]of Object.entries(s.per_tester)){
 const t=(c.correct||0)+(c.partial||0)+(c.wrong||0)+(c.missed||0);
 h+=`<tr><td>${k}<td class=n>${c.correct||0}<td class=n>${c.partial||0}<td class=n>${c.wrong||0}<td class=n>${c.missed||0}<td class=n>${t}</tr>`}
h+='</table><h3>Input source</h3><table>';
for(const[k,c]of Object.entries(s.per_source||{}))h+=`<tr><td>${k}<td class=n>${c}</tr>`;
h+='</table><p class=small><a href="/api/export">download all results as JSON</a></p>';
document.getElementById('o').innerHTML=h}
tick();setInterval(tick,4000);
</script>"""


@app.route("/")
def index():
    return PAGE


@app.route("/stats")
def stats():
    return STATS


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", type=int, default=5080)
    ap.add_argument("--weights", default=str(DEFAULT_WEIGHTS))
    args = ap.parse_args()

    global MODEL, NAMES, NAME_TO_ID, RESULTS
    from ultralytics import YOLO
    print(f"Loading {args.weights} …")
    MODEL = YOLO(args.weights)
    NAMES = MODEL.names
    NAME_TO_ID = {v: k for k, v in NAMES.items()}
    RESULTS = load_results()
    STORE.mkdir(parents=True, exist_ok=True)

    print(f"{len(NAMES)} classes · {len(RESULTS)} verdicts already recorded")
    print(f"Per-tester photos/labels under {STORE}/<name>/")

    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(("8.8.8.8", 80))
        lan = s.getsockname()[0]
    except Exception:
        lan = "127.0.0.1"
    finally:
        s.close()
    print(f"\n  Share with testers : http://{lan}:{args.port}")
    print(f"  Live results       : http://{lan}:{args.port}/stats")
    print(f"  On this machine    : http://127.0.0.1:{args.port}\n")
    print("  Everyone must be on the same WiFi. Ctrl+C to stop.\n")
    app.run(host="0.0.0.0", port=args.port, debug=False, threaded=True)


if __name__ == "__main__":
    main()
