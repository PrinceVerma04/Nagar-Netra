"""
Resolve-the-7-unresolved-cattle-images dashboard.

These 7 images (from data/classwise _data/cattle/) came back UNRESOLVED from
a visual species audit -- either because a box's species was genuinely
unclear (blur/darkness/no distinguishing features), or because the image has
MULTIPLE boxes belonging to DIFFERENT species (e.g. 2 cow boxes + 1 buffalo
box in the same photo). Because of that second case, this is a PER-BOX
classification tool, not per-image: each box gets its own species
assignment, independent of the others in the same picture.

Targets: cow, buffalo, camel, cat, dog, goat, horse. You can also draw a new
box (for a visible animal with no box yet) and delete a box entirely (junk /
not one of these 7 species / duplicate box).

This dashboard only records your decisions -- it does NOT move any files or
touch classwise_data / re-training_data. Saved as:
    data/classwise _data/cattle/unresolved_species_resolution.json
Once every image is resolved, run the move step: split
each box out to its assigned class's folder+label, verified, then check
whether cattle/ can finally be emptied.

Usage:
    python resolve_cattle_unresolved.py
    -> http://127.0.0.1:5062

Keyboard controls (while an image is open):
    Mouse drag        draw a new box
    Click a box       select it, then press a class key to assign it:
                       1 cow  2 buffalo  3 camel  4 cat  5 dog  6 goat  7 horse
    Delete/Backspace  delete selected box (or last box if none selected)
    S / Enter         save this image's assignments & go to next
                       (every box must be assigned a class first)
    N                 next (no save)
    P                 previous
"""
import functools
import json
import socket
import threading

print = functools.partial(print, flush=True)
from io import BytesIO
from pathlib import Path

from flask import Flask, jsonify, request, send_file, Response
from PIL import Image, ImageDraw, ImageFont

BASE = Path(__file__).resolve().parent
CATTLE = BASE / "data" / "classwise _data" / "cattle"
RESULT_PATH = CATTLE / "unresolved_species_resolution.json"
IMG_EXTS = (".jpg", ".jpeg", ".png")

CLASSES = ["cow", "buffalo", "camel", "cat", "dog", "goat", "horse"]

# the 7 unresolved images: (split, filename)
UNRESOLVED = [
    ("train", "Screenshot 2026-09-04 103205.png"),
    ("train", "Screenshot 2026-09-04 103235.png"),
    ("train", "Screenshot 2026-09-04 103245.png"),
    ("train", "dats2022_171.jpg"),
    ("train", "iddos9ak_0003329_jpg.rf.2eab962ef2ffea5f55aca0905e51fcc0.jpg"),
    ("train", "irc_IMG_20211228_122311_jpg.rf.9262f5000998f1d47684df1224c1bc60.jpg"),
    ("val", "iddos9ak_0008161_jpg.rf.12e7ba4dca15b07918a981f900b65e2d.jpg"),
]

app = Flask(__name__)
_lock = threading.Lock()


def _load_results():
    if RESULT_PATH.exists():
        return json.loads(RESULT_PATH.read_text())
    return {}


def _save_results():
    RESULT_PATH.write_text(json.dumps(RESULTS, indent=2))


RESULTS = _load_results()  # stem -> {"boxes": [{cx,cy,w,h,cls}], "split": ...}


class Item:
    __slots__ = ("stem", "split", "img", "lbl")

    def __init__(self, split, filename):
        self.split = split
        self.stem = Path(filename).stem
        self.img = CATTLE / split / "images" / filename
        self.lbl = CATTLE / split / "labels" / f"{self.stem}.txt"


ITEMS = [Item(split, fn) for split, fn in UNRESOLVED]
print(f"Resolving {len(ITEMS)} unresolved cattle images ({sum(1 for i in ITEMS if i.stem in RESULTS)} already saved)")


def find_item(stem):
    for it in ITEMS:
        if it.stem == stem:
            return it
    return None


def render_placeholder(text, size=(640, 480)):
    img = Image.new("RGB", size, (30, 20, 20))
    draw = ImageDraw.Draw(img)
    try:
        font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 22)
    except Exception:
        font = ImageFont.load_default()
    draw.text((size[0] // 2, size[1] // 2), text, fill=(224, 87, 79), font=font, anchor="mm")
    buf = BytesIO()
    img.save(buf, format="JPEG", quality=88)
    buf.seek(0)
    return buf


@app.route("/")
def index():
    return Response(INDEX_HTML, mimetype="text/html")


@app.route("/api/status")
def api_status():
    reviewed = sum(1 for it in ITEMS if it.stem in RESULTS)
    return jsonify({"total": len(ITEMS), "reviewed": reviewed, "pending": len(ITEMS) - reviewed, "classes": CLASSES})


@app.route("/api/images")
def api_images():
    return jsonify([{"stem": it.stem, "split": it.split, "reviewed": it.stem in RESULTS} for it in ITEMS])


@app.route("/api/boxes/<stem>")
def api_boxes(stem):
    it = find_item(stem)
    if it is None:
        return jsonify({"boxes": []})
    # if already resolved once, reload the saved per-box classes so it's editable
    if stem in RESULTS:
        return jsonify({"boxes": RESULTS[stem]["boxes"]})
    boxes = []
    if it.lbl.exists():
        for line in it.lbl.read_text().splitlines():
            parts = line.split()
            if len(parts) < 5:
                continue
            cx, cy, w, h = (float(x) for x in parts[1:5])
            boxes.append({"cx": cx, "cy": cy, "w": w, "h": h, "cls": None})
    return jsonify({"boxes": boxes})


@app.route("/image/<path:stem>")
def api_image(stem):
    it = find_item(stem)
    if it is None:
        return render_placeholder("NOT FOUND"), 404
    try:
        with Image.open(it.img) as im:
            im.verify()
        return send_file(str(it.img))
    except Exception:
        return send_file(render_placeholder(f"CORRUPT FILE\n{it.img.name}"), mimetype="image/jpeg")


@app.route("/api/save", methods=["POST"])
def api_save():
    body = request.get_json(force=True)
    stem, boxes = body["stem"], body["boxes"]
    it = find_item(stem)
    if it is None:
        return jsonify({"error": "not found"}), 404
    for b in boxes:
        if b.get("cls") not in CLASSES:
            return jsonify({"error": f"box missing a valid class assignment: {b}"}), 400
    with _lock:
        RESULTS[stem] = {"split": it.split, "boxes": boxes}
        _save_results()
    print(f"[RESOLVED] {stem} -> {len(boxes)} box(es): {[b['cls'] for b in boxes]}")
    return jsonify({"ok": True})


INDEX_HTML = r"""<!doctype html>
<html>
<head>
<meta charset="utf-8">
<title>Resolve Unclear Cattle</title>
<style>
  :root {
    --bg: #101216; --surface: #191c22; --ink: #eef0f3; --ink2: #b3b8c2; --muted: #7d828c;
    --hair: rgba(255,255,255,0.10); --accent: #5b9eee; --good: #2fbf5f; --bad: #e0574f; --warn: #e0a83f;
  }
  * { box-sizing: border-box; }
  body { margin: 0; background: var(--bg); color: var(--ink); font-family: system-ui, -apple-system, "Segoe UI", sans-serif; }
  .layout { display: flex; height: 100vh; }
  .sidebar { width: 260px; flex-shrink: 0; border-right: 1px solid var(--hair); padding: 16px 10px; overflow-y: auto; }
  .sidebar h1 { font-size: 13px; text-transform: uppercase; letter-spacing: 0.06em; color: var(--muted); padding: 0 8px; margin: 0 0 4px; }
  .sidebar .sub { font-size: 11px; color: var(--muted); padding: 0 8px; margin-bottom: 14px; line-height: 1.5; }
  .stat-box { padding: 10px 12px; margin: 0 8px 14px; border: 1px solid var(--hair); border-radius: 8px; font-size: 12px; }
  .stat-box .row { display: flex; justify-content: space-between; margin-bottom: 4px; }
  .stat-box .ok { color: var(--good); font-weight: 600; }
  .img-row { padding: 8px 10px; border-radius: 6px; cursor: pointer; font-size: 11.5px; margin-bottom: 2px; font-family: ui-monospace, monospace; color: var(--ink2); }
  .img-row:hover { background: rgba(255,255,255,0.05); }
  .img-row.active { background: var(--accent); color: #08131f; font-weight: 600; }
  .img-row.done::after { content: " ✓"; color: var(--good); }
  .class-legend { padding: 10px; margin: 8px; border: 1px solid var(--hair); border-radius: 8px; font-size: 11px; line-height: 1.9; }
  .class-legend .k { display: inline-block; width: 16px; color: var(--accent); font-weight: 700; }

  .main { flex: 1; display: flex; flex-direction: column; align-items: center; padding: 20px 24px; overflow-y: auto; }
  .topbar { width: 100%; max-width: 920px; display: flex; justify-content: space-between; align-items: baseline; margin-bottom: 10px; }
  .topbar h2 { font-size: 16px; margin: 0; }
  .canvas-wrap { position: relative; width: 100%; max-width: 920px; background: #000; border: 1px solid var(--hair); border-radius: 10px; overflow: hidden; line-height: 0; }
  .canvas-wrap img { width: 100%; display: block; max-height: 68vh; object-fit: contain; }
  .canvas-wrap canvas { position: absolute; top: 0; left: 0; cursor: crosshair; }

  .box-list { width: 100%; max-width: 920px; margin-top: 12px; }
  .box-item { display: flex; align-items: center; gap: 10px; padding: 8px 10px; border: 1px solid var(--hair); border-radius: 8px; margin-bottom: 6px; font-size: 12px; }
  .box-item.selected { border-color: var(--accent); }
  .box-item .idx { font-family: ui-monospace, monospace; color: var(--muted); width: 20px; }
  .box-item .cls-tag { padding: 2px 10px; border-radius: 10px; font-weight: 700; font-size: 11px; }
  .box-item .cls-tag.unset { background: rgba(224,87,79,0.15); color: var(--bad); }
  .box-item .cls-tag.set { background: rgba(47,191,95,0.18); color: var(--good); }
  .box-item .del { margin-left: auto; color: var(--bad); cursor: pointer; font-size: 11px; }
  .class-btns { display: flex; gap: 4px; flex-wrap: wrap; }
  .class-btns button { font-size: 10.5px; padding: 3px 8px; border-radius: 5px; border: 1px solid var(--hair); background: var(--surface); color: var(--ink2); cursor: pointer; }
  .class-btns button:hover { border-color: var(--accent); color: var(--ink); }
  .class-btns button.active { background: var(--accent); color: #08131f; font-weight: 700; }

  .controls { display: flex; gap: 10px; margin-top: 14px; flex-wrap: wrap; justify-content: center; }
  .btn { padding: 11px 22px; border-radius: 8px; border: 1px solid var(--hair); background: var(--surface); color: var(--ink); font-size: 13.5px; font-weight: 600; cursor: pointer; }
  .btn:hover { border-color: var(--accent); }
  .btn.save { color: var(--good); }
  .btn kbd { background: rgba(255,255,255,0.08); border-radius: 4px; padding: 1px 6px; font-family: ui-monospace, monospace; font-size: 11px; }
  .btn:disabled { opacity: 0.4; cursor: not-allowed; }
  .warn-text { font-size: 11px; color: var(--warn); margin-top: 8px; text-align: center; }
  .done-state { text-align: center; padding: 60px 20px; color: var(--muted); }
</style>
</head>
<body>
<div class="layout">
  <div class="sidebar">
    <h1>Resolve Unclear Cattle</h1>
    <div class="sub">Click a box, then click its species below (or press its number key). Draw a new box for anything missing an annotation. Every box needs a class before you can save.</div>
    <div class="stat-box" id="global-stats"></div>
    <div id="image-list"></div>
    <div class="class-legend" id="legend"></div>
  </div>
  <div class="main">
    <div class="topbar">
      <h2 id="title">&mdash;</h2>
    </div>
    <div id="stage-wrap"></div>
    <div class="box-list" id="box-list"></div>
    <div class="controls" id="controls" style="display:none">
      <button class="btn save" id="btn-save">Save & Next <kbd>S</kbd></button>
    </div>
    <div class="warn-text" id="warn-text"></div>
  </div>
</div>

<script>
const CLASS_KEYS = {"1":"cow","2":"buffalo","3":"camel","4":"cat","5":"dog","6":"goat","7":"horse"};
let CLASSES = [];
let images = [];
let idx = 0;
let boxes = [];  // {x1,y1,x2,y2,cls}
let selectedBox = -1;
let drawing = false, startX = 0, startY = 0;

async function loadStatus() {
  const res = await fetch("/api/status");
  const s = await res.json();
  CLASSES = s.classes;
  document.getElementById("global-stats").innerHTML = `
    <div class="row"><span>Resolved</span><span class="ok">${s.reviewed}/${s.total}</span></div>`;
  document.getElementById("legend").innerHTML = Object.entries(CLASS_KEYS)
    .map(([k,v]) => `<div><span class="k">${k}</span>${v}</div>`).join("");
}

async function loadImages() {
  const res = await fetch("/api/images");
  images = await res.json();
  renderList();
  await renderStage();
}

function renderList() {
  const el = document.getElementById("image-list");
  el.innerHTML = "";
  images.forEach((im, i) => {
    const row = document.createElement("div");
    row.className = "img-row" + (i === idx ? " active" : "") + (im.reviewed ? " done" : "");
    row.textContent = im.stem.length > 28 ? im.stem.slice(0,28) + "…" : im.stem;
    row.onclick = () => { idx = i; renderStage(); renderList(); };
    el.appendChild(row);
  });
}

async function renderStage() {
  boxes = []; selectedBox = -1;
  if (idx >= images.length) {
    document.getElementById("stage-wrap").innerHTML = `<div class="done-state">All 7 resolved. Run the move step.</div>`;
    document.getElementById("box-list").innerHTML = "";
    document.getElementById("controls").style.display = "none";
    return;
  }
  const im = images[idx];
  document.getElementById("title").textContent = `${im.split}/${im.stem}`;
  const wrap = document.getElementById("stage-wrap");
  wrap.innerHTML = `
    <div class="canvas-wrap" id="canvas-wrap">
      <img id="stage-img" src="/image/${encodeURIComponent(im.stem)}?t=${Date.now()}">
      <canvas id="stage-canvas"></canvas>
    </div>`;
  const img = document.getElementById("stage-img");
  const canvas = document.getElementById("stage-canvas");

  const setupCanvas = async () => {
    canvas.width = img.clientWidth;
    canvas.height = img.clientHeight;
    canvas.style.width = img.clientWidth + "px";
    canvas.style.height = img.clientHeight + "px";
    const bres = await fetch(`/api/boxes/${encodeURIComponent(im.stem)}`);
    const bdata = await bres.json();
    boxes = (bdata.boxes || []).map(b => ({
      x1: (b.cx-b.w/2)*canvas.width, y1: (b.cy-b.h/2)*canvas.height,
      x2: (b.cx+b.w/2)*canvas.width, y2: (b.cy+b.h/2)*canvas.height,
      cls: b.cls || null,
    }));
    drawBoxes();
    renderBoxList();
    attachCanvasHandlers(canvas);
  };
  if (img.complete) setupCanvas(); else img.onload = setupCanvas;
  document.getElementById("controls").style.display = "flex";
}

function drawBoxes() {
  const canvas = document.getElementById("stage-canvas");
  if (!canvas) return;
  const ctx = canvas.getContext("2d");
  ctx.clearRect(0, 0, canvas.width, canvas.height);
  boxes.forEach((b, i) => {
    ctx.strokeStyle = i === selectedBox ? "#e0a83f" : (b.cls ? "#2fbf5f" : "#e0574f");
    ctx.lineWidth = i === selectedBox ? 3 : 2;
    const x = Math.min(b.x1,b.x2), y = Math.min(b.y1,b.y2), w = Math.abs(b.x2-b.x1), h = Math.abs(b.y2-b.y1);
    ctx.strokeRect(x, y, w, h);
    if (b.cls) {
      ctx.fillStyle = "#2fbf5f"; ctx.font = "12px monospace";
      ctx.fillText(b.cls, x + 3, y + 14);
    }
  });
}

function renderBoxList() {
  const el = document.getElementById("box-list");
  el.innerHTML = "";
  boxes.forEach((b, i) => {
    const row = document.createElement("div");
    row.className = "box-item" + (i === selectedBox ? " selected" : "");
    const tag = b.cls ? `<span class="cls-tag set">${b.cls}</span>` : `<span class="cls-tag unset">unassigned</span>`;
    const btns = CLASSES.map(c => `<button data-i="${i}" data-c="${c}" class="${b.cls===c?'active':''}">${c}</button>`).join("");
    row.innerHTML = `<span class="idx">#${i+1}</span>${tag}<div class="class-btns">${btns}</div><span class="del" data-i="${i}">delete</span>`;
    row.onclick = (e) => {
      if (e.target.tagName === "BUTTON") {
        boxes[i].cls = e.target.dataset.c;
        drawBoxes(); renderBoxList(); updateWarn();
        return;
      }
      if (e.target.classList.contains("del")) {
        boxes.splice(i, 1); selectedBox = -1;
        drawBoxes(); renderBoxList(); updateWarn();
        return;
      }
      selectedBox = i; drawBoxes(); renderBoxList();
    };
    el.appendChild(row);
  });
  updateWarn();
}

function updateWarn() {
  const unassigned = boxes.filter(b => !b.cls).length;
  const warn = document.getElementById("warn-text");
  const saveBtn = document.getElementById("btn-save");
  if (unassigned > 0) {
    warn.textContent = `${unassigned} box(es) still need a class assigned before you can save.`;
    saveBtn.disabled = true;
  } else {
    warn.textContent = boxes.length ? "" : "No boxes on this image — draw one if an animal is visible, or save with 0 boxes if not.";
    saveBtn.disabled = false;
  }
}

function attachCanvasHandlers(canvas) {
  canvas.onmousedown = (e) => {
    const rect = canvas.getBoundingClientRect();
    const x = e.clientX - rect.left, y = e.clientY - rect.top;
    const hit = boxes.findIndex(b => x >= Math.min(b.x1,b.x2) && x <= Math.max(b.x1,b.x2) && y >= Math.min(b.y1,b.y2) && y <= Math.max(b.y1,b.y2));
    if (hit !== -1 && !drawing) { selectedBox = hit; drawBoxes(); renderBoxList(); return; }
    drawing = true; startX = x; startY = y; selectedBox = -1;
  };
  canvas.onmousemove = (e) => {
    if (!drawing) return;
    const rect = canvas.getBoundingClientRect();
    const x = e.clientX - rect.left, y = e.clientY - rect.top;
    drawBoxes();
    const ctx = canvas.getContext("2d");
    ctx.strokeStyle = "#5b9eee"; ctx.lineWidth = 2;
    ctx.strokeRect(Math.min(startX,x), Math.min(startY,y), Math.abs(x-startX), Math.abs(y-startY));
  };
  canvas.onmouseup = (e) => {
    if (!drawing) return;
    drawing = false;
    const rect = canvas.getBoundingClientRect();
    const x = e.clientX - rect.left, y = e.clientY - rect.top;
    if (Math.abs(x-startX) > 5 && Math.abs(y-startY) > 5) {
      boxes.push({x1: startX, y1: startY, x2: x, y2: y, cls: null});
      selectedBox = boxes.length - 1;
    }
    drawBoxes(); renderBoxList();
  };
}

async function save() {
  if (idx >= images.length) return;
  if (boxes.some(b => !b.cls)) return;
  const im = images[idx];
  const canvas = document.getElementById("stage-canvas");
  const w = canvas.width, h = canvas.height;
  const yoloBoxes = boxes.map(b => {
    const x1 = Math.min(b.x1,b.x2), x2 = Math.max(b.x1,b.x2);
    const y1 = Math.min(b.y1,b.y2), y2 = Math.max(b.y1,b.y2);
    return {cx: ((x1+x2)/2)/w, cy: ((y1+y2)/2)/h, w: (x2-x1)/w, h: (y2-y1)/h, cls: b.cls};
  });
  await fetch("/api/save", { method: "POST", headers: {"Content-Type": "application/json"},
    body: JSON.stringify({ stem: im.stem, boxes: yoloBoxes }) });
  images[idx].reviewed = true;
  idx += 1;
  await loadStatus();
  renderList();
  await renderStage();
}

document.getElementById("btn-save").onclick = save;

window.addEventListener("keydown", (e) => {
  const tag = (e.target.tagName || "").toLowerCase();
  if (tag === "input" || tag === "textarea") return;
  if (e.key === "s" || e.key === "Enter") { e.preventDefault(); save(); }
  else if (e.key === "Delete" || e.key === "Backspace") {
    e.preventDefault();
    const i = selectedBox !== -1 ? selectedBox : boxes.length - 1;
    if (i >= 0) { boxes.splice(i, 1); selectedBox = -1; drawBoxes(); renderBoxList(); }
  }
  else if (CLASS_KEYS[e.key] && selectedBox !== -1) {
    boxes[selectedBox].cls = CLASS_KEYS[e.key];
    drawBoxes(); renderBoxList(); updateWarn();
  }
});

(async () => { await loadStatus(); await loadImages(); })();
</script>
</body>
</html>
"""

if __name__ == "__main__":
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        lan_ip = s.getsockname()[0]
        s.close()
    except Exception:
        lan_ip = "<your-lan-ip>"
    print(f"\nResolutions saved to: {RESULT_PATH}")
    print("Open on this machine: http://127.0.0.1:5062")
    print(f"Open from another device on the same WiFi: http://{lan_ip}:5062\n")
    app.run(host="0.0.0.0", port=5062, debug=False)
