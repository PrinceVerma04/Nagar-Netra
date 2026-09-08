#!/usr/bin/env bash
# Pushes the CODE of this project to GitHub. Never the dataset.
#
# The working directory is ~19 GB (data/ alone is 4.2 GB) and GitHub caps single files
# at 100 MB, so this script refuses to continue if anything oversized has slipped past
# .gitignore.
#
#   ./push_to_github.sh --dry-run    # stage and check, change nothing
#   ./push_to_github.sh              # keep existing history, push
#   ./push_to_github.sh --fresh      # start clean history (recommended for a new repo)
#
# --fresh matters here: the current history is one commit that still carries ~78 MB of
# model weights and run artifacts which were deleted long ago. Git keeps deleted blobs
# forever, so pushing that history would upload 78 MB to permanently store files nobody
# wants. A fresh initial commit gives a ~25 MB repo instead. Use it when the target repo
# is new and empty; use the default when you need the existing history preserved.

set -euo pipefail
cd "$(dirname "$0")"

REPO="https://github.com/PrinceVerma04/Nagar-Netra.git"
BRANCH="main"

MODE="push"
case "${1:-}" in
    --dry-run) MODE="dry" ;;
    --fresh)   MODE="fresh" ;;
    "")        ;;
    *) echo "unknown option: $1"; exit 1 ;;
esac

echo "== Target =="
echo "   $REPO"
echo "   branch: $BRANCH   mode: $MODE"
echo

# --- point origin at the new repo ------------------------------------------
if git remote | grep -qx origin; then
    CURRENT=$(git remote get-url origin)
    if [[ "$CURRENT" != "$REPO" ]]; then
        echo "   origin was: $CURRENT"
        [[ "$MODE" != "dry" ]] && git remote set-url origin "$REPO" && echo "   origin now: $REPO"
    fi
else
    [[ "$MODE" != "dry" ]] && git remote add origin "$REPO"
fi
echo

# --- fresh history ----------------------------------------------------------
if [[ "$MODE" == "fresh" ]]; then
    echo "== Starting clean history =="
    git checkout --orphan __clean >/dev/null 2>&1
    git reset -q                       # unstage everything the orphan inherited
    echo "   on a fresh orphan branch, nothing inherited"
    echo
fi

# --- stage everything .gitignore permits -----------------------------------
echo "== Staging (respecting .gitignore) =="
git add -A
echo "   $(git diff --cached --name-only | wc -l) files staged"
echo

# --- refuse to push anything GitHub will reject ----------------------------
echo "== Size check =="
BIG=$(git diff --cached --name-only | while read -r f; do
        [[ -f "$f" ]] || continue
        sz=$(stat -c%s "$f")
        (( sz > 50000000 )) && printf '%s %s\n' "$((sz/1000000))MB" "$f"
      done || true)
if [[ -n "$BIG" ]]; then
    echo "   REFUSING TO PUSH — files over 50 MB are staged:"
    echo "$BIG" | sed 's/^/     /'
    echo "   Add them to .gitignore, then:  git reset"
    exit 1
fi
TOTAL=$(git diff --cached --name-only | while read -r f; do
          [[ -f "$f" ]] && stat -c%s "$f"; done | paste -sd+ | bc 2>/dev/null || echo 0)
printf "   total staged: %.1f MB (nothing over 50 MB)\n\n" "$(echo "$TOTAL/1000000" | bc -l)"

# --- prove no dataset file is being added ----------------------------------
# Only ADDED/MODIFIED files matter. Deletions under these paths are old commits being
# cleaned up, which is correct - counting them would be a false alarm.
echo "== Confirming no dataset files are being ADDED =="
DELETED=$(git diff --cached --name-status | awk '$1=="D"' | wc -l)
for d in "data/" "data for test/" "training_results/" "runs/"; do
    n=$(git diff --cached --name-status | awk -v d="$d" '$1!="D" && index($0,d)' | wc -l)
    printf "   %-22s %s\n" "$d" "$([[ $n -eq 0 ]] && echo 'clean ✓' || echo "$n FILES BEING ADDED ✗")"
done
[[ $DELETED -gt 0 ]] && echo "   ($DELETED stale files being removed — expected)"
echo "   models/      $(git diff --cached --name-only | grep -c '^models/' || true) files (shipped on purpose)"
echo "   docs/images/ $(git diff --cached --name-only | grep -c '^docs/images/' || true) files (README)"
echo

if [[ "$MODE" == "dry" ]]; then
    echo "--dry-run: nothing committed or pushed. Undo staging with:  git reset"
    exit 0
fi

read -r -p "Commit and push to $REPO ($BRANCH)? [y/N] " ok
[[ "$ok" == "y" || "$ok" == "Y" ]] || { echo "Aborted. Staged changes kept (git reset to undo)."; exit 0; }

git commit -q -m "Nagar Netra — 16-class on-device civic issue detector

Real-time detection of 16 street-level civic conditions (garbage, potholes,
encroachment, billboards, manhole state, streetlight state, stray animals),
running offline on Android via YOLO11n + TFLite.

- 16-class dataset: 3,896 images / 6,581 boxes, 80/10/10 stratified
- Leakage-safe splitter using perceptual hashing (removed 25% test-set leakage)
- Four class-balancing methods compared; oversampled (RFS) wins at mAP@50 0.604
- Streamlit demo + multi-person testing dashboard with in-browser annotation
- Android app (CameraX + TFLite) with letterbox preprocessing"

if [[ "$MODE" == "fresh" ]]; then
    git branch -M "$BRANCH"
    # Only a rewritten history needs to overwrite what is on the remote. A normal push
    # must NOT force - that is how you silently destroy someone else's commits.
    git push -u origin "$BRANCH" --force-with-lease
else
    git push -u origin "$BRANCH"
fi
echo
echo "Pushed → https://github.com/PrinceVerma04/Nagar-Netra"
