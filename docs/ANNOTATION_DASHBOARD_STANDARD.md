# Annotation / Review Dashboard — Canonical Standard

This is the reusable architecture for every manual annotation/review dashboard
built for this project. It was extracted by inspecting the actual working
dashboards already built and used successfully across multiple sessions:

- `review_annotate_dashboard.py` — original multi-queue review tool (streetlight
  negatives + new_review_data classes), the ancestor of the pattern.
- `review_cow_dashboard.py` — single fixed-class review (cow → cattle).
- `review_manhole_split_dashboard.py` — single-folder, multi-key classification
  (closed/open/broken) + live `/stats`.
- `review_streetlight_split_dashboard.py` — adds the hash-based two-person
  **partition** split (`?partition=A/B`) on top of the manhole pattern.
- `review_cat_horse_dashboard.py` — generalized N-way class split via
  `?class=` query param, N people, one dashboard.
- `review_cattle_species_dashboard.py` — 5-way species re-classification
  combined with the partition split, for QA'ing an already-merged class.
- `review_dataset_for_goat.py` — same partition idea, but with a **click-to-pick
  identity screen** (localStorage-remembered) instead of a URL query param.
- `review_pending_merge.py` — confirm/correct dashboard scoped to exactly the
  images a reconciliation pass found still unmerged.
- `status_dashboard.py` — read-only reconciliation dashboard: live diff between
  `configs/data.yaml`, `data/classwise _data/`, `data/re-training_data/`, and
  every `dataset for review/` folder.
- `review_github_streetlight.py` / `review_github_streetlight_auto.py` — a
  batch-confirm variant (folder-sorted input, dashboard just confirms/rejects).

Every one of these is a **single self-contained Python file**: stdlib +
Flask + Pillow (+ PyYAML if it needs `configs/data.yaml`). No database, no
JS build step, no external frontend framework. This is deliberate — it means
a dashboard can be written, run, and thrown away in one sitting, and anyone
can `python <file>.py` it with nothing but the project's existing venv.

---

## 1. When to reach for this pattern

Any time a human needs to look at images one at a time, fix or confirm YOLO
boxes, and have the result land directly in the dataset's own files — with a
progress record so it's resumable and so a second dashboard can find out
what's already done. This covers: first-pass annotation, correcting existing
boxes, splitting one coarse class into several finer ones, re-checking a
class that turned out to be contaminated, and confirm-only batch review.

Do **not** reach for this pattern for: anything that isn't image+box review
(that's just a script), anything that needs to run outside this LAN, anything
that needs more than a handful of concurrent users, or a permanent production
tool (this is explicitly a disposable, single-file, one-session tool).

## 2. Architecture at a glance

```
                    ┌───────────────────────────────┐
Browser (Person A)  │                                │
  /?partition=A ───▶│                                │
                    │        Flask app (1 process)   │
Browser (Person B)  │        binds 0.0.0.0:PORT      │
  /?partition=B ───▶│                                │──▶ reads/writes image +
                    │  in-memory ITEMS (scanned once  │    label files directly
Browser (you)       │  at startup) + REVIEWED dict    │    on local disk
  /stats ──────────▶│  (loaded from / flushed to a    │
                    │  single progress .json)         │──▶ progress .json
                    └───────────────────────────────┘     (survives restarts)
```

One Flask process is the single source of truth. Every browser — on this
machine or another one on the same LAN — talks to that one process over
HTTP. There is no client-side state that matters (a page refresh loses
nothing but the current unsaved box edit). This is what makes "two people,
two machines, one live state" trivial: it's just two HTTP clients hitting one
server, no different from three browser tabs.

## 3. Backend design

### 3.1 Startup: scan once, hold in memory

```python
class Item:
    __slots__ = ("split", "stem", "img", "lbl")   # or (qclass, stem, img, lbl), etc.
    @property
    def key(self): return f"{self.split}/{self.stem}"   # the one stable identity

def scan():
    items = []
    for split in SPLITS:                      # or: for class_folder in QUEUES
        for img in sorted(img_dir.iterdir()):
            lbl = lbl_dir / f"{img.stem}.txt"
            items.append(Item(split, img.stem, img, lbl))
    return items

ITEMS = scan()          # module-level, built once at process start
```

Rules that matter:
- **`key` is always `"<split_or_queue>/<stem>"`**, never just the filename —
  two different splits/queues can share a stem, and every progress dict,
  reject call, and save call is addressed by this key.
- The scan is **read-only** and defines "what exists" for the life of the
  process. New files dropped on disk after startup are not picked up until
  restart — this is intentional (a fixed set of work per session).
- Legitimate empty-box images (real negatives) are either skipped at scan
  time (if the dashboard's job is species/class-splitting, where an empty
  box has nothing to classify) or included and simply save with an empty
  boxes list (if the dashboard's job is drawing boxes from scratch). Decide
  this once per dashboard and be consistent.

### 3.2 Persistent state: one JSON file, loaded at boot, flushed on every write

```python
PROGRESS_PATH = REVIEW_DIR / "<something>_progress.json"

def _load_progress():
    if PROGRESS_PATH.exists():
        return json.loads(PROGRESS_PATH.read_text())
    return {}                      # or {} / [] / set() depending on shape

def _save_progress():
    PROGRESS_PATH.write_text(json.dumps(REVIEWED, indent=2, sort_keys=True))

REVIEWED = _load_progress()        # module-level, mutated in place, in-process
```

- `REVIEWED` maps `key -> <whatever's useful>` — a bare `True`/list-membership
  for a single-class dashboard, or the chosen class/species name for a
  multi-way one. Whatever it stores, **the annotation ground truth is never
  only in this file** — it always mirrors what's already been written to the
  real label `.txt`. If this JSON were deleted, the dashboard just forgets
  what it already showed you and everything reappears as "pending" (annoying,
  re-review-worthy, but **not data loss** — see §7).
- Every mutation (`/api/save`, `/api/reject`) takes `_lock`, mutates the
  dict/ITEMS, and calls `_save_progress()` **before** returning `{"ok": true}`
  to the browser. The write is synchronous and small (one JSON file, one
  `write_text` call) — no batching, no async, no queue. At this project's
  scale (hundreds to a few thousand images, 1-3 concurrent reviewers) this
  is fast enough to not be worth optimizing, and "safe over slick" wins.
- **Progress files live next to the data they describe**
  (`dataset for review/<name>_progress.json`, or inside the specific
  `classwise_data/<class>/` folder being worked on), never in a shared global
  location — so deleting a review folder cleanly takes its own progress file
  with it, and two unrelated dashboards never collide on one file.

### 3.3 Concurrency & the "claiming" problem — solved by construction, not by locks

This project's dashboards do **not** implement live claim/lock/heartbeat
machinery (no "worker X is holding image Y, release after 60s of silence").
Instead, they make two accidentally-claiming-the-same-image impossible by
**deterministic partitioning up front**:

```python
@property
def partition(self):
    h = int(hashlib.md5(self.key.encode()).hexdigest(), 16)
    return "A" if h % 2 == 0 else "B"
```

- The hash of each item's `key` decides its partition **once**, and that
  answer never changes for the life of the dataset (same key → same hash →
  same partition, forever, across restarts, across N people if you extend it
  to `h % N`). Two people can load the queue at the exact same instant and
  will never receive the same image, because the split isn't first-come-first
  -served — it's baked into the key itself.
- This is strictly simpler and more robust than live claiming for this
  project's actual usage pattern: 1-3 named people, working for a session or
  two, on a small-to-medium batch. Live claiming earns its complexity at
  much higher concurrency or with anonymous/rotating workers — neither
  applies here.
- **"Stale worker" handling falls out for free**: if Person B disconnects
  mid-session, their half of the queue simply sits there unreviewed — no
  lease to expire, no orphaned lock to detect, nothing to clean up. Anyone
  (including a third person) can resume that exact partition later by
  loading the same URL; the server has no notion of "B is currently working"
  to go stale in the first place.
- **Never-conflicting writes**: `_lock` (a plain `threading.Lock`) still
  guards every write to `REVIEWED`/label files, because Flask's dev server
  can service two requests concurrently on threads — this is defense against
  simultaneous requests corrupting the shared `dict`/JSON write, not defense
  against two people picking the same image (already impossible by
  construction above).
- **Exposing identity to the reviewer**, two accepted variants:
  - **URL query param** (`?partition=A`, `?class=cat`) — dead simple, and the
    right choice when you're personally handing each person their own link
    (this project's most common case).
  - **Click-to-pick screen, remembered via `localStorage`** — nicer when the
    same single link gets shared to a group and you want each browser to
    remember its own identity across reloads without re-typing a URL param
    (`review_dataset_for_goat.py`'s approach). Prefer this when the "who are
    you" question is better asked once inside the page than baked into the
    link you distribute.

### 3.4 Standard Flask route surface

Every dashboard exposes the same shape of API, regardless of what it's
splitting by (split/class/species/partition):

| Route | Method | Purpose |
|---|---|---|
| `/` | GET | Serves the single-page HTML+JS review UI |
| `/stats` | GET | Serves a separate, read-only, auto-refreshing live-progress page |
| `/api/status` | GET | Aggregate counts: total/reviewed/pending (+ per-partition, + per-class tally) |
| `/api/images` | GET | The **pending-only** queue for this viewer (filtered by partition/class/etc via query param) |
| `/api/boxes/<split>/<stem>` | GET | Existing boxes for one image, as normalized `[cx,cy,w,h]` |
| `/image/<split>/<stem>` | GET | Serves the actual image file (`send_file`, with a placeholder JPEG fallback on corrupt/missing files) |
| `/api/save` | POST | Writes the label file, marks the item reviewed, flushes progress |
| `/api/reject` | POST | Deletes a bad image+label pair outright, removes it from `ITEMS` and progress |

`/api/images` **only ever returns unreviewed items** — once saved, an image
drops out of every future `/api/images` response for every viewer. This is
what makes "resume where you left off" and "never re-show a done image"
automatic rather than something the frontend has to track.

### 3.5 Saving: always full-image replace, never line-patching by position

```python
@app.route("/api/save", methods=["POST"])
def api_save():
    body = request.get_json(force=True)
    lines = [f"{class_id} {cx:.6f} {cy:.6f} {w:.6f} {h:.6f}" for cx, cy, w, h in boxes]
    it.lbl.write_text("\n".join(lines) + ("\n" if lines else ""))
    REVIEWED[it.key] = <chosen class/species/True>
    _save_progress()
```

The browser always sends the **complete current box list** for that image
(everything currently drawn on the canvas — kept boxes plus new ones minus
deleted ones), and the save handler always **overwrites the whole label file**
with exactly that list. There is no "append a box" or "patch line 2" endpoint.
This means:
- A reviewer redrawing a wrong box is just: delete it on the canvas, drag a
  new one, save — the file ends up correct with no special-case "replace"
  logic anywhere.
- There's no way to "merge" a stale browser's edit with someone else's newer
  edit on the *same* image, because that can't happen — an image belongs to
  exactly one partition/queue, so only one browser ever legitimately edits it
  in a session. (If two dashboards for *different* purposes both touch the
  same file — e.g. this species-check dashboard and a hypothetical box-only
  dashboard running at once — that's a process-design mistake to avoid, not
  something the save handler defends against.)

## 4. Frontend: the one canvas editor, copy it verbatim

Every dashboard ships **the same box-editing JS**, adapted only in which API
paths it calls. Do not redesign this per dashboard — copy it:

- An `<img>` for the photo, a `<canvas>` absolutely positioned on top of it,
  sized to `img.clientWidth`/`clientHeight` once the image has loaded.
- Existing boxes are fetched from `/api/boxes/...`, converted from normalized
  YOLO (`cx,cy,w,h`) to canvas pixels once, and redrawn with a `drawBoxes()`
  call on every change.
- **Draw**: mousedown starts a rect, mousemove live-previews it, mouseup
  commits it to the `boxes` array (only if it's bigger than a 5px dead zone,
  so an accidental click doesn't create a zero-size box).
- **Select**: mousedown that lands inside an existing box (and isn't a drag)
  selects it (highlighted in a different stroke color) instead of starting a
  new one.
- **Delete**: `Delete`/`Backspace` removes the selected box, or the last box
  drawn if nothing's selected.
- **Convert back to YOLO on save**: canvas pixels → normalize by
  `canvas.width`/`canvas.height` → `[cx,cy,w,h]`, always taking `min`/`max` of
  the two drag corners so a box dragged in any direction comes out correct.
- **Keyboard**, bound on `window`, always guarded against firing while an
  `<input>`/`<textarea>` has focus:
  - a single key (or one key per class, e.g. `1`/`2`/`3`) triggers
    "classify (if applicable) + save + advance to next" in one action — this
    is what makes review *fast*; nobody should have to reach for a mouse to
    move to the next of a thousand images.
  - `N` = next without saving, `P` = previous, `X` = reject (with a
    `confirm()` — the one dialog these pages are allowed to use, since
    reject is destructive and rare).
- Dark theme, `system-ui` font, no external CSS/JS dependencies — the whole
  page is one Python triple-quoted string. This isn't an aesthetic
  preference so much as a portability one: nothing to install, nothing to
  fail to load, works the same on any machine's browser.

## 5. Live progress tracking (`/stats`)

A **separate route**, never mixed into the main review page, so a "watch
progress" tab can be left open on your own machine without it fighting over
canvas/keyboard state with an active reviewer's tab:

- Auto-refreshes via `setInterval(tick, 3000)` hitting `/api/status` — no
  websockets, no SSE, just polling every 3s. At this scale that is plenty
  responsive and immeasurably simpler than a push channel.
- Shows: overall reviewed/total + bar, a per-partition (or per-class,
  per-species — whatever the split axis is) breakdown, and a class-wise
  tally of what's been decided so far.
- `<meta http-equiv="refresh" content="300">` as a dumb fallback in case JS
  ever stalls — cheap insurance, not the primary refresh mechanism.
- Read-only: `/stats` never calls `/api/save` or `/api/reject`. It exists
  purely so "who's working on what, how much is left" doesn't require asking
  anyone or `grep`-ing progress JSON by hand.

## 6. Multi-machine / network setup

```python
app.run(host="0.0.0.0", port=PORT, debug=False)
```

- `host="0.0.0.0"` is what makes the dashboard reachable from other machines
  at all — `127.0.0.1` (the Flask default) only ever answers on the same
  machine.
- Print **both** the loopback and LAN URLs on startup (LAN IP discovered via
  the connect-a-UDP-socket-to-8.8.8.8 trick, no real packet sent, just reads
  back which local interface routing picked):
  ```python
  s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
  s.connect(("8.8.8.8", 80)); lan_ip = s.getsockname()[0]; s.close()
  print(f"Open on this machine: http://127.0.0.1:{PORT}")
  print(f"Open from another device on the same WiFi: http://{lan_ip}:{PORT}")
  ```
- Every other machine must be **on the same WiFi/LAN** — there is no tunnel,
  no port-forwarding, no auth. This is a same-room/same-network tool, never
  exposed to the internet.
- **Port choice matters more than it looks**: Chrome (and other Chromium
  browsers) hard-block a list of "unsafe" ports regardless of what's
  listening there — this bit us for real on port `5060` (`ERR_UNSAFE_PORT`,
  reserved for SIP). Symptom: works via `curl`/on the server machine, fails
  with "site can't be reached" from every other browser. **Before handing out
  a new port, sanity-check it isn't one of the classic blocked ones** (20,
  21, 25, 69, 111, 137-139, 445, 512-532, 540, 587, 601, 636, 993, 995, 1719,
  1720, 1723, 2049, 3659, 4045, 5060, 5061, 6000, 6566, 6665-6669, 6697, and a
  few dozen more historically-abused service ports). This project's ports in
  use: `5053`, `5055`, `5056`, `5057`, `5058`, `5059`, `5062`, `5063` — pick
  the next free number outside the 505x SIP-adjacent range and outside the
  6000s (X11) if you can, and if a link mysteriously fails only in-browser,
  suspect this before anything else (see §9).
- A dead-simple firewall check when a link fails despite the server
  responding fine locally: `systemctl is-active ufw` tells you if the
  *service* is running, but `sudo ufw status` is what tells you if it's
  actually *enforcing* anything (`inactive` means it's a non-issue even if
  the service unit shows active).

## 7. Recovery & restart safety

- **The dashboard process is stateless-restartable with zero data loss**:
  restarting re-runs `scan()` (rebuilds `ITEMS` from whatever's on disk right
  now) and reloads `REVIEWED` from the progress JSON. Annotations already
  saved are safe because they live in the real label files, not in the
  Flask process's memory.
- **The only thing a restart can "lose" is review bookkeeping**, and only if
  the progress JSON itself is deleted or was never written — in that case
  everything shows as pending again, meaning redundant re-review work, not
  corrupted or lost annotations. Treat the progress JSON with the same care
  as any other small but important file: don't delete it while work is
  in-flight, but don't panic if it's gone — nothing about the dataset itself
  is unrecoverable.
- **A crash mid-fix-up script is the one real danger, and it already bit us
  once**: a promotion/merge script that reads a label file, transforms it,
  and rewrites it needs to be **idempotent** — safe to run twice — because
  you will, eventually, need to run it twice (a crash, a re-run to catch
  strays, etc). The concrete failure mode we hit: a re-training-data label
  fixup that did `kept = [lines not starting with old_id] + [new lines]`
  duplicated every affected box when re-run, because after the first
  successful run there were no more `old_id` lines to strip, so the "new
  lines" got appended a second time on top of the already-correct ones.
  **Always guard mutating fixups with an explicit idempotency check**
  (`if not any(l.startswith(old_prefix) for l in lines): continue`), or better,
  make the operation naturally idempotent (recompute the full authoritative
  content and overwrite, rather than incrementally patch).

## 8. Dataset integration — identifying reviewed/pending/merged/duplicate

This project's folder shapes, and how a dashboard (or a reconciliation
script like `status_dashboard.py`) reasons about them:

- **`data/classwise _data/<class>/{train,val,test}/{images,labels}/`** — the
  live, authoritative, per-class training data. A dashboard reviewing this
  folder directly is editing the real thing in place.
- **`data/re-training_data/{images,labels}/{train,val,test}/`** — the same
  images/labels, organized by split instead of by class, for actually
  pointing `configs/data.yaml`'s `train`/`val`/`test` at. **These two must be
  kept in sync by hand** — nothing auto-propagates a `classwise_data` edit
  into `re-training_data` or vice versa. Every promotion script in this
  project's history updates both explicitly, in the same script, in the
  same run.
- **`dataset for review/<name>/`** — a staging/working copy for review that
  is *not* live training data yet. Two shapes seen in practice:
  flat (`images/`+`labels/` directly), or already-sorted-by-class
  (`<class_a>/images,labels`, `<class_b>/images,labels`, ...).
- **Merged vs. pending, computed by filename-stem matching** (the technique
  `status_dashboard.py` uses, and the right one to reuse): for a review
  folder mapped to a target class, take the set of image stems in the review
  folder and the set of stems already in that class's `classwise_data`
  folder (stripping a known `<classname>_` prefix if the destination adds
  one), and diff:
  ```python
  merged = review_stems & classwise_stems
  pending = review_stems - classwise_stems
  status = "Fully merged" if not pending else ("Not merged" if not merged else "Partially merged")
  ```
  This is **recomputed fresh every time**, never cached — it's cheap (a
  filesystem listing + set intersection) and guarantees the status always
  reflects the current, real state of both folders, including work done by
  a promotion script, a different session, or a person's manual copy outside
  any dashboard.
- **A review folder is safe to delete only when its status is "Fully
  merged"** for every class it maps to. "Partially merged" or "Not merged"
  means real, otherwise-unrecoverable review decisions are still only in the
  review folder — deleting it would lose that work. **Always run the
  merge-status check before deleting any `dataset for review/` folder**,
  never infer it from memory of "I think we finished this."
- **Class-id updates when the taxonomy changes** (splitting one class into
  several, as with `manhole_open_broken` → closed/open/broken, or
  `streetlight_pole` → working/not_working): the pattern used every time —
  1. Add the new id(s) to `configs/data.yaml`, mark the old id's line with an
     inline `# deprecated <date>: superseded by ids X-Y` comment. **Never
     delete or renumber an existing id** — anything already trained against
     it, or any label file not yet touched, still needs that id to mean what
     it always meant.
  2. Run the review dashboard writing the *new* ids directly onto the boxes
     it saves (this dashboard doesn't need to know or care that a promotion
     step comes later).
  3. Separately, run a one-off promotion script (kept in the session's
     scratchpad, not committed — see `data/build_train_variants.py`'s own
     docstring for the same philosophy re: derived data) that:
     - splits `classwise_data/<old_class>` into `classwise_data/<new_class_i>`
       folders by reading each label's (now-correct) class id, **moving**
       (not copying) each image+label pair — since it's leaving one class for
       another, not being duplicated into both;
     - rewrites the matching `re-training_data` label file, replacing lines
       of the old id with the new, corrected lines from the just-moved
       classwise copy (which may have different box geometry than before, if
       the review corrected a box — always source the replacement content
       from the classwise copy, never assume the geometry is unchanged);
     - is **idempotent** (see §7) so a crash or accidental double-run can't
       corrupt data;
     - **only processes images that were actually reviewed** — anything
       still carrying the old, deprecated id after review is left exactly
       where it is, for a later pass, never force-promoted with a guessed
       class.
  4. Re-run `data/build_train_variants.py` (or whatever derived-dataset
     builder exists) to regenerate anything built *from* `re-training_data` —
     never hand-edit a derived/generated dataset directly.

## 9. Common failure cases (seen for real, on this project)

| Symptom | Cause | Fix |
|---|---|---|
| "Site can't be reached" from another machine, `curl` from the server machine works fine | Wrong URL (`127.0.0.1` typed on the *other* machine) or genuinely different network | Confirm both machines are on the same WiFi/LAN; use the printed LAN IP, never `127.0.0.1`, from any other machine |
| `ERR_UNSAFE_PORT` in the browser specifically | Port is on Chromium's built-in blocked-ports list (5060/5061 = SIP, 6000 = X11, etc) | Change the port to an unlisted one (see §6) and restart |
| A dashboard shows 0 reviewed after it previously had progress | Progress JSON was deleted, or the destination path changed between runs | Check whether the JSON exists and matches `PROGRESS_PATH`; this is recoverable annotation-wise (see §7) but redoes bookkeeping |
| Duplicate boxes appear in `re-training_data` after a promotion script | Fixup logic wasn't idempotent and got run twice (e.g. a crash mid-script, then a naive re-run) | Rewrite as "recompute full authoritative content, overwrite" instead of "append if condition", or add an explicit already-done guard; to repair existing damage, resync from the classwise copy (authoritative) rather than trying to de-dupe blindly |
| Two people worked the same image anyway | A dashboard was run *without* the partition/identity split (e.g. an ad-hoc single-queue tool handed to two people) | Any dashboard given to more than one person **must** implement §3.3's partitioning — this is not optional past one reviewer |
| `git status` shows huge/binary diffs after a dashboard session | Dashboards write real image/label files directly — this is intended, not a bug, but means these are real dataset commits, not throwaway | Review the diff like any other data change before committing; the dashboard itself is disposable, its *output* is not |
| A promotion script silently used the wrong folder-layout assumption (e.g. treated `re-training_data` as `{class}/{split}/...` like `classwise_data`) | `classwise_data` and `re-training_data` have **different** directory shapes (see §8) — easy to copy-paste one loop over both by mistake | Always write the two destination paths explicitly and separately; never assume a shared helper function's path shape applies to both |

## 10. Security / data-safety considerations

- **No authentication, ever, by design** — this is a same-LAN, trusted-people
  tool. It must never be exposed past the local network (no port-forwarding,
  no reverse proxy to the internet, no cloud tunnel). If a use case ever
  needs remote reviewers, that's a different, explicitly-scoped tool, not
  this pattern with a tunnel bolted on.
- **Reject is destructive and irreversible by design** (permanently deletes
  an image+label pair) — the one `confirm()` dialog these pages use exists
  specifically to gate this action. Never add a "reject all" or bulk-reject
  shortcut without an equally deliberate confirmation step.
- **Never let the dashboard write outside its own `REVIEW_DIR`/target class
  folder** — every path the server touches is built from `BASE` + a small,
  hardcoded set of known subfolders, never from unvalidated request input
  interpolated directly into a filesystem path. The `<split>`/`<stem>`/
  `<qclass>` route parameters are looked up against the in-memory `ITEMS`
  list (built from a real, trusted directory scan) rather than used to
  construct a path directly — this is what stops a malformed request from
  reading or writing arbitrary files.
- **Treat the annotation output as real project data, not scratch** — the
  dashboard script itself can live in the repo or in scratch depending on
  how reusable it turns out to be, but the image/label files it writes are
  exactly as significant as any other dataset change and should be reviewed
  (via `git status`/`git diff` on the label files, or the merge-status check
  in §8) before being trusted for training.

## 11. Checklist for building a new dashboard

When asked to "make a dashboard" or "make the annotation dashboard" for a
new batch/class-split, follow this checklist in order rather than designing
from scratch:

1. **Inspect the actual target folder(s)** first — image/label counts, label
   format (numeric class id vs. class-name text), split layout (flat vs.
   `train/val/test`), any existing progress files. Never assume; a mismatch
   here (like `re-training_data`'s different layout, or a source using class
   *names* instead of ids) is the most common real bug.
2. **Decide the split axis and how many people**: one fixed class per queue
   (§3, cow-style), N classes via a query param (cat/horse/dog-style), or a
   single class needing hash-partitioning across 2+ people (streetlight/
   cattle-species-style). Pick whichever matches the actual task, don't
   default to the most complex option.
3. **Decide identity UX**: URL query param (simplest, use when you're
   handing out per-person links yourself) vs. click-to-pick +
   `localStorage` (nicer for a single shared link).
4. **Copy an existing dashboard closest to the new shape** as the starting
   file (don't write the canvas/keyboard JS from scratch — it has already
   been debugged across half a dozen dashboards) and adapt: the `Item`
   scan, the class/queue definitions, the keyboard-key-to-class mapping, and
   the port number (checked against §6's blocked-port list).
5. **Decide the target class id(s)** up front if this is a taxonomy change —
   check `configs/data.yaml`, add new ids with a clear name, mark any
   superseded id deprecated in a comment, **before** wiring the dashboard to
   write them.
6. **Add `/stats`** unconditionally — it costs almost nothing and is what
   lets progress be watched without interrupting reviewers.
7. **Smoke-test the full round trip before handing out links**: start the
   server, `curl` `/api/status`, `curl` one image's `/api/boxes`, POST a
   test `/api/save`, verify the label file content, **then restore the test
   data** (either from the original box coordinates you fetched, or by
   deleting the one progress-JSON entry your test created) before real
   reviewers touch it.
8. **Print both loopback and LAN URLs, plus the `/stats` URL**, on startup —
   copy the exact print block used elsewhere in this codebase.
9. **When review is finished, promotion is a separate, explicit step** — a
   scratch script (see §8), never folded into the dashboard's save handler.
   Verify counts before and after, check for idempotency if the script might
   ever be re-run, and re-run any derived-dataset builder
   (`build_train_variants.py` or equivalent) afterward.
10. **Stop the server and clean up its progress file only after promotion is
    verified complete** — while it's still useful for resuming or auditing,
    leave it; a finished, promoted progress file is safe to delete since the
    real annotations live in the label files, not in it.
