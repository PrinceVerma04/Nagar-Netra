# Dataset snapshot — 20260907_133035

**Label:** before_all_retrain

Generated 2026-09-07T13:30:35 · **16 classes** (ids 0–15)

## Integrity checks

| check | result |
|---|---|
| both trees in sync | PASS (6581 vs 6581 boxes) |
| class ids in range | PASS |
| degenerate boxes | PASS (0) |
| orphan labels | PASS (0) |
| empty labels | PASS (0) |
| no image in two splits | PASS |

## Overall summary

- **3896 images**, **6581 boxes**, 16 classes
- Split **3118 / 389 / 389** (train/val/test)
- val and test are byte-identical across all four variants; only train differs
- smallest classes: manhole_closed (22), buffalo (31), goat (37), cat (42)

## Per-variant splits

### canonical (unbalanced)

| class | train | val | test | total | val % | boxes tr/val/test |
|---|---:|---:|---:|---:|---:|---|
| garbage_pile | 499 | 62 | 62 | 623 | 10.0% | 773 / 117 / 104 |
| pothole | 568 | 71 | 71 | 710 | 10.0% | 1197 / 170 / 115 |
| encroachment | 378 | 47 | 47 | 472 | 10.0% | 770 / 72 / 92 |
| billboard_hoarding | 388 | 48 | 48 | 484 | 9.9% | 614 / 128 / 114 |
| cow | 74 | 9 | 9 | 92 | 9.8% | 157 / 19 / 19 |
| manhole_closed | 18 | 2 | 2 | 22 | 9.1% | 18 / 2 / 2 |
| manhole_open | 325 | 40 | 40 | 405 | 9.9% | 329 / 42 / 40 |
| manhole_broken | 139 | 17 | 17 | 173 | 9.8% | 141 / 17 / 20 |
| streetlight_working | 328 | 42 | 42 | 412 | 10.2% | 361 / 64 / 58 |
| streetlight_not_working | 168 | 21 | 21 | 210 | 10.0% | 177 / 31 / 29 |
| cat | 34 | 4 | 4 | 42 | 9.5% | 56 / 5 / 8 |
| horse | 48 | 6 | 6 | 60 | 10.0% | 52 / 7 / 8 |
| dog | 47 | 6 | 6 | 59 | 10.2% | 89 / 27 / 26 |
| buffalo | 25 | 3 | 3 | 31 | 9.7% | 65 / 5 / 7 |
| goat | 29 | 4 | 4 | 37 | 10.8% | 292 / 30 / 23 |
| camel | 52 | 7 | 7 | 66 | 10.6% | 70 / 8 / 11 |
| **TOTAL** | **3118** | **389** | **389** | **3896** | | **5161 / 744 / 676** |

Split ratio: **80.0 / 10.0 / 10.0**

Fingerprints — train `3918a3c88e93c4b6` · val `1798979946ab72c5` · test `3e59b0cafdcfb131`

### oversampled

| class | train | val | test | total | val % | boxes tr/val/test |
|---|---:|---:|---:|---:|---:|---|
| garbage_pile | 499 | 62 | 62 | 623 | 10.0% | 773 / 117 / 104 |
| pothole | 568 | 71 | 71 | 710 | 10.0% | 1197 / 170 / 115 |
| encroachment | 378 | 47 | 47 | 472 | 10.0% | 770 / 72 / 92 |
| billboard_hoarding | 388 | 48 | 48 | 484 | 9.9% | 614 / 128 / 114 |
| cow | 155 | 9 | 9 | 173 | 5.2% | 323 / 19 / 19 |
| manhole_closed | 74 | 2 | 2 | 78 | 2.6% | 74 / 2 / 2 |
| manhole_open | 325 | 40 | 40 | 405 | 9.9% | 329 / 42 / 40 |
| manhole_broken | 206 | 17 | 17 | 240 | 7.1% | 209 / 17 / 20 |
| streetlight_working | 328 | 42 | 42 | 412 | 10.2% | 361 / 64 / 58 |
| streetlight_not_working | 226 | 21 | 21 | 268 | 7.8% | 238 / 31 / 29 |
| cat | 104 | 4 | 4 | 112 | 3.6% | 171 / 5 / 8 |
| horse | 122 | 6 | 6 | 134 | 4.5% | 133 / 7 / 8 |
| dog | 121 | 6 | 6 | 133 | 4.5% | 236 / 27 / 26 |
| buffalo | 92 | 3 | 3 | 98 | 3.1% | 233 / 5 / 7 |
| goat | 95 | 4 | 4 | 103 | 3.9% | 944 / 30 / 23 |
| camel | 124 | 7 | 7 | 138 | 5.1% | 167 / 8 / 11 |
| **TOTAL** | **3797** | **389** | **389** | **4575** | | **6772 / 744 / 676** |

Split ratio: **83.0 / 8.5 / 8.5**

Fingerprints — train `86a6b360e5e4ec6a` · val `1798979946ab72c5` · test `3e59b0cafdcfb131`

### undersampled

| class | train | val | test | total | val % | boxes tr/val/test |
|---|---:|---:|---:|---:|---:|---|
| garbage_pile | 168 | 62 | 62 | 292 | 21.2% | 248 / 117 / 104 |
| pothole | 168 | 71 | 71 | 310 | 22.9% | 333 / 170 / 115 |
| encroachment | 168 | 47 | 47 | 262 | 17.9% | 341 / 72 / 92 |
| billboard_hoarding | 168 | 48 | 48 | 264 | 18.2% | 255 / 128 / 114 |
| cow | 74 | 9 | 9 | 92 | 9.8% | 157 / 19 / 19 |
| manhole_closed | 18 | 2 | 2 | 22 | 9.1% | 18 / 2 / 2 |
| manhole_open | 168 | 40 | 40 | 248 | 16.1% | 171 / 42 / 40 |
| manhole_broken | 139 | 17 | 17 | 173 | 9.8% | 141 / 17 / 20 |
| streetlight_working | 168 | 42 | 42 | 252 | 16.7% | 189 / 64 / 58 |
| streetlight_not_working | 168 | 21 | 21 | 210 | 10.0% | 177 / 31 / 29 |
| cat | 34 | 4 | 4 | 42 | 9.5% | 56 / 5 / 8 |
| horse | 48 | 6 | 6 | 60 | 10.0% | 52 / 7 / 8 |
| dog | 47 | 6 | 6 | 59 | 10.2% | 89 / 27 / 26 |
| buffalo | 25 | 3 | 3 | 31 | 9.7% | 65 / 5 / 7 |
| goat | 29 | 4 | 4 | 37 | 10.8% | 292 / 30 / 23 |
| camel | 52 | 7 | 7 | 66 | 10.6% | 70 / 8 / 11 |
| **TOTAL** | **1640** | **389** | **389** | **2418** | | **2654 / 744 / 676** |

Split ratio: **67.8 / 16.1 / 16.1**

Fingerprints — train `07c057270c29882a` · val `1798979946ab72c5` · test `3e59b0cafdcfb131`

### augmented

| class | train | val | test | total | val % | boxes tr/val/test |
|---|---:|---:|---:|---:|---:|---|
| garbage_pile | 499 | 62 | 62 | 623 | 10.0% | 773 / 117 / 104 |
| pothole | 568 | 71 | 71 | 710 | 10.0% | 1197 / 170 / 115 |
| encroachment | 378 | 47 | 47 | 472 | 10.0% | 770 / 72 / 92 |
| billboard_hoarding | 388 | 48 | 48 | 484 | 9.9% | 614 / 128 / 114 |
| cow | 155 | 9 | 9 | 173 | 5.2% | 323 / 19 / 19 |
| manhole_closed | 74 | 2 | 2 | 78 | 2.6% | 74 / 2 / 2 |
| manhole_open | 325 | 40 | 40 | 405 | 9.9% | 329 / 42 / 40 |
| manhole_broken | 206 | 17 | 17 | 240 | 7.1% | 209 / 17 / 20 |
| streetlight_working | 328 | 42 | 42 | 412 | 10.2% | 361 / 64 / 58 |
| streetlight_not_working | 226 | 21 | 21 | 268 | 7.8% | 238 / 31 / 29 |
| cat | 104 | 4 | 4 | 112 | 3.6% | 171 / 5 / 8 |
| horse | 122 | 6 | 6 | 134 | 4.5% | 133 / 7 / 8 |
| dog | 121 | 6 | 6 | 133 | 4.5% | 236 / 27 / 26 |
| buffalo | 92 | 3 | 3 | 98 | 3.1% | 232 / 5 / 7 |
| goat | 95 | 4 | 4 | 103 | 3.9% | 941 / 30 / 23 |
| camel | 124 | 7 | 7 | 138 | 5.1% | 167 / 8 / 11 |
| **TOTAL** | **3797** | **389** | **389** | **4575** | | **6768 / 744 / 676** |

Split ratio: **83.0 / 8.5 / 8.5**

Fingerprints — train `c563d43600e143cc` · val `1798979946ab72c5` · test `3e59b0cafdcfb131`

## Train-split comparison across variants

| class | canonical (unbalanced) | oversampled | undersampled | augmented |
|---|---|---|---|---|
| garbage_pile | 499 | 499 | 168 | 499 |
| pothole | 568 | 568 | 168 | 568 |
| encroachment | 378 | 378 | 168 | 378 |
| billboard_hoarding | 388 | 388 | 168 | 388 |
| cow | 74 | 155 | 74 | 155 |
| manhole_closed | 18 | 74 | 18 | 74 |
| manhole_open | 325 | 325 | 168 | 325 |
| manhole_broken | 139 | 206 | 139 | 206 |
| streetlight_working | 328 | 328 | 168 | 328 |
| streetlight_not_working | 168 | 226 | 168 | 226 |
| cat | 34 | 104 | 34 | 104 |
| horse | 48 | 122 | 48 | 122 |
| dog | 47 | 121 | 47 | 121 |
| buffalo | 25 | 92 | 25 | 92 |
| goat | 29 | 95 | 29 | 95 |
| camel | 52 | 124 | 52 | 124 |
| **train images** | **3118** | **3797** | **1640** | **3797** |

