#!/usr/bin/env bash
# Start AutoTessell GUI — FastAPI backend + Next.js frontend
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
FRONTEND_DIR="$SCRIPT_DIR/b_aYczSLScZNH"
BACKEND_PORT="${AUTOTESSELL_PORT:-9720}"
FRONTEND_PORT="${FRONTEND_PORT:-3000}"

echo "=== AutoTessell GUI ==="
echo "Backend:  http://localhost:$BACKEND_PORT"
echo "Frontend: http://localhost:$FRONTEND_PORT"
echo ""

# Ensure frontend dependencies are installed
if [ ! -d "$FRONTEND_DIR/node_modules" ]; then
  echo "[setup] Installing frontend dependencies..."
  cd "$FRONTEND_DIR" && npm install
fi

# Start FastAPI backend
echo "[backend] Starting FastAPI on port $BACKEND_PORT..."
cd "$SCRIPT_DIR"
python -m desktop.server --port "$BACKEND_PORT" &
BACKEND_PID=$!

# Start Next.js frontend
echo "[frontend] Starting Next.js on port $FRONTEND_PORT..."
cd "$FRONTEND_DIR"
NEXT_PUBLIC_API_URL="http://localhost:$BACKEND_PORT" npm run dev -- --port "$FRONTEND_PORT" &
FRONTEND_PID=$!

# Cleanup on exit
trap 'echo ""; echo "Stopping..."; kill $BACKEND_PID $FRONTEND_PID 2>/dev/null; exit 0' INT TERM

echo ""
echo "Open http://localhost:$FRONTEND_PORT in your browser."
echo "Press Ctrl+C to stop."
wait
