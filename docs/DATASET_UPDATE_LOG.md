# Dataset Update Log

Running changelog of every dataset added, removed, or changed in this project.
Append a new dated entry every time the dataset composition changes — new source
merged, a class discarded, a collector adds new photos, a re-annotation happens, etc.
Do not edit past entries; add a new one.

**Entry template:**

```
## YYYY-MM-DD HH:MM TZ — <short title>
- Collector: <ashrith | Pawan | Prince | Rahul | ...>
- Dataset: <dataset/folder name>
- Source link: <URL, or "self-collected" / "unknown">
- Class(es): <unified class name(s) it maps to, or "n/a — discarded">
- Action: <added | removed | re-annotated | merged | moved>
- Where it lives now: <path>
- Notes: <anything non-obvious>
```

---

## 2026-08-29 14:48 IST — All kept-source folders deleted; data/unified is now the sole copy

- Action: removed
- Where it lived: `data/raw/` (3.6G — the 8 remaining Prince source folders: taco,
  trash_detection, pothole_intel, open_manholes, streetlight, manhole_broken_v2,
  manhole_cover, street_vendors_india) and `Data Collection/` in full (3.1G —
  Pawan/Pavan, ashrith/ASHRITH, Rahul's kept folders)
- Notes: user explicitly chose, after seeing the exact tradeoff, to keep only
  `data/unified/` as "the data selected for training." **This is different from the
  earlier not_used deletion** — these were all "keep"-decision classes, already fully
  copied into `data/unified` under renamed filenames, so no unified-training content
  is lost. **One real, permanent loss: `ashrith::drain_closed` (3.3MB, ~80 images)**
  — it was marked "keep" in class_review.json but was deliberately never merged into
  data/unified (no matching unified class — it represents the non-hazard/negative
  drain case). Its images now exist nowhere on disk or in git; if ever wanted again
  it would need to be re-collected from scratch (self-collected phone photos, no
  external source link recorded).
  Also lost: the ability to re-run `data/merge_datasets.py` (source dirs gone) and
  `dataset_dashboard.py`'s ability to browse any class's original images (verified:
  it still runs without crashing, just shows 0 items everywhere — confirmed, not
  assumed). Project size: 18G → 11G.
  All source provenance (which collector/link/license fed which unified class)
  remains fully documented in the entries below and in [[project_dataset_provenance]] —
  only the pixel data itself is gone, not the record of where it came from.

## 2026-08-29 17:39 IST — fixed: no annotation boxes showing for manhole sub-views

- Action: bug fix (review_tool.py)
- Notes: user reported no bounding boxes drawn when browsing manhole_open /
  manhole_broken / manhole_closed in the dashboard. Root cause: `render_annotated`'s
  `only_class` filter compares against the class name literally stored in the label
  file — which is still `manhole_open_broken` for every box, since the sub-views are
  just filtered slices of the same class, not a separate label. The frontend was
  passing `class=manhole_open` (etc.), which never matched `manhole_open_broken`, so
  every box got silently filtered out. Fixed in the `/image/<split>/<stem>` route:
  resolve the requested class through `SUB_CLASS_PARENT` before filtering, so a
  sub-view request now correctly matches its parent class's boxes. Verified by
  fetching one real image from each of the 3 sub-views directly — boxes now render
  correctly in all three (confirmed visually, including re-confirming the earlier
  "closed" data-quality finding: that box sits around the covered/grated drain, not
  the open hole in the same photo).

## 2026-08-29 17:36 IST — manhole folder relocated + made visible in review_tool.py

- Action: moved + tool updated
- User correctly pushed back on two things from the previous entry: (1) the
  `manhole/` folder sat at the repo root instead of inside `data/` where all other
  project data lives (moved to `data/manhole/` — plain `mv` on the same filesystem,
  hardlinks to data/unified confirmed still intact, same inodes); (2) it wasn't
  visible anywhere in the actual review dashboard (http://127.0.0.1:5050) — it was
  just a folder on disk, browsable only by a human digging through the filesystem.
- Persisted the open/closed/broken classification itself to
  `data/manhole_classification.json` (previously only existed in `/tmp`, which does
  not survive). `review_tool.py` now loads that file at startup and adds
  `manhole_open` / `manhole_broken` / `manhole_closed` as three extra sidebar
  entries, indented under `manhole_open_broken` with a small "↳" marker — same
  images, same annotation rendering, same rotate controls, and Keep/Discard
  decisions are shared with the parent class (both use the same `split/stem` key in
  review_decisions.json, so reviewing an image once counts everywhere it appears).
- Verified: dashboard restarted cleanly, all 3 sub-entries show correct counts
  (open=811, broken=207, closed=4), image rendering and decision API confirmed
  working for the new entries via direct API calls.

## 2026-08-29 16:00 IST — manhole/{open,closed,broken}/ folder built from re-downloaded original labels

- Action: added (organizational only — no change to data/unified)
- Where it lives: `manhole/{open,closed,broken}/{images,labels}` at repo root, hardlinked
  from data/unified (zero extra disk space)
- Notes: the unified `manhole_open_broken` class collapsed each source's original
  sub-state (Broken/Good/Lose/Uncovered from `manhole_cover`; Manhole/Open-Manholes
  from `open_manholes`; single-class MB from `manhole_broken_v2`) into one class id
  during merging — and the original source folders were later deleted (see the
  "kept-source folders deleted" entry above). To recover the sub-state per image,
  **re-downloaded the 3 relevant Roboflow projects fresh** (into `/tmp/`, not
  committed to the repo — same URLs as in the table above, ROBOFLOW_API_KEY still
  valid) and matched every one of the 1,022 currently-kept manhole images back to
  its original label by filename stem. All 1,022 matched with zero ambiguity.
  **Real bug caught and fixed during this process**: the first classification pass
  used each image's *full* original label set, but `merge_datasets.py`'s
  `SOURCE_CLASS_KEEP_FILTER` had already dropped any "Good"/"Lose" boxes for the
  `manhole_cover` source at merge time — so an image with both a dropped "Good" box
  and a surviving "Uncovered" box was wrongly bucketed as "closed" (31 images, later
  found to be a mistake) instead of "open" (correct — the "Good" box never actually
  made it into data/unified). Fixed by intersecting each image's original classes
  with the filter's actual surviving keywords before classifying, re-verified by
  cross-checking against the real box count in each current unified label file, then
  spot-checked 9 images across all 3 buckets after the fix — all correct this time.
  **Result: open=811, broken=207, closed=4.**
  **Data-quality finding worth acting on**: the 4 "closed" images are ones whose
  *only* surviving box is labeled "Manhole" (i.e. an intact/covered manhole, not a
  hazard) — from `open_manholes`, which unlike `manhole_cover` was merged with no
  filter at all, so its "Manhole" (non-hazard) boxes went into the
  `manhole_open_broken` training class alongside the real "Open-Manholes" hazard
  boxes. These 4 arguably shouldn't be training positives for the hazard class —
  flagged to the user, not yet removed from data/unified.

## 2026-08-29 15:51 IST — billboard_hoarding: removed user's 52 explicit discards

- Collector: Pawan (`pawan_billboard_` prefix, currently the only billboard_hoarding source)
- Action: removed
- Notes: user did a manual partial review pass on billboard_hoarding in
  `review_tool.py` (44 keep, 52 discard, 416 not-yet-reviewed out of 512 total).
  User also reported suspected bounding-box misalignment on this class and asked
  whether it was a mistake on my end. Investigated by rendering 14 sample images (6
  keep + 8 discard) with boxes/polygons drawn — **all 14 were correctly aligned**.
  One looked box-less at first glance but turned out to be a red-outline-on-red-signage
  contrast issue in my own diagnostic script (re-rendered in high-contrast colors,
  confirmed all 8 polygons on that image were correct) — not a real annotation bug,
  and not something review_tool.py's own UI would show anyway since it draws boxes
  in green, not red. No genuine misalignment found in the sample checked; asked user
  for a specific example if they can point to one.
  Clarified scope before acting (user's phrasing was ambiguous between "keep only the
  44 marked keep" vs "remove only the 52 marked discard") — user chose the latter,
  so the 416 unreviewed billboard images were left untouched, consistent with every
  other class this session.
- **billboard_hoarding: 512 → 460 images.** Total unified dataset: 16,470 → 16,418.

## 2026-08-29 15:33 IST — Cross-source duplicate images removed (all classes)

- Action: removed (deduplicated)
- Method: difference-hash (dHash, 8×8 grid) computed for every image in data/unified;
  grouped by exact hash match per class; every affected class spot-checked visually
  (8 samples across pothole/garbage_pile/manhole_open_broken/streetlight_pole/
  billboard_hoarding, 100% confirmed true duplicates — including cases where
  filenames were completely different but pixel content was identical, e.g.
  `ashrith_garbage_waste_train_images131` == `ashrith_garbage_waste_train_basura203`).
  For the cattle class only, a full pairwise Hamming-distance scan (not just exact
  match) was run first and presented as an artifact before removal, per user request.
- Removed per class (kept 1 image per duplicate group, removed the rest):
  | class | removed | remaining |
  |---|---:|---:|
  | pothole | 1,462 | 3,542 |
  | garbage_pile | 863 | 8,196 |
  | manhole_open_broken | 537 | 1,022 |
  | streetlight_pole | 154 | 3,100 |
  | billboard_hoarding | 122 | 512 |
  | cattle | 9 (removed in a separate pass just before this one) | 39 |
  | encroachment | 0 (none found) | 59 |
- Notes: root causes of duplication, confirmed by inspection: (1) the same public
  photo present in two independently-collected sources — e.g. Prince's
  `manhole_cover` and Rahul's `Manhole Cover Dataset` are the same underlying
  Roboflow project (`create-dataset-for-yolo/manhole-cover-dataset-yolo`),
  independently re-downloaded by two people; Prince's `taco` and `trash_detection`
  overlap in underlying TACO-sourced images. (2) `streetlight` (dashcam video
  frames) had near-static duplicate frames during stationary moments — one cluster
  had 24 near-identical frames. (3) A handful of exact re-uploads within a single
  self-collected source (ashrith's garbage set) under different filenames.
  **Total unified dataset: 19,608 → 16,470 images** (a ~16% reduction). Duplicate
  removal ran on the composition as of the street_vendors revision and the two
  no_used deletions earlier the same day — see the two entries above for that
  lineage.

## 2026-08-29 14:45 IST — Archived (not_used) data permanently deleted

- Action: removed
- Where it lived: `data/not_used/` (1.1G — billboard, footpath_guide, illegal_parking,
  illegal_parking_v2, lamp_detector, street_vendors) and `Data Collection/not_used/`
  (2.7G — Pawan's cattle_cow_buffalo/Goats/hen, Rahul's Cow Detection/road_damage_data/
  TACO-trash-data)
- Notes: user explicitly confirmed permanent deletion (not just archival) to reclaim
  3.8GB. Source names/links/licenses for everything deleted are preserved in the
  entries above and in `class_review.json`'s remarks — if any of these are ever wanted
  again, they'd need to be re-downloaded from their recorded Roboflow/Mendeley links,
  not restored from disk. `dataset_dashboard.py` still references these paths for
  discarded classes; they now correctly resolve to 0 items (verified, no crash) since
  `scan_yolo_split` handles missing directories gracefully — the keep/discard decision
  and remark for each class are still visible in the dashboard even though the pixel
  data is gone.

## 2026-08-29 13:20 IST — Revised decision: Prince's street_vendors discarded

- Collector: Prince
- Dataset: `data/raw/street_vendors` (Roboflow `public-2mrlb/street-vendors`, https://universe.roboflow.com/public-2mrlb/street-vendors/dataset/2, CC BY 4.0)
- Class(es): was encroachment, now discarded — user narrowed Prince's encroachment source to `street_vendors_india` only
- Action: moved + removed from data/unified
- Where it lives now: `data/not_used/street_vendors` (495 images, untouched, just archived)
- Notes: **encroachment shrank hard as a result — 554 → 59 images (140 boxes) in data/unified.**
  ashrith's `encroachment_detected` still has 0 label files, so `street_vendors_india`
  (59 images) is now the *only* contributor to this class. This is a big step down from
  the 621-image encroachment set that got AP50 from 0.00→0.35 in the 2026-08-26 retrain
  (see civic_monitor_project_status memory) — flagged to user, not silently accepted.
  `data/merge_datasets.py` TARGET_CLASS_BY_KEY no longer has a `street_vendors` entry
  (only `street_vendors_india` remains). `class_review.json` updated via dashboard API;
  `dataset_dashboard.py`'s Prince::street_vendors now points at the archived path.

## 2026-08-29 13:09 IST — Initial classwise keep/discard pass + merge into data/unified

Source of truth for this pass: `class_review.json` (via `dataset_dashboard.py`,
http://127.0.0.1:8060) — the per-class Keep/Discard/Unsure decisions made together
in this session, then executed by `data/merge_datasets.py`.

### Kept classes (merged into data/unified/, remapped to the 7-class scheme)

| Collector | Dataset / folder | Source link | License | → Unified class |
|---|---|---|---|---|
| Prince | `data/raw/taco` | https://universe.roboflow.com/mohamed-traore-2ekkp/taco-trash-annotations-in-context/dataset/16 | CC BY 4.0 | garbage_pile |
| Prince | `data/raw/trash_detection` | https://universe.roboflow.com/yolo-hfplh/trash-detection-1fjjc-nd1dg/dataset/1 | CC BY 4.0 | garbage_pile |
| Prince | `data/raw/pothole_intel` | https://universe.roboflow.com/intel-unnati-training-program/pothole-detection-bqu6s/dataset/9 | MIT | pothole |
| Prince | `data/raw/open_manholes` | https://universe.roboflow.com/aibased-solution-for-realtime-detection-of-road-anomalies-d6eay/open-manholes/dataset/1 | CC BY 4.0 | manhole_open_broken |
| Prince | `data/raw/manhole_broken_v2` | https://universe.roboflow.com/2nd-workspace/manhole-broken/dataset/7 | CC BY 4.0 | manhole_open_broken |
| Prince | `data/raw/manhole_cover` (filtered: Broken/Uncovered only) | https://universe.roboflow.com/create-dataset-for-yolo/manhole-cover-dataset-yolo/dataset/1 | CC BY 4.0 | manhole_open_broken |
| Prince | `data/raw/streetlight` | https://universe.roboflow.com/sashank-s/street-light/dataset/1 | CC BY 4.0 | streetlight_pole |
| Prince | `data/raw/street_vendors` | https://universe.roboflow.com/public-2mrlb/street-vendors/dataset/2 | CC BY 4.0 | encroachment |
| Prince | `data/raw/street_vendors_india` | https://universe.roboflow.com/mit-f83x1/street-vendors-india/dataset/1 | CC BY 4.0 | encroachment |
| Prince | `data/raw/dats2022_cattle` (consumed by `add_cattle_road_sources.py`, folder no longer present) | Mendeley DATS_2022 — https://data.mendeley.com/datasets/nfc34n8svj/2 | CC BY 4.0 | cattle |
| Prince | `data/raw/indian_roads_cattle` (consumed by `add_cattle_road_sources.py`, folder no longer present) | Roboflow `indian-road-dataset/indian-roads-detection` v2 | Unconfirmed | cattle |
| Pawan | `Data Collection/Pawan/Pavan/bill_board_&_hoarding` | self-collected / unknown (no data.yaml) | — | billboard_hoarding |
| Pawan | `Data Collection/Pawan/Pavan/Street Light Night` | self-collected / unknown (no data.yaml) | — | streetlight_pole |
| ashrith | `Data Collection/ashrith/ASHRITH/raw/images/garbage_detected` | self-collected phone photos (no data.yaml) | — | garbage_pile |
| ashrith | `Data Collection/ashrith/ASHRITH/raw/images/pothole_detected` | self-collected phone photos (no data.yaml) | — | pothole |
| ashrith | `Data Collection/ashrith/ASHRITH/raw/images/drain_opened` | self-collected phone photos (no data.yaml) | — | manhole_open_broken |
| ashrith | `Data Collection/ashrith/ASHRITH/raw/images/drain_closed` | self-collected phone photos (no data.yaml) | — | **kept but not merged** — represents the non-hazard/negative case, no unified class to map to |
| ashrith | `Data Collection/ashrith/ASHRITH/raw/images/encroachment_detected` | self-collected phone photos (no data.yaml) | — | encroachment — **0 label files, contributes nothing until annotated** |
| Rahul | `Data Collection/Rahul/.../Damaged Lights.v1i.yolov5pytorch` (filtered: "Not Working" only) | https://universe.roboflow.com/godspeed-yqpeo/damaged-lights | CC BY 4.0 | streetlight_pole |
| Rahul | `Data Collection/Rahul/.../Manhole Cover Dataset YOLO.v1i.yolov5pytorch` (filtered: Broken/Uncovered only) | https://universe.roboflow.com/create-dataset-for-yolo/manhole-cover-dataset-yolo/dataset/1 (same source as Prince's `manhole_cover`, independently re-collected) | CC BY 4.0 | manhole_open_broken |

### Discarded classes (moved to `not_used`, excluded from data/unified)

| Collector | Dataset / folder | Moved to | Reason |
|---|---|---|---|
| Prince | `data/raw/billboard` | `data/not_used/billboard` | superseded by Pawan's billboard/hoarding |
| Prince | `data/raw/footpath_guide` | `data/not_used/footpath_guide` | not selected |
| Prince | `data/raw/illegal_parking` | `data/not_used/illegal_parking` | not selected (only 2 images anyway) |
| Prince | `data/raw/illegal_parking_v2` | `data/not_used/illegal_parking_v2` | not selected |
| Prince | `data/raw/lamp_detector` | `data/not_used/lamp_detector` | not selected |
| Pawan | `cattle/cow_buffalo` | `Data Collection/not_used/Pawan/cattle_cow_buffalo` | cattle class not sourced from Pawan (using Prince's vetted road-scene cattle instead) |
| Pawan | `cattle/Goats` | `Data Collection/not_used/Pawan/cattle_Goats` | same as above |
| Pawan | `cattle/hen` | `Data Collection/not_used/Pawan/cattle_hen` | same as above — also not a target class in the 7-class scheme |
| Rahul | `Cow Detection.v1i.yolov5pytorch` | `Data Collection/not_used/Rahul/Cow Detection.v1i.yolov5pytorch` | not selected |
| Rahul | `road_damage_data` | `Data Collection/not_used/Rahul/road_damage_data` | not selected |
| Rahul | `TACO-trash-data` | `Data Collection/not_used/Rahul/TACO-trash-data` | not selected — Prince's `taco` used instead |

### Result
- `data/unified/` rebuilt: 20,136 images across the 7 unified classes (see composition table shared earlier).
- `data/unified_classwise/<class_name>/{train,val}/{images,labels}` added as a hardlinked per-class view (zero extra disk space).
- Full per-class keep/discard decisions + free-text remarks: `class_review.json` (browsable via `dataset_dashboard.py`, http://127.0.0.1:8060).

## 2026-08-31 IST — India-restricted pothole sources added; several "Indian" candidates researched and rejected

- Collector: Prince (new Roboflow downloads)
- Action: added
- Class(es): pothole
- Sources added:
  - `data/raw/indian_road_potholes` → Roboflow `project-o3ot9/indian-road-potholes` v5.
    4,306 images merged. Visually confirmed genuinely Indian (scooters, whitewashed
    compound walls, Indian apartment-block architecture, palm-lined streets).
  - `data/raw/bharat_pothole` → Roboflow `bharat-ai-soc-challenge/pothole-detector-n0swk`
    v5, **pruned to only the 784 `India_*`-prefixed images** before merging (the
    other ~2,000 images in this project are NOT Indian — one sampled frame was
    unmistakably Rome, Italy). Of those 784, 52 had `pothole`-class boxes (filtered
    via `SOURCE_CLASS_KEEP_FILTER`, keyword "pothole") and were merged. Confirmed
    genuinely Indian via sample (auto-rickshaw, Indian truck design, Indian roadside
    signage).
- Where it lives now: `data/raw/indian_road_potholes/`, `data/raw/bharat_pothole/`
  (pruned), merged into `data/unified`.
- Result: pothole class 3,542 → 7,900 images. Unified dataset: 16,418 → 20,776.
- **Not yet retrained** — the S24 phone still runs civic_services-3.

### Candidates researched and explicitly rejected (do not re-suggest without new evidence)

| Candidate | Why rejected |
|---|---|
| `indian-institute-of-technology-madras-xamot/pothole-detection-huf2x` ("iitm_pothole") | Despite IIT Madras branding, sampled images show what looks like a South African/African township storefront ("Plaza Superette Take Away & Bakery") — not India. Downloaded, sample-checked, deleted. |
| `project-iqlva/indian-potholes` ("iqlva_pothole") | Generic Dreamstime-watermarked stock photo despite "Indian" name — no location evidence, low quality. Downloaded, sample-checked, deleted. |
| `indian-road-dataset/indian-roads-detection` v7, for a new "Lamp Post"→streetlight_pole class | Same source already used (unconfirmed-India, per earlier log entry) for the existing cattle data. New sample-check of bus/truck images was inconclusive-to-negative (one bus looked Balkan/Turkish, not Indian). Not trustworthy enough to add a *new* class from — downloaded, sample-checked, deleted. |
| `sakshi-kumari-70uxi/cow-indian` | This is the exact same project already rejected on 2026-08-25/26 for being tight face/nose crops, not whole-animal road photos. Re-surfaced by a research pass that didn't cross-check history — not re-added. |
| `pib-e46kr/indian-bovine` | 22-breed cattle classification dataset (Gir, Sahiwal, Tharparkar, etc.) — sample-checked, confirmed to be close-up farm/breed-showcase photography, not road scenes. Off-context for "cattle on road" detection, same failure mode as cow-indian. Downloaded, sample-checked, deleted. |
| Kaggle "Waste Management and Recycling in Indian Cities" (garbage) | Not attempted — no Kaggle credentials configured in this environment, and the title suggests it may be tabular/stats data rather than images. Needs Kaggle API key + manual verification before use. |
| `pothole-fw8hn/street_light-0wrmn` (streetlight) | Roboflow API returned `classes={}` (empty/inconclusive) and no independent India evidence was found — not pursued. |
| Billboard/hoarding, encroachment | No credibly India-specific candidate found for either class after a real search pass — these remain the weakest classes and need self-collection, not more dataset search. |

**Lesson for future dataset research**: a dataset's title/workspace/institution name ("Indian", "Bharat", "IIT Madras") is not reliable evidence of actual content origin — several candidates with confident-sounding names turned out to be non-Indian or mixed-origin on visual inspection. Always sample-check actual images (multiple, random) before merging, not just the project metadata. Also always cross-check new "candidates" against this log first — a fresh research pass re-surfaced a dataset already tried and rejected in an earlier session.

## 2026-08-31 (later) IST — Deeper per-class India research: billboard, encroachment, streetlight added

Previous entry only covered pothole. User correctly pushed back that the research
needed to actually cover all 7 classes, not stop after the first success. Redid the
search per-class (Roboflow API + GitHub + Kaggle), verifying every candidate by
downloading and visually inspecting sample images (title/workspace names proved
repeatedly unreliable — see rejections below).

### Added

- **Billboard/hoarding**: `data/raw/advision_ooh_detection` → Roboflow
  `advision/ooh-detection` v9. Filtered via keyword `["hoarding","billboard","gantry"]`
  → `billboard_hoarding` (excludes their `logo-branding`/`bus-advertising`/
  `car-advertising`/`amts-bus-shelter-board`/`wall-led` classes as too far from the
  target definition). 316 images merged. **Confirmed genuinely Indian**: 360°
  scooter-cam footage down CG Road, Ahmedabad — Indian vehicles, Devanagari/English
  mixed signage, "Money Changer" shop visible, filenames literally say "CGRoad".
  Class taxonomy itself (AMTS = Ahmedabad Municipal Transport Service) is
  India-specific by construction. billboard_hoarding: 460 → 776 images.

- **Encroachment**: `data/raw/vendor_footpath_guide2` → Roboflow
  `vendor/footpath-guide-2` v6. Filtered via keyword `["vendor"]` → `encroachment`
  (Vendor + Vendor cart classes; excluded the more generic "Obstacle" class to avoid
  diluting the hazard definition with tree branches/debris). 154 images merged.
  **Confirmed genuinely Indian** via sample images: palm-lined residential streets,
  Indian black/yellow-striped utility poles, auto-rickshaws, one sample shows a
  vendor cart under a tarp directly on the footpath. This is a different/larger
  project (395 images, 6 versions) from the "footpath_guide" already discarded on
  2026-08-29 — same family of project but not the identical dataset. encroachment:
  59 → 213 images.

- **Streetlight (NEW DATA TYPE — not yet merged into data/unified)**:
  `data/raw/streetlight_chennai/{Working,NotWorking}` — 718 images (444 working, 274
  not working) scraped from GitHub `Team16Project/Street-Light-Dataset` (companion
  data to arXiv:2407.01117, "Comprehensive Dataset for Urban Streetlight Analysis").
  Real high-res photos of individual streetlight fixtures taken across Chennai,
  India, pre-labeled functional vs non-functional. **Confirmed genuinely Indian**
  via sample images (tropical vegetation, hazy urban sky, Indian municipal
  streetlight fixture design). **This is classification-format data (whole-image
  label, no bounding boxes)** — cannot be merged via `merge_datasets.py`'s box-remap
  pipeline as-is. It directly fills a gap flagged repeatedly in project memory: the
  project has never had a real lit/unlit dataset, only an untrained brightness
  heuristic (`streetlight/classify_lit_state.py`). **Needs a follow-up decision**:
  either (a) train a small separate working/not-working image classifier on this set
  to replace the brightness heuristic, or (b) hand-box a subset to add as detection
  training data. Not actioned yet — flagging for next session.

### Classwise folders — `data/india_datasets/<class>/`

```
data/india_datasets/
├── pothole/{indian_road_potholes, bharat_pothole}
├── encroachment/vendor_footpath_guide2
├── billboard_hoarding/advision_ooh_detection
└── streetlight_pole/streetlight_chennai_working_notworking
```
Each entry is a symlink to the corresponding `data/raw/<key>/` download (single
source of truth, no duplication). Per explicit user instruction, this folder is
**kept separate from `review_tool.py`** — not wired into the dashboard as a
sub-view, unlike the earlier manhole open/broken/closed precedent.

### Result
Unified dataset: 16,418 → 21,246 images. Per-class: garbage_pile 8,196 (unchanged),
pothole 7,900 (was 3,542), manhole_open_broken 1,022 (unchanged), streetlight_pole
3,100 (unchanged — new data is classifier-format, not yet merged), encroachment 213
(was 59), billboard_hoarding 776 (was 460), cattle 39 (unchanged).
**Not yet retrained.**

### Still no credible India-specific candidate found (after real effort, not just skipped)

| Class | What was tried | Why nothing was added |
|---|---|---|
| Garbage | Searched Roboflow (`smart-india-hackathon-2023/final-garbage`, `garbage_best`), Kaggle ("Waste Management and Recycling in Indian Cities") | `final-garbage`'s sample thumbnail is a Bigstock stock photo of **Indonesian** grocery brands (Sedaap, Sosa) despite the "Smart India Hackathon" workspace name — rejected. `garbage_best` has messy mixed-language classes (`sampah-detection` = Indonesian for garbage, stray `ç` class) — same contamination pattern, not trusted. The Kaggle set could not be verified — **no Kaggle API credentials configured in this environment**, and page-scraping couldn't confirm it's even image data (title suggests it may be statistics/CSV). Needs a Kaggle account + manual check next session. |
| Manhole | Checked `bharat-ai-soc-challenge/pothole-detector-n0swk`'s "manhole" class (954 instances, mixed into the India-confirmed pothole source) and the Indian Driving Dataset (IDD)'s semantic-segmentation manhole class | Bharat AI SoC's manhole boxes don't distinguish open/broken vs closed/intact — same contamination risk already flagged for the existing `manhole_closed` bucket, so not merged without state info. IDD explicitly lists manhole as one of its "underrepresented" classes (segmentation format, would need conversion) — not pursued given low expected yield. |
| Cattle | Checked `pib-e46kr/indian-bovine` (govt PIB workspace, 22 breed classes) and re-found `sakshi-kumari-70uxi/cow-indian` | `indian-bovine` sample-confirmed to be close-up farm/breed-showcase photography (filenames like "Tharparkar_99"), not road scenes — same off-context failure as the already-rejected cow-indian face-crop set. `cow-indian` **is** that already-rejected set (2026-08-25/26) — a research pass re-surfaced it without cross-checking this log. Existing cattle source (AP50 0.986) remains best. |

**Lesson reinforced**: dataset title/workspace/institution branding ("Smart India
Hackathon", "IIT Madras", "Bharat AI SoC") is not reliable evidence of genuine
Indian imagery — this session found confidently-named datasets that were actually
Indonesian, South African/other, or generic stock photos. Every candidate in this
log was accepted or rejected based on actually opening sample images, not metadata.

## 2026-08-31 (later) IST — Removed obsolete dataset_dashboard.py

- Action: removed
- Where it lived: `dataset_dashboard.py` (repo root, port 8060)
- Notes: not running, not used by training or `review_tool.py`. It had been dead
  since the 2026-08-29 permanent deletion of `data/raw/`'s collector source folders
  and `Data Collection/` — it only ever showed 0 items per class after that point.
  `class_review.json` (its decisions file) is left in place as historical record but
  is now unused by any running tool. Also deleted `data/unified_classwise/` this
  session (stale hardlinked per-class view, not referenced by training — see prior
  entries; it was never refreshed after this session's merges, so its counts were
  wrong).

## 2026-09-02 IST — Kaggle credentials now working; re-attempted garbage/manhole India search, staged to `data/new_review_data/` (NOT yet merged into data/unified)

Kaggle API credentials were configured for the first time this session (prior
sessions could not use Kaggle at all — see the 2026-08-31 "still no candidate"
table). Re-attempted the specific garbage/manhole leads that were previously
blocked on missing credentials, plus a fresh round of Kaggle/Roboflow search for
both classes. Per the file-review workflow now in use, everything accepted was
staged into `data/new_review_data/<class>/{images,labels}/` (flat, prefixed
`newsrc_...`) rather than merged directly — not yet reviewed in the dashboard or
pulled into `data/unified`.

### Added — garbage_pile (+248 images)

- **DataCluster Labs `dataclusterlabs/domestic-trash-garbage-dataset`** (Kaggle,
  "Domestic Trash / Garbage Dataset", license `copyright-authors`, public sample of
  a larger paid dataset). Downloaded the full public zip (885MB, 250 images / 248
  Pascal-VOC XML annotations, single class `Domestic Trash	Garbage`). Converted all
  248 XML annotations to YOLO (`class 0 = garbage_pile`, box coords normalized from
  each XML's own `<size>`), keeping images with >=1 resulting box. **Confirmed
  genuinely Indian** by sampling ~20 images: a "Tata Tea Premium" packet with
  "INDIA" printed on the pack, a roadside chai-stall scene (glass tumbler of tea,
  biscuits, a folded Indian-language newspaper, rubber chappals), a yellow/black
  striped curb post (standard Indian road-curb paint convention), plus generic
  Colgate/other packaging consistent with Indian retail. Most images are
  extreme-closeup ground-level shots of litter (bottles, wrappers, food waste) —
  boxes are mostly tight single-item crops rather than large (>1m) pile regions,
  same item-level annotation style already present in the existing `taco` /
  `trash_detection` sources for this class, so kept for consistency with precedent.
  6 of the 248 images have 2 boxes; the rest have 1.
  Copied to `data/new_review_data/garbage_pile/images|labels/` with prefix
  `newsrc_dclindtrash_`. Raw zip/extract deleted from scratch after conversion.
- **garbage_pile: 7,847 → 8,095 files in `new_review_data`** (staged, not yet in
  `data/unified`).

### Added — manhole_open_broken (+1 image — see rejection below for why so few)

- One image hand-verified from the CMIRD source below:
  `newsrc_cmird_video_12_frame_000004.jpg` — a genuine open/broken manhole (a dark,
  jagged-edged hole in a footpath slab, cracked concrete rim, clearly not a closed
  cover) shot from a moving two-wheeler on a street in Thiruvananthapuram, Kerala
  (Malayalam shop signage, "GOLD LOAN"/"HEART CLINIC" boards, Kerala-registration
  bus KL15... visible in frame — unambiguously Indian). The source image had a
  second `manhole`-class box in the same frame (a light rectangular patch near a
  parked bus) that was **excluded** — on inspection it was ambiguous/likely a
  closed patch, not clearly open or broken, so only the one verified hazard box was
  kept (label file has exactly 1 line, remapped to class `2 = manhole_open_broken`).
  Copied to `data/new_review_data/manhole_open_broken/images|labels/` with prefix
  `newsrc_cmird_`.
- **manhole_open_broken: 511 → 512 files in `new_review_data`** (staged, not yet in
  `data/unified`). Still the weakest class by a wide margin — see rejection below,
  this remains an open problem.

### Rejected — garbage_pile

| Candidate | Why rejected |
|---|---|
| Kaggle `krishnayadav456wrsty/waste-management-and-recycling-in-indian-cities` (the exact dataset flagged in the 2026-08-31 log as "needs Kaggle credentials to check") | Now checked with working credentials: it is **3 CSV files** (`Waste_Management_India_20K.csv`, a smaller CSV, `cities_master.csv`) — tabular statistics, no images at all. Confirms the 2026-08-31 suspicion. Not an image dataset, cannot be used. |
| Kaggle `xixama/waste-management-and-recycling-india-cleaned` | Same underlying tabular dataset ("cleaned" version), also CSV-only. Not checked further given the above. |
| Kaggle `shohomde/dmc-project` ("Garbage detection Dataset on an Indian Campus", IITK Signalsprint 2026 hackathon entry) | Rejected from metadata alone (no download needed): author's own description says it is a **mix of real and AI-generated (ChatGPT-produced) images**, scaled from ~150 real photos to 4,000+ via augmentation/AI generation, for a binary clean/spill **classification** task (no bounding boxes) — fails on format (not detection), fails on authenticity (explicitly synthetic images mixed in), and the author self-describes it as "very weak and not diverse". |
| Kaggle `rajeevpaudel1/urban-community-issues` ("Urban Community Issues") | Sampled file listing shows an `animal/` folder of images with Open-Images-style hex-hash filenames (e.g. `005cbd1f2b3e2b8b.jpg`) — a strong signature of scraped/aggregated Open Images content, not original India-specific capture. Not downloaded given this signal; no India evidence pursued further. |
| Kaggle `ammanaveen/custom-multitask-indian-road-dataset-cmird` for garbage | This dataset's 10 detection classes (see manhole section below) do not include any garbage/trash/litter class — only vehicles + pothole/crack/manhole/speed-bump/waterlogging road anomalies. Not applicable to garbage_pile. |

### Rejected / mostly-rejected — manhole_open_broken

- **`ammanaveen/custom-multitask-indian-road-dataset-cmird`** (Kaggle, "Custom
  Multitask Indian Road Dataset (CMIRD)", CC-BY-NC-SA-4.0, 3,350 GoPro dashcam
  images from Thiruvananthapuram (Kerala) and Nagercoil (Tamil Nadu), 10-class
  detection incl. a `manhole` class, 268 total manhole-class box instances across
  train+val). **Genuinely and strongly Indian** (GoPro dashcam footage, Malayalam/
  Tamil signage, KL/TN plates, auto-rickshaws, temples) — but on exhaustive visual
  inspection (rendered and reviewed all 268 `manhole`-class boxes as contact
  sheets, full images, plus an automated darkness-heuristic pass to surface the
  most likely "open/dark-hole" candidates for closer review) **the overwhelming
  majority (267 of 268) are closed/intact manhole covers, or storm-drain grates**,
  i.e. exactly the "manhole ≠ open/broken manhole" contamination risk already
  flagged in this log for the Bharat AI SoC pothole-detector's manhole class and
  for IDD. The class simply was not annotated with an open/closed distinction.
  Only **one** genuine open/broken example was found and hand-picked (see "Added"
  above); bulk-merging the class was rejected as it would inject ~267 wrong-label
  negatives into a hazard-detection class. Not pursued further for pothole/crack/
  waterlogging either in this pass (out of scope this session).
- Kaggle searches "manhole india", "open manhole", "manhole detection" otherwise
  turned up only generic/global road-damage datasets with no India-specific claim
  or evidence (`lorenzoarcioni/road-damage-dataset-potholes-cracks-and-manholes`,
  `notitltd/demo-utilitymanhole-detection-5-crops-and-data`,
  `mcii34/*-utilities-detection-*`, `uzbtrust/smartroad-yolo`, etc.) — not
  downloaded, no India claim in title/description to even test against the
  "verify by eye" bar.

### Lesson reinforced
Kaggle access changed the *reach* of the search (found CMIRD and the DataCluster
Labs set, neither previously visible) but not the *bar* — CMIRD's own title/
description ("Indian Road Dataset") was completely genuine about being Indian
footage, and still failed the class-specific check (open vs. closed manhole) that
matters for this project. Verifying "is this image from India" and verifying "is
this box the hazard state we actually want" are two independent checks; a source
can legitimately pass the first and fail the second.

## 2026-09-02 (later) IST — streetlight_pole/encroachment/billboard_hoarding: new Roboflow government-audit sources merged; Chennai classification conversion attempted and rejected

Focus of this pass: the three classes flagged as thinnest/newest in prior entries —
`encroachment` (only ~5 files in `new_review_data` going in), `billboard_hoarding`,
and `streetlight_pole` (specifically the non-working state per the problem
statement). All additions verified by opening multiple sample images per source,
not by title — see rejections below for cases where a promising-sounding title did
not survive that check. All additions staged to `data/new_review_data/<class>/` only
(flat images/labels dirs, YOLO `.txt`), **not yet merged into `data/unified`**.

### Added

Found via a Roboflow Universe web-search pass for `class:encroachment` / `class:hoarding`,
which surfaced several unrelated-looking workspace names (`pwd3601`-`pwd3605`, `pot1`,
`pot2`, `nithiyas-workspace/hydraa`, `sofikaws/hydraa-ohwet`) that turned out to be real
Indian government/PWD (Public Works Department) road-condition-audit AI training
projects — the taxonomy (`RUTTING`, `RAVELLING`, `KERB`, `HOTSPOT`, `GANTRY-BOARD`,
`UNAUTHORISED-BOARD`, `NON-FUNCTIONAL-STREET-LIGHT`) is standard Indian highway
maintenance/road-safety-audit terminology, and "HYDRAA" is a real Telangana state
government body (Hyderabad Disaster Response and Assets Protection Agency, tasked with
removing encroachments). **Confirmed genuinely Indian** on every source by opening
multiple sample images: Telangana ("TS..") motorbike plate + Hyderabad apartment-block
skyline (hydraa), a "भारत"/Hindi hazmat tanker + "Eyes on Bharat" watermark + Devanagari
highway gantry sign reading "Mahagunpuram / Wave City / Lal Kuan" (Ghaziabad, UP) on
`pot2/n_1-yln2j`, and a Maharashtra ("MH12..") number-plate car + Devanagari shop/bridge
signage + a visible dashcam windshield-wiper on `pwd3601/p_3-xewio`.

| Source | Roboflow project | License | Source class(es) kept | → unified class | Images added |
|---|---|---|---|---|---|
| `nithiyas-workspace/hydraa` v1 | https://universe.roboflow.com/nithiyas-workspace/hydraa | CC BY 4.0 | `Encroachment` | encroachment | 391 |
| `sofikaws/hydraa-ohwet` v1 | https://universe.roboflow.com/sofikaws/hydraa-ohwet | CC BY 4.0 | `encroachment` (polygon/seg format — converted to bbox by taking min/max of each polygon's points) | encroachment | 210 |
| `pwd3601/p_3-xewio` v2 | https://universe.roboflow.com/pwd3601/p_3-xewio | CC BY 4.0 | `ENCROACHMENT` | encroachment | 22 |
| `pwd3601/p_3-xewio` v2 | (same) | CC BY 4.0 | `DAMAGED-STREET-LIGHT` | streetlight_pole | 45 |
| `pwd3601/p_3-xewio` v2 | (same) | CC BY 4.0 | `UNAUTHORISED-BOARD` | billboard_hoarding | 121 |
| `pot2/n_1-yln2j` v7 | https://universe.roboflow.com/pot2/n_1-yln2j | CC BY 4.0 | `NON-FUNCTIONAL-STREET-LIGHT` (polygon/seg format — converted to bbox) | streetlight_pole | 47 |
| `pot2/n_1-yln2j` v7 | (same) | CC BY 4.0 | `UNAUTHORISED-BOARD` (polygon/seg format — converted to bbox) | billboard_hoarding | 17 |

Filename prefixes used to avoid collisions: `hydraa1_`, `hydraa2_`, `pwd3601_`,
`pot2n1_`. Only images with ≥1 resulting box after class filtering were copied;
multi-class source images were filtered to keep only the target-class boxes (e.g. a
`pot2/n_1-yln2j` image with both a `NON-FUNCTIONAL-STREET-LIGHT` and an
`UNAUTHORISED-BOARD` box was copied once into each of the two class folders, each
copy's label containing only that folder's class). `GANTRY-BOARD` (also present in
these sources, 100+ instances) was deliberately **not** mapped to billboard_hoarding —
on inspection it mixes legitimate advertising boards with plain overhead directional/
informational road signage (e.g. the "Mahagunpuram / Wave City" highway sign), which
is not what "billboard/hoarding compliance" in the problem statement means;
`UNAUTHORISED-BOARD` is the semantically-correct, safer class for this project.
Generic `STREET-LIGHT` (no working-state info, thousands of instances across these
sources) was likewise not used — only the explicit non-functional/damaged classes,
per the task's requirement to detect *non-working* streetlights specifically.

Bounding-box sanity-checked by rendering boxes on 2 samples (one converted-from-polygon
encroachment box tightly bounding a tarp-roofed roadside stall; one converted-from-
polygon streetlight box correctly bounding a visibly-unlit fixture against a lit
background) before trusting the bulk conversion — both correct.

**Result**: `data/new_review_data/encroachment` 5 → 628 files; `streetlight_pole`
2,849 → 2,941; `billboard_hoarding` 390 → 528. Raw downloads (~3.3GB across the 3
Roboflow projects) deleted from `/tmp` after conversion, per instruction not to keep
large raw downloads.

### Streetlight (Chennai classification→detection conversion) — attempted, rejected

Per the standing gap noted in the 2026-08-31 entry, re-cloned
`github.com/Team16Project/Street-Light-Dataset` fresh into `/tmp` (the earlier
`data/india_datasets/` symlink to it no longer resolves — its `data/raw/` target was
deleted in the 2026-08-29 cleanup). Confirmed the "NotWorking" folder is still
present and still classification-format (`Raw Dataset/Not Working/`, 295 whole-image
files, no boxes).

Before bulk-applying the "central 60–80% box" heuristic suggested as a fallback,
sample-checked 8 images spanning both the WhatsApp-shared (`IMG-*-WA*.jpg`) and
phone-camera (`2024*.jpg`, `17*.jpg`) subsets. **The centered/dominant-fixture
framing assumption does not hold**: fixtures appear small and off-center in a
lower-left corner against mostly sky/cloud (`20240430_052112.jpg`), tiny at the top
of a portrait frame with a large empty-sky foreground (`IMG-20240228-WA0015.jpg`),
buried in cluttered tree foliage off-center (`IMG-20240303-WA0077.jpg`,
`20240305_192124.jpg`), or reduced to a small feature at the top of a wide
street-level night shot dominated by road/traffic/buildings
(`IMG-20240301-WA0003.jpg`). One sampled file (`1710175965876.jpg`) was not even a
streetlight photo — an unrelated close-up macro shot, i.e. the folder also has some
non-conforming/junk entries. A single central-box heuristic applied across this set
would produce boxes that mostly bound sky/foliage/road rather than the actual
fixture — exactly the "don't force it" case the task called out.

**Decision: did not bulk-convert.** No images from this dataset were added to
`data/new_review_data/streetlight_pole`. It remains genuinely and strongly
confirmed Indian (Chennai, tropical vegetation, Indian municipal fixture design)
and still the best available lit/unlit-labeled source, but needs real manual
bounding-box annotation (e.g. a quick pass in a tool like `labelImg`/`CVAT` over
the 295 NotWorking images) before it can contribute detection training data —
flagging for a future session rather than inventing boxes now. Re-cloned copy
deleted from `/tmp` after this check.

### Rejected candidates — encroachment / billboard_hoarding

| Candidate | Why rejected |
|---|---|
| Kaggle `caprolal/detect-footpath-vendors` ("Detect footpath vendors" v6, Roboflow-sourced, classes incl. `Vendors`, `Auto`, `Streel Light`) | Sample images show Bengali-script shop/wall signage and a cycle-rickshaw carrying a passenger — this is **Dhaka, Bangladesh**, not India (matches the pattern already seen with Bangladesh-named candidates in earlier sessions). Not the same project as the already-merged `vendor/footpath-guide-2`. Downloaded, sample-checked, deleted. |
| Kaggle `faysalahmedfahim/bdstreetvendors` ("BDStreetVendors") | Not downloaded — "BD" naming and author context strongly suggest Bangladesh, consistent with the sibling dataset above; not pursued given that confirmation elsewhere. |
| Roboflow `arslan-ongr8/billboard-xlvz1` v1 (9,823 `billboard`-class instances) | Large generic global billboard dataset — sampled images are an Abu Dhabi highway sign (Arabic/English), a Tokyo Kabukicho street (Japanese neon signage), and a Spanish lingerie-ad billboard ("Moda & Salud"). No India content found in samples. Downloaded, sample-checked, deleted. |
| Roboflow `billboarddetection/object_detection-noxg1` v6 (class literally named `"1"`) | Despite the workspace name, sampled images are close-up product barcodes and a QR code — this is a barcode/QR detection dataset mislabeled/misfiled under a "billboard" workspace name, completely unrelated content. Downloaded, sample-checked, deleted. |
| Kaggle `dataclusterlabs/ad-board` ("Advertisement Board Image", 213 raw crowd-sourced photos, CC0) | dataClusterLabs is a genuine India-based crowdsourcing company and at least one sample (a "Metro Tools" hardware-store hoarding, "A-111/112, Patel Super Market, Station Road, Bharuch") is confirmed Gujarat, India — but the dataset ships with **zero bounding-box annotations** (only a flat image list + a Firebase-URL manifest), and framing is inconsistent (one sample was a "Billboard Mockup" stock-photo screenshot, i.e. junk; another was a torn flyer nailed to a tree, not a hoarding). Same "don't force it" logic as the Chennai streetlight case — hand-annotating ~200 raw photos was out of scope for this pass. Not added; flagged as a manual-annotation candidate for later, not a data-search dead end. |
| Roboflow `indian-road-dataset/indian-roads-detection` (`Cart`: 13 instances, `Board`/`Digital Display`: 131/4 instances) | Same source already flagged as unreliable in the 2026-08-31 entry (one sampled bus looked Balkan/Turkish, not Indian) and its classes here are too sparse (13 Cart instances total) or too semantically vague (`Board` could be any road sign, not specifically an advertising hoarding) to trust without much heavier re-verification. Not downloaded this pass. |
| Roboflow `capstone-*` "Capstone Obstacles" (`Hawker L`/`Hawker R` classes) | Its full class list includes `MRT`, `Town Council`, `Active Ageing Hub` — unambiguously **Singapore** government/transit terminology, not India. Not downloaded. |
| Zenodo/ScienceDirect "StreetVendor-SLI" dataset (2,794 images, fixed/semi-fixed/itinerant vendor classes, YOLO format) | Published by Universidad Nacional de Colombia — confirmed **Colombia**, not India, from the paper metadata alone. Not downloaded. |
| GitHub `lonlonago/Smart-City-Street-Vendor-Detection-Dataset...` (2,401 images, Pascal VOC + YOLO, `street-vendor` class) | Repo is a marketing/lead-gen page only (2 preview images + a Stripe paid-access link, $89) — no actual dataset files in the repo, no India claim evaluated since the real data isn't accessible without payment. Not pursued. |

### Result
`data/new_review_data/` per-class file counts (staged, not yet in `data/unified`):
encroachment 5 → **628**, streetlight_pole 2,849 → **2,941**, billboard_hoarding
390 → **528**. Not yet retrained; not yet reviewed in `review_annotate_dashboard.py`
(new files are automatically picked up by that tool's folder scan — no code change
needed, unlike the earlier `review_tool.py`/dashboard-visibility precedent).

## 2026-09-02 (later still) IST — pothole: RDD2022 India subset added (+717); cattle: new `new_review_data/cattle/` folder created, IDD "animal" superclass hand-filtered (+18)

Focus this pass: two more India-specific sources beyond everything already logged
(the 3 GitHub repos the user supplied were pre-rejected per this session's brief —
`Ritish330/Cattle-detection-` (no boxes), `jaygala24/pothole-detection` (confirmed
non-Indian), `project-ssayl/potholes-detection-d4rma` via `PeterHdd/pothole-detection-yolo`
(confirmed Mexico/US/snow) — not re-checked). Everything added was staged into
`data/new_review_data/<class>/{images,labels}/` only, YOLO format, filtered to the
target class and remapped to this project's ids (pothole=1, cattle=6). Raw downloads
(~1.7GB total across all candidates this pass) deleted from `/tmp` after conversion.
`review_annotate_dashboard.py`'s `QUEUE_CLASSES` dict was updated to add a `"cattle":
"cattle"` entry (previously only billboard_hoarding/encroachment/manhole_open_broken/
garbage_pile/pothole were wired in) — per the standing "new folder must be visible in
the running dashboard, not filesystem-only" lesson from the manhole precedent, since
`cattle/` did not exist in `new_review_data` before this session.

### Added — pothole (+717 images, 1,536 boxes)

- **Roboflow `siddhesh-onuvb/road-damage-detection-india` v2** (7,706 images total,
  CC BY 4.0) — this is a mirror of the **RDD2022 India country-split** (the
  academic Road Damage Detection dataset used in the CRDDC global road-damage
  challenges; classes are the standard RDD damage codes `D00/D01/D0w0/D10/D11/
  D20/D40/D43/D44/D50`, where `D40` = pothole). Filtered to keep only `D40`-class
  boxes → 717 of the 3,743 total images had ≥1 pothole box (1,536 boxes total,
  some images have multiple potholes). **Confirmed genuinely Indian**: filenames
  are literally `India_NNNNNN.jpg` (RDD's own per-country naming convention), and
  sample images show Indian-plate cars (a Maruti Suzuki Swift with a partial
  Indian plate), auto-rickshaws, a decorated Indian cargo truck, Indian-style
  raised road medians/curbs, and Indian traffic-signal pole design — all dashcam
  photos, real road context (not macro crops), several showing potholes 
  alongside visible traffic for scale. Copied with prefix `rddindia_`, one image
  per source stem (no augmentation was enabled on this project version, so no
  near-duplicate risk).
- **pothole: 7,395 → 8,112 files in `new_review_data`** (staged, not yet in
  `data/unified`).

### Added — cattle (+18 images, 29 boxes) — new folder created

`data/new_review_data/cattle/{images,labels}/` did not exist before this session
(the project's only prior cattle source is the fully-merged
`data/add_cattle_road_sources.py` pipeline already in `data/unified`, per project
memory). Created it and added a first small hand-verified batch:

- **IDD (Indian Driving Dataset) Roboflow mirrors** — IDD's own taxonomy lumps all
  non-human animals into one coarse `animal` class (confirmed by inspection: this
  class mixes cattle/buffalo with dogs, monkeys, birds/kites, and unidentifiable
  night crops — **not** usable as a bulk merge). Rather than bulk-filtering by
  class name (which would inject dogs mislabeled as cattle), sorted every
  `animal`-class box across two mirrors by bounding-box area (large/close boxes
  are overwhelmingly real cattle/buffalo; small/distant boxes are overwhelmingly
  birds or dogs — confirmed by rendering contact sheets at multiple area
  thresholds) and individually eyeballed every candidate box crop before keeping
  it. Sources:
  - `object-detection-ioglc/idd-de2sp` v1 (779 images) — 8 candidate images (all
    from 2 short multi-frame sequences of a buffalo herd standing/walking on a
    rural road with a truck approaching); 1 of the 8 (`0004860...`) was dropped
    after checking its label coordinates against the frame — the `animal` box in
    that specific image was a stray dog near parked bicycles, not the herd. 7
    kept, prefix `idddesp_`.
  - `xmltotxt-laixa/idd-os9ak` v1 (5,189 images, 767MB) — 527 images had ≥1
    `animal` box; sorted by max box area, individually inspected box crops for
    the top ~100 by area. Precision was high (~85%) in the top 40 and dropped off
    sharply below area≈0.009 (rank ~40), where dogs and unidentifiable dark/night
    crops start dominating — did not pursue further down the ranking given the
    yield/precision tradeoff. Also discovered and corrected for **within-image
    duplication**: this project version had 3x train-time augmentation enabled,
    so several source photos appear 2-3 times under different `.rf.<hash>` names
    (flipped/rotated) — deduplicated to one copy per original stem before adding.
    11 unique verified images kept (one, `0008161...`, had a second small
    mid-frame `animal` box that was ambiguous/likely a false positive near a
    pedestrian — excluded, kept only the confirmed cattle box), prefix
    `iddos9ak_`. One additional candidate (`0008904...`, 3 very dark tree-shadow
    boxes) was dropped for being too visually ambiguous to confirm by eye even
    though the location (tree-lined rural road) matched the others.
  Sample visual evidence across both sources: a buffalo tethered outside a shop
  with Kannada wall-text and a "SART-B" (speed-breaker) road sign, a cow standing
  next to a parked Maruti Suzuki with a visible partial Karnataka plate ("KA 01
  ..."), a herd of buffalo on a rural road with power-line poles and a person in
  the frame, a cow between two auto-rickshaws on a paved street, and a cow beside
  roadside garbage near motorcycles — all unambiguously Indian street/road scenes,
  the exact "cattle on road" scenario in the problem statement.
- **cattle: 0 → 18 files in `new_review_data`** (new folder; staged, not yet in
  `data/unified`, not yet reviewed in the dashboard).

### Rejected candidates — cattle

| Candidate | Why rejected |
|---|---|
| Roboflow `shaiks-workspace-i5jmj/india-road-20class` (COW: 262, BUFFALO: 258 instances) | Filenames and sample images confirmed this is a scrape of **watermarked Alamy stock photography** (visible "Alamy"/image-ID watermarks on every sampled image), not organic dashcam/road capture — one sample was genuinely an Indian street scene (cow lying on a road amid auto-rickshaws) but another sampled "BUFFALO"-class image was an **American bison at sunset** in what looks like a North American prairie, confirming the dataset is a contaminated, non-curated scrape unsuitable for training regardless of the occasional genuine Indian photo mixed in. Downloaded, sample-checked, deleted. |
| Roboflow `projects-btxjo/cattle-3ggtr` (`Cattle`: 26 instances, taxonomy incl. `Autorickshaw`/`Scooter` which looked promising) | All 27 source filenames are literally `istockphoto-<id>-612x612...jpg` — **iStock stock-photo previews** (612×612 is iStock's standard preview-image size). One sample was genuinely an Indian beach/tourist scene (Goa, cow with a tikka mark on its forehead) but the source is commercial stock photography, not organic capture, and too small (27 images) to be worth the copyright/contamination tradeoff. Downloaded, sample-checked, deleted. |
| Roboflow `nirma-university-cmc5a/buffalo-mgttx` v1 (dataset dominated by 19,571 `camel` instances; `buffalo`: 452, `Cow`: 36) | Despite the Indian-university workspace name (same "institution name ≠ Indian content" failure mode already logged repeatedly), the exported v1 (grayscale + Gaussian-blur preprocessing baked in) sample image is a **grayscale African cape buffalo in savanna grassland with palm trees**, watermarked "© Andy Murch / AnimalImages.net" — generic wildlife stock photography, not India, not road context. Downloaded, sample-checked, deleted. |
| Roboflow `sids-garage/buffalo-entkk` (`buffalo`: 2,032 instances, taxonomy incl. `gaur` (Indian bison) which looked promising) | Sample images are heavily rotated video-frame screenshots, one with a "WATCH NOW ▶" video-player UI overlay burned into the pixels (a screen-scrape from an embedded video player, not raw photography) and another showing what appears to be a wild African cape buffalo in marsh grassland — contaminated, non-curated mixed-origin scrape. Downloaded, sample-checked, deleted. |
| Roboflow `object-detection-dp5wa/yolo-v8-indian-roads-dataset` / its duplicate `multi-object-tracking/yolo-v8-indian-roads-dataset-fdkct` (`Animal`: 149 instances) | Genuinely an Indian-roads vehicle-tracking dataset overall, but its generic `Animal` class is contaminated the same way as IDD's: sampled `Animal`-class images included a **Rhesus macaque monkey** on a wall in Gokarna and an **African elephant on a dirt road with a "Finchley Collection" stock-photo watermark** — not filterable to cattle-only without the same expensive per-box manual review already done for IDD, and this source is smaller/less clean than IDD for that effort. Not pursued further. |
| Kaggle `atharvadarpude/indian-cattle-image-dataset` (2.4GB, "Indian Cattle Image Dataset") | File listing shows a `cattle/<BreedName>/*.jpg` folder structure (e.g. `cattle/Amritmahal/Amritmahal_1.JPG`) — same breed-classification-showcase format as the already-rejected `pib-e46kr/indian-bovine` and `cow-indian` sources (2026-08-31 log), no bounding boxes, no road context. Not downloaded, matches an established rejection pattern exactly. |
| GitHub `Priyansh7570/Cattle-breed-detection-yolov8` (Roboflow-exported, `cattle-ddm3j/cattle-zocu9`, 21 breed classes: Gir, Sahiwal, Murrah, Hallikar, etc.) | Same breed-classification failure mode — sample image (`Deoni_02.jpg`) is a tethered animal in a bare dirt farmyard with a model-inference box overlay already burned into the pixels (i.e. not even raw training data, a saved prediction screenshot), not a road scene. Downloaded one sample, confirmed, not pursued. |
| GitHub search for "cattle india road yolo" / "stray cattle detection" (`MrGladiator14/Enhancing-Road-Safety-Cattle-Detection-System-using-YOLOv8` and similar) | Checked the one repo with an on-topic name and description ("prevent traffic disruptions caused by cattle on roads") — it is application code only (Flask/Tkinter apps, email-alert scripts) built on a **stock pretrained `yolov8l.pt`/COCO model** (COCO's generic `cow` class), no custom dataset or annotations shipped. No usable training data. |
| Kaggle searches ("stray cattle detection", "cow detection yolo", `bsridevi/modes-dataset-of-stray-animals`) | No India-specific cattle-detection-with-boxes dataset found. `modes-dataset-of-stray-animals` turned out to be synthetic foreground/background depth-composite frames (`out2/depth/fgbg*.jpg`), unrelated to real cattle photography. |

### Rejected candidates — pothole

No new rejections this pass beyond what's already logged on 2026-08-31 — the RDD
India source above was the only new pothole candidate investigated and it passed.

### Lesson reinforced
The IDD "animal" superclass and several Roboflow "cattle/buffalo" projects looked
promising by title or class-list alone (`gaur`, `Autorickshaw`+`Cattle` taxonomy,
Indian-university workspace names) but needed **per-box visual inspection, not
just per-dataset** — several sources mixed genuine Indian cattle photos with dogs,
monkeys, or entirely non-Indian wildlife/stock content within the *same* class or
even the *same* image. Sorting by bounding-box area before manual review (large/
close boxes are real animals; tiny/distant boxes are much more likely birds or
noise) was an effective triage heuristic for the one source (IDD) worth the
per-box effort.

### Result
`data/new_review_data/` per-class file counts (staged, not yet in `data/unified`):
pothole **7,395 → 8,112**; cattle **0 → 18** (new folder). Not yet retrained; not
yet reviewed in `review_annotate_dashboard.py` (the dashboard's `QUEUE_CLASSES`
dict was updated to include `cattle` so the new folder is visible there, unlike a
filesystem-only drop).

## 2026-09-03 IST — Deep search for cattle-class diversity (cow/buffalo/goat/ox + young):
no new usable sources found

Goal: `cattle` is the thinnest class in `data/re-training_data` (46/5/6 train/val/test
images, 1.26% of train images vs. 12–24% for every other class). Searched Roboflow
Universe, Kaggle, and GitHub for road-relevant cow/buffalo/goat/ox (and calves/kids)
datasets to diversify it beyond the existing `data/add_cattle_road_sources.py` sources
(Mendeley DATS_2022, indian-roads-cattle, IDD "animal" superclass hand-filtered — see
earlier entries). Every candidate below was downloaded (or its metadata/class list
inspected first) and sample-checked by actually opening images, not by title — per the
standing lesson in this log, and per this session's own re-confirmation of it.

### Rejected — none merged into `data/new_review_data` this session

| Candidate | Why rejected |
|---|---|
| Kaggle `raghavdharwal/cows-and-buffalo-computer-vision-dataset` (1,747 images, Roboflow `object-detection-naauz/cow-buffalo` mirror; duplicate mirrors also found: `sethshubh/catbuf-dataset-dataset-of-cows-and-buffalo`, `amiteshpatra07/cattle-dataset-pig-sheep-cow-horse` — confirmed identical source images via matching filenames, e.g. `-OWS_mp4-123_jpg...`, treated as one source) | Confirmed mixed-origin by opening samples: `HolsteinFriesiancattle107` is a Western dairy-farm stock photo (manicured pasture, studio lighting); `vaca221` (Spanish for cow) shows cactus scrubland, likely Latin American rangeland; the `-OWS_mp4-*` video-frame subset (83 images) shows barbed-wire fencing and American-style pasture/farm buildings — barbed wire is not used in rural Indian cattle-tending. Labels are also meaningless (`nc: 12`, class names `['0'..'11']`, no real names survived export). No subset of this dataset passed the India check. |
| Roboflow `4-t8ses/ox-detect` (86 images) | Class list is `{rm, yellow, X, O, blue, red, ym, bm}` — this is a tic-tac-toe/board-game symbol dataset misfiled under an "OX detect" project name, not oxen at all. Rejected from metadata alone, no download needed. |
| Roboflow `brookside-research/goat-looker` (3,970 images, classes `goats`/`sheep`) | Downloaded and sampled ~8 images across empty- and non-empty-label frames: confirmed to be a single fixed trail/security camera over one rural Western property (visible American pickup truck, wire-mesh fencing, wood-plank stairs, night-vision frames) — same repetitive background across the whole set, wrong camera angle/style for this project's handheld/dashcam target domain, and not India. |
| Roboflow `goatdataset/goat-swaod` (167 images, class `goat`) | Filenames are Flickr ID/size-suffix format (`_n`, `_w`, `_m`) — confirmed via sample images to be Flickr-scraped close-up pet/farm-goat portraits on manicured Western lawns, studio-quality, not road-context, not India. |
| Roboflow `training-data-kgqsn/common-road-animals` (510 images) | Class list includes `elk`, `barnowl`, `porcupine` — a North American road-collision wildlife dataset. Rejected from the class list alone, no download needed. |
| Kaggle `mitangshu11/indian-roads-dataset` | File listing (`Dataset3Class/AN_unpaved_0.jpg`+`.txt`) shows this is a **road-surface-type** classification/detection dataset (paved/unpaved), not an animal dataset at all — wrong task entirely. |
| Kaggle `birendranathnandi/indian-cattle-and-buffalo-breeds-dataset` | File listing (`breeds/test/Alambadi/Alambadi_001.jpg`) confirms the same breed-showcase folder format already rejected multiple times in this log (`pib-e46kr/indian-bovine`, `atharvadarpude/indian-cattle-image-dataset`, `cow-indian`) — farm/studio breed photography, no bounding boxes, no road context. |
| Kaggle `kautilya91/indian-animal-dataset` (327 images, incl. 61 cow) | Species-folder classification format mixed with lions/tigers/macaques — a general Indian-wildlife showcase set, not road-scene detection data. Not downloaded given the format alone. |

### Lesson reinforced
Every generic English-keyword search for "goat"/"buffalo"/"ox" + India/road on
Roboflow and Kaggle surfaced either (a) Western farm/stock/security-camera content
with an India-sounding or misleading title, or (b) correctly India-labeled but
wrong-format data (breed classification, road-surface type). This matches the
pattern already established for garbage/manhole in the 2026-08-31 and 2026-09-02
entries: cattle-adjacent species diversity (goat, ox specifically) appears to be a
genuine gap with no ready-made dataset, not a search-effort problem. **Next step
for these species is very likely self-collection** (phone photos, per the
`data/add_cattle_road_sources.py` precedent), not further dataset search, unless a
specifically Indian-sourced candidate surfaces with clear evidence in its own
description (not just title).

### Result
No files added to `data/new_review_data/cattle` this session. `cattle` remains at
46/5/6 (train/val/test) in `data/re-training_data`, unchanged.
