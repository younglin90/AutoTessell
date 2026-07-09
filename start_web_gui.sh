#!/usr/bin/env bash
# Start the Auto-Tessell Web GUI.
#
# The single-page web app (desktop/web/) is served directly by the FastAPI
# server (desktop/server.py) at the root URL — no Node.js / build step.
# Just run the server and open a browser.
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PORT="${AUTOTESSELL_PORT:-9720}"
URL="http://localhost:${PORT}/"

cd "$SCRIPT_DIR"

echo "=== Auto-Tessell Web GUI ==="
echo "Serving at: $URL"
echo "Press Ctrl+C to stop."
echo ""

# Best-effort: open the default browser a couple seconds after startup.
(
  sleep 2
  if command -v xdg-open >/dev/null 2>&1; then xdg-open "$URL"
  elif command -v open >/dev/null 2>&1; then open "$URL"
  elif command -v powershell.exe >/dev/null 2>&1; then powershell.exe -NoProfile Start-Process "$URL"
  fi
) >/dev/null 2>&1 &

exec python -m desktop.server --port "$PORT"
