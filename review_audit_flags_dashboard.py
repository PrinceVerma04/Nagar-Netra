"""
Review dashboard for the images flagged by scripts/audit_dataset.py.

Queue = exactly the images the 2026-09-07 annotation audit flagged (372 of 4,021),
each shown with WHY it was flagged so you can go straight to the suspect box
instead of re-inspecting a clean image.

Built to docs/ANNOTATION_DASHBOARD_STANDARD.md: single self-contained file,
stdlib + Flask + Pillow + PyYAML, scan-once/hold-in-memory, progress JSON flushed
on every write, deterministic hash partitioning, same canvas editor, /stats route.

WHAT MAKES THIS ONE DIFFERENT (read before editing):
Saving must update BOTH canonical trees, because nothing auto-propagates between
them (standard §8). Their shapes differ and the difference is not obvious:

    data/re-training_data/labels/<split>/<stem>.txt
        the UNION - every box on the image, all classes together.

    data/classwise _data/<class>/<split>/labels/<stem>.txt
        a per-class SUBSET - only that class's boxes. An image holding two classes
        therefore exists as two files, one under each class folder, each listing
        only its own boxes.

(That shape is also the answer to the long-standing "~2 image gap": classwise has
4,023 label files vs re-training's 4,021 because exactly 2 images hold two classes
each and so appear under two class folders. Not a missing-data bug.)

So /api/save rewrites the union file, rewrites/creates/deletes each affected
per-class file, and copies the image into a class folder that newly gains a box.
It is a full recompute-and-overwrite, never an incremental patch - deliberately,
per standard §7's warning about non-idempotent fixups.

Usage:
    python review_audit_flags_dashboard.py
    python review_audit_flags_dashboard.py --port 5070
    python review_audit_flags_dashboard.py --issue B      # only out-of-frame boxes

Then open the printed LAN URL. Add ?partition=A / ?partition=B to split the queue
between two people; omit it to get everything.
"""
import argparse
import hashlib
import json
import shutil
import socket
import threading
from pathlib import Path

import yaml
from flask import Flask, jsonify, request, send_file

BASE = Path(__file__).resolve().parent
DATA = BASE / "data"
RETRAIN = DATA / "re-training_data"
CLASSWISE = DATA / "classwise _data"
AUDIT_JSON = BASE / "docs" / "annotation_audit_20260907.json"
PROGRESS_PATH = DATA / "audit_flag_review_progress.json"
IMG_EXTS = (".jpg", ".jpeg", ".png")

NAMES = {int(k): v for k, v in yaml.safe_load((BASE / "configs" / "data.yaml").read_text())["names"].items()}
NC = len(NAMES)

ISSUE_LABELS = {
    "A": "malformed label line / bad class id",
    "B": "box extends past the image edge",
    "C": "zero-area box",
    "D": "suspiciously tiny box (<0.15% of frame)",
    "E": "box covers >95% of the frame",
    "F": "extreme aspect ratio (>20:1)",
    "G": "duplicate box (same class, IoU>0.9)",
    "H": "image has no boxes at all",
    "J": "corrupt / unreadable image",
    "K": "same image also in another split (leakage)",
    "L": "duplicate image within this split",
}

_lock = threading.Lock()


# --------------------------------------------------------------------- model

class Item:
    __slots__ = ("split", "stem", "img", "lbl", "issues", "details", "classes")

    def __init__(self, split, stem, img, lbl, issues, details, classes):
        self.split, self.stem, self.img, self.lbl = split, stem, img, lbl
        self.issues, self.details = issues, details
        self.classes = classes          # class names this image's FLAGS concern,
                                        # falling back to every class in the image

    @property
    def key(self):
        return f"{self.split}/{self.stem}"

    @property
    def partition(self):
        h = int(hashlib.md5(self.key.encode()).hexdigest(), 16)
        return "A" if h % 2 == 0 else "B"


def find_image(img_dir: Path, stem: str):
    return next((p for ext in IMG_EXTS if (p := img_dir / f"{stem}{ext}").is_file()), None)


def scan(issue_filter=None):
    if not AUDIT_JSON.is_file():
        raise SystemExit(f"{AUDIT_JSON} not found - run: python scripts/audit_dataset.py")
    audit = json.loads(AUDIT_JSON.read_text())

    # key -> {code: [detail, ...]}, built from the per-finding lists so the
    # dashboard can show the exact reason(s) next to the image.
    details, flag_classes = {}, {}
    for code, findings in audit["findings"].items():
        letter = code.split("_")[0]
        for f in findings:
            if f["split"] == "-":
                continue
            k = f"{f['split']}/{f['stem']}"
            details.setdefault(k, {}).setdefault(letter, []).append(
                f"{f.get('class', '')} {f['detail']}".strip())
            if f.get("class"):
                flag_classes.setdefault(k, set()).add(f["class"])

    wanted = {c.strip().upper() for c in issue_filter.split(",")} if issue_filter else None

    items = []
    for key, codes in sorted(audit["flagged_images"].items()):
        split, stem = key.split("/", 1)
        if wanted and not (wanted & set(codes)):
            continue
        img = find_image(RETRAIN / "images" / split, stem)
        if img is None:
            continue
        lbl = RETRAIN / "labels" / split / f"{stem}.txt"
        cls = flag_classes.get(key)
        if not cls:      # image-level flag (empty label, duplicate image) - use its content
            cls = {NAMES[c] for c in {b[0] for b in read_boxes(lbl)} if c in NAMES}
        items.append(Item(split, stem, img, lbl, sorted(codes), details.get(key, {}),
                          sorted(cls)))
    return items


def _load_progress():
    if PROGRESS_PATH.exists():
        return json.loads(PROGRESS_PATH.read_text())
    return {}


def _save_progress():
    PROGRESS_PATH.write_text(json.dumps(REVIEWED, indent=2, sort_keys=True))


def read_boxes(lbl: Path):
    if not lbl.is_file():
        return []
    out = []
    for line in lbl.read_text().splitlines():
        p = line.split()
        if len(p) >= 5:
            try:
                out.append([int(p[0]), *map(float, p[1:5])])
            except ValueError:
                pass
    return out


# ------------------------------------------------------------- the sync write

def write_both_trees(it: Item, boxes):
    """Overwrite the union file and every affected per-class file. Full recompute."""
    lines = [f"{c} {cx:.6f} {cy:.6f} {w:.6f} {h:.6f}" for c, cx, cy, w, h in boxes]
    it.lbl.parent.mkdir(parents=True, exist_ok=True)
    it.lbl.write_text("\n".join(lines) + ("\n" if lines else ""))

    by_class = {}
    for c, cx, cy, w, h in boxes:
        by_class.setdefault(c, []).append(f"{c} {cx:.6f} {cy:.6f} {w:.6f} {h:.6f}")

    touched = []
    # every class folder that currently holds this stem, plus every class now present
    existing = {p.parent.parent.parent.name for p in CLASSWISE.rglob(f"{it.stem}.txt")}
    for cname in existing | {NAMES[c] for c in by_class}:
        cls_lbl_dir = CLASSWISE / cname / it.split / "labels"
        cls_img_dir = CLASSWISE / cname / it.split / "images"
        cid = next((k for k, v in NAMES.items() if v == cname), None)
        target = cls_lbl_dir / f"{it.stem}.txt"
        if cid is not None and cid in by_class:
            cls_lbl_dir.mkdir(parents=True, exist_ok=True)
            cls_img_dir.mkdir(parents=True, exist_ok=True)
            target.write_text("\n".join(by_class[cid]) + "\n")
            dest_img = cls_img_dir / it.img.name
            if not dest_img.exists():
                shutil.copy2(it.img, dest_img)
            touched.append(f"+{cname}")
        else:
            # this class no longer has boxes here - remove its copy
            if target.is_file():
                target.unlink()
                old = find_image(cls_img_dir, it.stem)
                if old:
                    old.unlink()
                touched.append(f"-{cname}")
    return touched


# ----------------------------------------------------------------- the app

app = Flask(__name__)
ITEMS = []
REVIEWED = {}


@app.route("/api/status")
def api_status():
    total = len(ITEMS)
    done = sum(1 for it in ITEMS if it.key in REVIEWED)
    per_part, per_issue = {}, {}
    for it in ITEMS:
        p = per_part.setdefault(it.partition, {"total": 0, "done": 0})
        p["total"] += 1
        p["done"] += it.key in REVIEWED
        for c in it.issues:
            q = per_issue.setdefault(c, {"total": 0, "done": 0})
            q["total"] += 1
            q["done"] += it.key in REVIEWED
    per_class = {}
    for it in ITEMS:
        for c in it.classes:
            q = per_class.setdefault(c, {"total": 0, "done": 0})
            q["total"] += 1
            q["done"] += it.key in REVIEWED
    actions = {}
    for v in REVIEWED.values():
        actions[v.get("action", "?")] = actions.get(v.get("action", "?"), 0) + 1
    return jsonify({"total": total, "done": done, "pending": total - done,
                    "per_partition": per_part, "per_issue": per_issue,
                    "per_class": per_class,
                    "issue_labels": ISSUE_LABELS, "actions": actions})


@app.route("/api/images")
def api_images():
    part = request.args.get("partition")
    issue = request.args.get("issue")
    klass = request.args.get("class")
    wanted = {c.strip().upper() for c in issue.split(",")} if issue else None
    wclass = {c.strip() for c in klass.split(",")} if klass else None
    out = []
    for it in ITEMS:
        if it.key in REVIEWED:
            continue
        if part and it.partition != part:
            continue
        if wanted and not (wanted & set(it.issues)):
            continue
        if wclass and not (wclass & set(it.classes)):
            continue
        out.append({"split": it.split, "stem": it.stem, "key": it.key,
                    "issues": it.issues, "classes": it.classes,
                    "reasons": [f"[{c}] {ISSUE_LABELS.get(c, c)}" for c in it.issues],
                    "details": it.details})
    return jsonify(out)


@app.route("/api/boxes/<split>/<path:stem>")
def api_boxes(split, stem):
    it = next((i for i in ITEMS if i.split == split and i.stem == stem), None)
    if not it:
        return jsonify([])
    return jsonify([{"cls": b[0], "cx": b[1], "cy": b[2], "w": b[3], "h": b[4]}
                    for b in read_boxes(it.lbl)])


@app.route("/image/<split>/<path:stem>")
def image(split, stem):
    it = next((i for i in ITEMS if i.split == split and i.stem == stem), None)
    if it and it.img.is_file():
        return send_file(it.img)
    return ("", 404)


@app.route("/api/save", methods=["POST"])
def api_save():
    body = request.get_json(force=True)
    key = body["key"]
    it = next((i for i in ITEMS if i.key == key), None)
    if not it:
        return jsonify({"ok": False, "error": "unknown key"}), 404
    boxes = [[int(b["cls"]), float(b["cx"]), float(b["cy"]), float(b["w"]), float(b["h"])]
             for b in body.get("boxes", [])]
    for b in boxes:
        if not (0 <= b[0] < NC):
            return jsonify({"ok": False, "error": f"bad class id {b[0]}"}), 400
    with _lock:
        touched = write_both_trees(it, boxes)
        REVIEWED[key] = {"action": body.get("action", "corrected"),
                         "n_boxes": len(boxes), "classwise": touched}
        _save_progress()
    return jsonify({"ok": True, "touched": touched})


@app.route("/api/reject", methods=["POST"])
def api_reject():
    body = request.get_json(force=True)
    key = body["key"]
    it = next((i for i in ITEMS if i.key == key), None)
    if not it:
        return jsonify({"ok": False, "error": "unknown key"}), 404
    with _lock:
        for p in CLASSWISE.rglob(f"{it.stem}.txt"):
            cls_img = find_image(p.parent.parent / "images", it.stem)
            p.unlink()
            if cls_img:
                cls_img.unlink()
        if it.lbl.is_file():
            it.lbl.unlink()
        if it.img.is_file():
            it.img.unlink()
        ITEMS.remove(it)
        REVIEWED[key] = {"action": "rejected"}
        _save_progress()
    return jsonify({"ok": True})


PAGE = """<!doctype html><meta charset=utf-8><title>Audit flag review</title>
<style>
:root{color-scheme:dark}
body{background:#12141a;color:#e6e8ee;font-family:system-ui,sans-serif;margin:0;padding:14px}
h1{font-size:16px;margin:0 0 10px}
#wrap{display:flex;gap:16px;align-items:flex-start}
#stage{position:relative;display:inline-block;background:#000;border:1px solid #2a2f3a}
#img{display:block;max-width:76vw;max-height:78vh}
#cv{position:absolute;left:0;top:0;cursor:crosshair}
#side{width:340px;flex:0 0 340px}
.card{background:#1a1d25;border:1px solid #2a2f3a;border-radius:8px;padding:10px;margin-bottom:10px}
.reason{background:#3a2416;border-left:3px solid #e08b3e;padding:6px 8px;margin:4px 0;border-radius:4px;font-size:12px}
.det{color:#9aa3b5;font-size:11px;margin:2px 0 2px 10px;font-family:ui-monospace,monospace}
.chip{display:inline-block;padding:3px 7px;margin:2px;border-radius:5px;background:#242936;
      border:1px solid #333a49;font-size:11px;cursor:pointer}
.chip.on{background:#2d6cdf;border-color:#2d6cdf;color:#fff}
button{background:#242936;color:#e6e8ee;border:1px solid #333a49;border-radius:6px;
       padding:7px 11px;font-size:12px;cursor:pointer;margin:2px}
button.pri{background:#2d6cdf;border-color:#2d6cdf}
button.dan{background:#8b2b2b;border-color:#8b2b2b}
kbd{background:#000;border:1px solid #333a49;border-radius:3px;padding:1px 4px;font-size:10px}
#bar{height:6px;background:#242936;border-radius:3px;overflow:hidden;margin:6px 0}
#bar>div{height:100%;background:#3ba55d}
.small{color:#9aa3b5;font-size:11px;line-height:1.5}
#boxlist div{font-size:11px;padding:3px 5px;border-radius:4px;cursor:pointer;font-family:ui-monospace,monospace}
#boxlist div.sel{background:#2d6cdf}
</style>
<h1>Annotation audit review <span class=small id=hdr></span></h1>
<div id=wrap>
 <div><div id=stage><img id=img><canvas id=cv></canvas></div>
   <div class=small style="margin-top:6px">
     drag = new box &middot; click box = select &middot; <kbd>Del</kbd> delete &middot;
     <kbd>D</kbd> remove duplicate boxes &middot;
     <kbd>S</kbd> save+next &middot; <kbd>A</kbd> looks fine, keep as-is &middot;
     <kbd>N</kbd> skip &middot; <kbd>X</kbd> delete image</div></div>
 <div id=side>
  <div class=card><b id=cnt></b><div id=bar><div></div></div>
    <div class=small id=fname></div></div>
  <div class=card><b style="font-size:12px">Why this was flagged</b><div id=why></div></div>
  <div class=card><b style="font-size:12px">Class for new / selected box</b>
    <div id=classes></div></div>
  <div class=card><b style="font-size:12px">Boxes</b><div id=boxlist></div></div>
  <div class=card>
    <button onclick=dedupe()>Remove duplicate boxes <kbd>D</kbd></button>
    <div class=small id=dedupmsg></div>
  </div>
  <div class=card>
    <button class=pri onclick=save('corrected')>Save + next <kbd>S</kbd></button>
    <button onclick=save('confirmed_ok')>Looks fine <kbd>A</kbd></button>
    <button onclick=next()>Skip <kbd>N</kbd></button>
    <button class=dan onclick=reject()>Delete image <kbd>X</kbd></button>
  </div>
 </div></div>
<script>
const NAMES=__NAMES__, QS=new URLSearchParams(location.search),
      PART=QS.get('partition')||'', ISSUE=QS.get('issue')||'', KLASS=QS.get('class')||'';
let Q=[],i=0,boxes=[],sel=-1,cur=0,drag=null,total=0,done=0;
const img=document.getElementById('img'),cv=document.getElementById('cv'),cx=cv.getContext('2d');
function esc(s){return s.replace(/[&<>]/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;'}[c]))}
async function boot(){
  const st=await(await fetch('/api/status')).json(); total=st.total; done=st.done;
  document.getElementById('hdr').innerHTML=
    (PART?'partition '+PART+' · ':'')+(ISSUE?'issue '+ISSUE+' · ':'')
    +(KLASS?'class '+KLASS+' · ':'')+total+' flagged in all · <a style="color:#7ab0ff" href="/menu">menu</a>';
  document.getElementById('classes').innerHTML=Object.entries(NAMES).map(([k,v])=>
    `<span class=chip data-c="${k}" onclick=pick(${k})>${k} ${v}</span>`).join('');
  pick(0);
  Q=await(await fetch('/api/images?partition='+PART+'&issue='+ISSUE
                      +'&class='+encodeURIComponent(KLASS))).json();
  if(!Q.length){document.body.innerHTML='<h1>Nothing pending in this queue.</h1>';return}
  load();
}
function pick(c){cur=c;
  document.querySelectorAll('#classes .chip').forEach(e=>e.classList.toggle('on',+e.dataset.c===c));
  if(sel>=0){boxes[sel].cls=c;draw();list()}}
async function load(){
  if(i>=Q.length){document.body.innerHTML='<h1>Queue complete.</h1>';return}
  const it=Q[i]; sel=-1;
  document.getElementById('cnt').textContent=`${done} / ${total} reviewed · ${Q.length-i} left here`;
  document.querySelector('#bar>div').style.width=(100*done/total)+'%';
  document.getElementById('fname').textContent=it.key;
  document.getElementById('why').innerHTML=it.reasons.map((r,n)=>{
    const code=it.issues[n], d=(it.details[code]||[]).map(x=>`<div class=det>${esc(x)}</div>`).join('');
    return `<div class=reason>${esc(r)}</div>${d}`}).join('');
  const bs=await(await fetch(`/api/boxes/${it.split}/${encodeURIComponent(it.stem)}`)).json();
  img.onload=()=>{cv.width=img.clientWidth;cv.height=img.clientHeight;
    boxes=bs.map(b=>({cls:b.cls,x:(b.cx-b.w/2)*cv.width,y:(b.cy-b.h/2)*cv.height,
                      w:b.w*cv.width,h:b.h*cv.height}));draw();list()};
  img.src=`/image/${it.split}/${encodeURIComponent(it.stem)}?t=`+Date.now();
}
function draw(){cx.clearRect(0,0,cv.width,cv.height);
  boxes.forEach((b,n)=>{const out=b.x<-.5||b.y<-.5||b.x+b.w>cv.width+.5||b.y+b.h>cv.height+.5;
    cx.lineWidth=n===sel?3:2;cx.strokeStyle=n===sel?'#ffd54a':(out?'#ff6b6b':'#3ba55d');
    cx.strokeRect(b.x,b.y,b.w,b.h);
    cx.fillStyle=cx.strokeStyle;cx.font='11px system-ui';
    cx.fillText(NAMES[b.cls]||b.cls,b.x+2,Math.max(10,b.y-3))});
  if(drag)  {cx.setLineDash([4,3]);cx.strokeStyle='#2d6cdf';
    cx.strokeRect(drag.x,drag.y,drag.w,drag.h);cx.setLineDash([])}}
function list(){document.getElementById('boxlist').innerHTML=boxes.map((b,n)=>
  `<div class="${n===sel?'sel':''}" onclick="sel=${n};pick(${b.cls});draw();list()">${n+1}. ${NAMES[b.cls]}
   ${(b.w*b.h/(cv.width*cv.height)*100).toFixed(2)}%</div>`).join('')||'<div class=small>no boxes</div>'}
cv.onmousedown=e=>{const r=cv.getBoundingClientRect(),x=e.clientX-r.left,y=e.clientY-r.top;
  const hit=boxes.findIndex(b=>x>=b.x&&x<=b.x+b.w&&y>=b.y&&y<=b.y+b.h);
  if(hit>=0){sel=hit;pick(boxes[hit].cls);draw();list();return}
  drag={x0:x,y0:y,x:x,y:y,w:0,h:0}};
cv.onmousemove=e=>{if(!drag)return;const r=cv.getBoundingClientRect();
  const x=e.clientX-r.left,y=e.clientY-r.top;
  drag.x=Math.min(x,drag.x0);drag.y=Math.min(y,drag.y0);
  drag.w=Math.abs(x-drag.x0);drag.h=Math.abs(y-drag.y0);draw()};
cv.onmouseup=()=>{if(drag&&drag.w>5&&drag.h>5){
    boxes.push({cls:cur,x:drag.x,y:drag.y,w:drag.w,h:drag.h});sel=boxes.length-1}
  drag=null;draw();list()};
function iou(a,b){const ax2=a.x+a.w,ay2=a.y+a.h,bx2=b.x+b.w,by2=b.y+b.h;
  const iw=Math.max(0,Math.min(ax2,bx2)-Math.max(a.x,b.x)),
        ih=Math.max(0,Math.min(ay2,by2)-Math.max(a.y,b.y));
  const inter=iw*ih,u=a.w*a.h+b.w*b.h-inter;return u>0?inter/u:0}
// Same class + IoU>0.9 means two near-identical boxes on one object. Two distinct
// animals cannot produce that, so the later one is redundant - keep the first.
function dedupe(){const keep=[];let removed=0;
  boxes.forEach(b=>{const dup=keep.find(k=>k.cls===b.cls&&iou(k,b)>0.9);
    if(dup){removed++}else{keep.push(b)}});
  boxes=keep;sel=-1;draw();list();
  document.getElementById('dedupmsg').textContent=
    removed?`removed ${removed} duplicate box(es) - check, then press S to save`
           :'no duplicates found on this image';}
async function save(action){
  const it=Q[i];
  const payload=boxes.map(b=>({cls:b.cls,
    cx:(b.x+b.w/2)/cv.width,cy:(b.y+b.h/2)/cv.height,w:b.w/cv.width,h:b.h/cv.height}));
  const r=await(await fetch('/api/save',{method:'POST',headers:{'Content-Type':'application/json'},
    body:JSON.stringify({key:it.key,boxes:payload,action:action})})).json();
  if(!r.ok){alert('save failed: '+r.error);return}
  done++;i++;load()}
function next(){i++;load()}
async function reject(){if(!confirm('Delete this image and its labels from BOTH trees?'))return;
  await fetch('/api/reject',{method:'POST',headers:{'Content-Type':'application/json'},
    body:JSON.stringify({key:Q[i].key})});done++;i++;load()}
window.addEventListener('keydown',e=>{
  if(/^(INPUT|TEXTAREA)$/.test(document.activeElement.tagName))return;
  const k=e.key.toLowerCase();
  if(k==='delete'||k==='backspace'){e.preventDefault();
    if(sel>=0)boxes.splice(sel,1);else boxes.pop();sel=-1;draw();list()}
  else if(k==='s'){e.preventDefault();save('corrected')}
  else if(k==='a'){e.preventDefault();save('confirmed_ok')}
  else if(k==='d'){e.preventDefault();dedupe()}
  else if(k==='n'){e.preventDefault();next()}
  else if(k==='x'){e.preventDefault();reject()}});
boot();
</script>"""


STATS = """<!doctype html><meta charset=utf-8><title>Audit review progress</title>
<meta http-equiv=refresh content=300>
<style>body{background:#12141a;color:#e6e8ee;font-family:system-ui,sans-serif;padding:20px}
table{border-collapse:collapse;margin:10px 0}td,th{padding:5px 12px;border-bottom:1px solid #2a2f3a;
text-align:left;font-size:13px}#bar{height:12px;background:#242936;border-radius:6px;overflow:hidden;
max-width:520px}#bar>div{height:100%;background:#3ba55d}.small{color:#9aa3b5;font-size:12px}</style>
<h2>Annotation audit review progress</h2><div id=o></div>
<script>async function tick(){const s=await(await fetch('/api/status')).json();
let h=`<b>${s.done} / ${s.total}</b> reviewed (${s.pending} pending)
<div id=bar><div style="width:${100*s.done/Math.max(s.total,1)}%"></div></div>`;
h+='<h3>By partition</h3><table><tr><th>partition<th>done<th>total</tr>';
for(const[k,v]of Object.entries(s.per_partition))h+=`<tr><td>${k}<td>${v.done}<td>${v.total}</tr>`;
h+='</table><h3>By issue type</h3><table><tr><th>code<th>issue<th>done<th>total</tr>';
for(const[k,v]of Object.entries(s.per_issue).sort())
  h+=`<tr><td>${k}<td class=small>${s.issue_labels[k]||''}<td>${v.done}<td>${v.total}</tr>`;
h+='</table><h3>Decisions</h3><table>';
for(const[k,v]of Object.entries(s.actions))h+=`<tr><td>${k}<td>${v}</tr>`;
h+='</table>';document.getElementById('o').innerHTML=h}
tick();setInterval(tick,3000);</script>"""


MENU = """<!doctype html><meta charset=utf-8><title>Review menu</title>
<style>body{background:#12141a;color:#e6e8ee;font-family:system-ui,sans-serif;padding:22px;
line-height:1.5}h2{margin:0 0 4px}h3{margin:22px 0 6px;font-size:14px;color:#9aa3b5;
text-transform:uppercase;letter-spacing:.05em}a{color:#7ab0ff;text-decoration:none}
a:hover{text-decoration:underline}table{border-collapse:collapse}
td,th{padding:5px 14px 5px 0;text-align:left;font-size:13px;border-bottom:1px solid #22262f}
th{color:#9aa3b5;font-weight:500;font-size:11px;text-transform:uppercase}
.n{color:#e6e8ee;font-variant-numeric:tabular-nums}.d{color:#3ba55d}
.small{color:#9aa3b5;font-size:12px}</style>
<h2>Annotation review</h2>
<div class=small>Pick a queue. Everything writes to both canonical trees.</div>
<div id=o></div>
<script>async function tick(){const s=await(await fetch('/api/status')).json();
let h=`<h3>Everything</h3><a href="/">Review all ${s.total} flagged images</a>
 &nbsp;<span class=small>(${s.done} done, ${s.pending} pending)</span>
 &nbsp;·&nbsp;<a href="/stats">live progress</a>`;
h+='<h3>By problem</h3><table><tr><th>code<th>problem<th>images<th>done<th></tr>';
for(const[k,v]of Object.entries(s.per_issue).sort())
 h+=`<tr><td class=n>${k}<td>${s.issue_labels[k]||''}<td class=n>${v.total}
 <td class="n d">${v.done}<td><a href="/?issue=${k}">review</a></tr>`;
h+='</table><h3>By class</h3><table><tr><th>class<th>flagged images<th>done<th></tr>';
for(const[k,v]of Object.entries(s.per_class).sort((a,b)=>b[1].total-a[1].total))
 h+=`<tr><td>${k}<td class=n>${v.total}<td class="n d">${v.done}
 <td><a href="/?class=${encodeURIComponent(k)}">review</a></tr>`;
h+='</table><div class=small style="margin-top:18px">Combine filters in the URL, e.g.'
+' <code>/?issue=G,H&class=goat</code> · split with a partner by adding'
+' <code>&partition=A</code> / <code>&partition=B</code></div>';
document.getElementById('o').innerHTML=h}
tick();setInterval(tick,5000);</script>"""


@app.route("/menu")
def menu():
    return MENU


@app.route("/")
def index():
    return PAGE.replace("__NAMES__", json.dumps(NAMES))


@app.route("/stats")
def stats():
    return STATS


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", type=int, default=5070)
    ap.add_argument("--issue", default=None,
                    help="only queue one issue code, e.g. B (out-of-frame) or G (duplicate box)")
    args = ap.parse_args()

    global ITEMS, REVIEWED
    ITEMS = scan(args.issue)
    REVIEWED = _load_progress()

    counts, ccounts = {}, {}
    for it in ITEMS:
        for c in it.issues:
            counts[c] = counts.get(c, 0) + 1
        for c in it.classes:
            ccounts[c] = ccounts.get(c, 0) + 1

    print(f"\nQueued {len(ITEMS)} flagged images "
          f"({sum(1 for i in ITEMS if i.key in REVIEWED)} already reviewed)")
    for c in sorted(counts):
        print(f"   [{c}] {ISSUE_LABELS.get(c, c):46s} {counts[c]:>4}")
    print("\n  by class:")
    for c, n in sorted(ccounts.items(), key=lambda kv: -kv[1]):
        print(f"   {c:28s} {n:>4}")
    print(f"\nProgress file: {PROGRESS_PATH}")
    print("Saves update BOTH data/re-training_data AND data/classwise _data.\n")

    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(("8.8.8.8", 80))
        lan = s.getsockname()[0]
    except Exception:
        lan = "127.0.0.1"
    finally:
        s.close()
    print(f"  START HERE   : http://{lan}:{args.port}/menu")
    print(f"  Review all   : http://{lan}:{args.port}/")
    print(f"  This machine : http://127.0.0.1:{args.port}/menu")
    print(f"  Live progress: http://{lan}:{args.port}/stats")
    print(f"  One class    : http://{lan}:{args.port}/?class=camel")
    print(f"  One issue    : http://{lan}:{args.port}/?issue=G")
    print(f"  Two people   : add &partition=A / &partition=B\n")
    app.run(host="0.0.0.0", port=args.port, debug=False)


if __name__ == "__main__":
    main()
