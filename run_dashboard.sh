#!/usr/bin/env bash
# Launches the Civic Issue Detector Streamlit dashboard.
#
# Handles the two things that bite when launching this by hand:
#   1. streamlit lives in this project's .venv, not on the system PATH, so a bare
#      `streamlit run` gives "command not found" even though it is installed.
#   2. --server.address 0.0.0.0 is what makes it reachable from your phone or another
#      laptop; the Streamlit default only answers on localhost.
#
# Usage:
#   ./run_dashboard.sh            # default port 8501
#   ./run_dashboard.sh 8600       # a different port, if 8501 is taken
#
# Stop it with Ctrl+C. Keep the terminal open - closing it kills the server.

set -euo pipefail
cd "$(dirname "$0")"

PORT="${1:-8501}"
VENV_STREAMLIT=".venv/bin/streamlit"

if [[ -x "$VENV_STREAMLIT" ]]; then
    STREAMLIT="$VENV_STREAMLIT"
elif command -v streamlit >/dev/null 2>&1; then
    STREAMLIT="$(command -v streamlit)"
else
    echo "streamlit not found. Install it with:" >&2
    echo "    pip install streamlit" >&2
    exit 1
fi

# A stale server on the port is the most common reason the page will not load.
if ss -ltn 2>/dev/null | grep -q ":${PORT}\b"; then
    echo "Port ${PORT} is already in use."
    echo "Either open http://localhost:${PORT} (it may already be running),"
    echo "stop the old one with:  pkill -f 'streamlit run civic_detect_app.py'"
    echo "or pick another port:   ./run_dashboard.sh 8600"
    exit 1
fi

LAN_IP="$(ip -4 addr show scope global 2>/dev/null | grep -oP 'inet \K[\d.]+' | head -1)"

echo "Starting the Civic Issue Detector dashboard..."
echo "  This machine : http://localhost:${PORT}"
[[ -n "$LAN_IP" ]] && echo "  Same WiFi    : http://${LAN_IP}:${PORT}"
echo "  Stop with Ctrl+C. Keep this terminal open."
echo

exec "$STREAMLIT" run civic_detect_app.py \
    --server.address 0.0.0.0 \
    --server.port "$PORT" \
    --server.headless true \
    --browser.gatherUsageStats false
