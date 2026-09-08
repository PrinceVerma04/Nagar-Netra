# Dataset Sources

All links verified via Kaggle/GitHub/Roboflow Universe research (2026-08-25). None of these
alone is production-scale — the plan is to merge 2-4 sources per class and rely on
augmentation. Classes with no usable dataset (streetlight state, encroachment) get a
workaround instead of a dataset.

## 1. Garbage / litter piles
- TACO — https://universe.roboflow.com/mohamed-traore-2ekkp/taco-trash-annotations-in-context (1,499 img, YOLO, CC BY 4.0)
- Trash Detection — https://universe.roboflow.com/yolo-hfplh/trash-detection-1fjjc-nd1dg (2,783 img, YOLO)
- YOLOv8 Trash Detection EE4016 — https://universe.roboflow.com/yolov8-trash-detection/yolo-v8-trash-detection-ee4016 (2,527 img, YOLO)
- Kaggle Domestic Trash/Garbage — https://www.kaggle.com/datasets/dataclusterlabs/domestic-trash-garbage-dataset (~9,000 img, classification, needs bbox relabel)
- Master index of 20+ litter datasets: https://github.com/AgaMiko/waste-datasets-review
- Reference repo (YOLOv8 + TACO, trained weights): https://github.com/jeremy-rico/litter-detection
- Note: most items are per-object (bottle/can), not "pile > 1m". Filter/relabel toward
  dense clusters, or treat clusters of nearby detections as one "pile" incident in post-processing.

## 2. Road potholes
- Pothole Detection (Intel Unnati) — https://universe.roboflow.com/intel-unnati-training-program/pothole-detection-bqu6s (2,475 img, YOLO)
- Kaggle Annotated Potholes (Chitholian) — https://www.kaggle.com/datasets/chitholian/annotated-potholes-dataset (665 img, VOC/YOLO)
- Kaggle Road Damage (potholes+cracks+manholes) — https://www.kaggle.com/datasets/lorenzoarcioni/road-damage-dataset-potholes-cracks-and-manholes (2,009 img, YOLO, 3 classes)
- Roboflow public Pothole set — https://public.roboflow.com/object-detection/pothole
- Reference (exports to TFLite): https://github.com/gbadrain/Pothole-Image-Segmentation-with-YOLOv8
- Synthetic augmentation technique for scarce damage class: PG-GAN pothole patch + Poisson
  blending onto clean road images (arxiv.org/pdf/2005.08628)

## 3. Open/broken manholes
- Open-Manholes (segmentation) — https://universe.roboflow.com/aibased-solution-for-realtime-detection-of-road-anomalies-d6eay/open-manholes (677 img)
- Manhole Cover Dataset YOLO (Broken/Good/Loose/Uncovered) — https://universe.roboflow.com/create-dataset-for-yolo/manhole-cover-dataset-yolo (1,427 img, YOLO, 4 classes)
- Pothole and Manhole Detection (combined) — https://universe.roboflow.com/project-auzdn/pothole-and-manhole-detection (2,482 img)
- Reference architecture (MGB-YOLO = YOLOv5s+MobileNetV3, embedded-deployed, 96.6% acc):
  https://www.nature.com/articles/s41598-023-43173-z
- Smallest/scarcest class — expect to merge all sources and augment heavily.

## 4. Non-working streetlights — NO end-to-end dataset exists
- Street Light detection (localization only, no lit/unlit label) —
  https://universe.roboflow.com/sashank-s/street-light (1,232 img, YOLO)
- LA Bureau of Street Lighting outage records (tabular, not imagery) —
  https://www.kaggle.com/datasets/cityofLA/los-angeles-bureau-of-street-lighting-data
- **Workaround (used in this project, see streetlight/):** train the unified detector to
  localize the lamp head only, then classify lit/unlit with a brightness/HSV heuristic on
  the cropped ROI at night. Self-collect a small verification set from real footage over time.

## 5. Encroachment — no mature single dataset, merge 2-3 partial sources
- StreetVendor-SLI (Zenodo, CC BY) — https://doi.org/10.5281/zenodo.14635548 (2,794 img, 3 vendor classes, YOLO)
- Illegal Parking — https://universe.roboflow.com/parking-amu50/illegal-parking (56 img — seed only)
- FootpathVision (binary encroached/clear) — referenced in a 2026 arXiv benchmarking paper, verify host before use.
- **Workaround for immediate coverage without training:** zero-shot with YOLO-World or
  Grounding DINO prompted with "vendor cart", "parked vehicle on sidewalk", "construction
  debris on road"; use its high-confidence outputs as pseudo-labels to bootstrap a
  supervised YOLO11n encroachment class.

## 6. Billboard & hoarding
- Billboard Object Detection — https://universe.roboflow.com/arslan-ongr8/billboard-xlvz1 (YOLO, CC BY 4.0)
- Additional Roboflow Universe projects: search `class:billboard`, `class:hoarding`
- Reference notebook: https://github.com/Tessellate-Imaging/Monk_Object_Detection/blob/master/application_model_zoo/Example%20-%20Billboard%20(Hoarding%20detection).ipynb
- Compliance/size checking has no ground-truth dataset — add a second stage that measures
  the billboard bbox against a reference object (pole/vehicle/door) for relative scale.

## 7. Cattle on road

**2026-08-29: `Cow Indian` removed, replaced with two vetted road-scene sources.**
`Cow Indian`'s boxes were tight crops on the cow's face/nose, not the whole animal — wrong
shape of label for "cattle obstructing a road". All 447 images were deleted.

Four parallel research agents then searched Roboflow, Kaggle, GitHub/academic hosts, and
video platforms for real road-scene cattle data. Everything generic ("cattle", "cow") kept
turning up farm/breed photography, synthetic composites, or code-only repos with no
redistributable data — see the rejection list below. Two sources actually passed visual
verification:

- **Roboflow `indian-road-dataset/indian-roads-detection`, version 2 specifically** (later
  versions dropped the Cattle class) — a 48-class Indian-roads dataset; only its ~120
  Cattle-labeled images are used, filtered down to 26 after deduplication (see below).
- **Mendeley `DATS_2022`** (data.mendeley.com/datasets/nfc34n8svj/2, CC BY 4.0) — a
  45-class Indian traffic dataset; pulled only the 47 images (of 1000 annotated) whose XML
  contains a Cattle object, via Mendeley's public file-listing API rather than the full
  9.97GB archive.

**Real bugs found and fixed in both sources** (confirmed by eye, not assumed — see
`data/add_cattle_road_sources.py` for the exact fix and why):
1. Both sources store a large fraction of their photos rotated with no usable EXIF
   orientation flag. `indian-roads-detection`: files with a standard Android camera name
   (`IMG_YYYYMMDD_...`) are upright; everything else (raw numeric timestamps, `N (M)`-style
   names) is 180° rotated. `DATS_2022`: every image checked was 90° rotated (dashcam mount).
   Both needed the box coordinates transformed to match, not just the pixels.
2. **~58% of `indian-roads-detection`'s Cattle images turned out to be re-uploads of the
   exact same `DATS_2022` photos** (matching filename stems, e.g. `544`, `432` in both).
   Deduplicated by source stem before merging — final count is 26 unique images from
   `indian-roads-detection` + 46 from `DATS_2022` = **72 images**, not the ~167 first
   estimated before dedup was checked.

**Rejected during the search** (checked and confirmed wrong, not just assumed):
- Roboflow `pib-e46kr/indian-bovine` — 22-class breed classifier (Gir, Sahiwal, Jersey...),
  farmyard/tethered-cow photos.
- Roboflow `rep-rxi6f/stray-animal-detection` — only has `cat`/`dog` classes, zero cattle.
- Roboflow `roadanimals/road-animals` — US wildlife (bird/boar/deer/raccoon/skunk...), no cattle.
- Roboflow `object-detection-dp5wa/yolo-v8-indian-roads-dataset` — generic "Animal" class
  turned out to be a mix of non-India photos and a stock-photo cow cutout on a studio background.
- Several single-class Roboflow "cow"/"cattle" projects (`lupora/cattle-detection-and-classification-1`,
  `cattle-fcdkw/cow-behavior-...`, `livestock-monitoring/cow-detection-0nsef`,
  `data-labelling-demo/cattle-dataset-7pewx`, `srav/cattle-rhuuh`) — all farm-monitoring
  (behavior/re-ID classes) or junk annotations, not road scenes.
- Kaggle `bsridevi/modes-dataset-of-stray-animals` (MoDES) — 400K **synthetic** composite
  images (`fgbg######.jpg` = foreground cutout pasted onto background), not real photographs.
- Kaggle `raghavdharwal/cows-and-buffalo-computer-vision-dataset` — breed-photography style
  (`HolsteinFriesiancattle...`, `vaca...`), pasture/farm/pen settings only.
- Kaggle `trainingdatapro/cows-detection-dataset` — 100% dairy-farm/barn interior shots.
- `github.com/Vivek1258/Custom-object-detection-Indain-Stray-Animals` — the images
  themselves are genuinely on-target (real cattle mid-road in Indian traffic) but are
  uncredited scraped stock photography with visible Alamy/iStock/Depositphotos watermarks —
  excluded on licensing grounds, not quality.
- `github.com/abhishek-rabidas/Animal-Intrusion-Detection-System-AIDS-`,
  `siddharthPriyadarshi/Animal-Intrusion-Detection-System`, `abiraaaaaaf/Cattle-Detection`,
  `SaiSwarup27/Animal-Intrusion-Detection` — code-only, no dataset actually committed.
- MDPI "R-3D-YOLOv3" paper (doi.org/10.3390/electronics10243079) — describes ~1,600 Indian
  roadway-animal images but has no public dataset link or data-availability statement.

**Not yet pursued — video-frame extraction fallback** (for if 72 images proves too thin
after retraining): dashcam/CCTV footage of cattle on Indian roads can be scraped with
`yt-dlp` and frame-extracted with OpenCV (tested working end-to-end, no `ffmpeg` needed —
`pip install imageio-ffmpeg` if a real ffmpeg binary is ever needed instead). Still needs
~45min-2.5hrs of human box-labeling time even in the fastest (open-vocab-assisted) form, so
deprioritized unless the two sources above turn out insufficient. Candidate videos/channels
found: DW's "South India: why are there so many cows on the street?" (verified — real
cattle-on-street footage), several `DashCamIndian`-style channel compilations (unverified,
would need per-video spot-checking since compilations mix in unrelated incidents), a WION
news segment on the Supreme Court/stray-cattle-highways issue.

**Reproduce this dataset**: `source .env && python data/add_cattle_road_sources.py` —
re-downloads both sources, re-applies the rotation fixes and dedup, and merges into
`data/unified/`.
