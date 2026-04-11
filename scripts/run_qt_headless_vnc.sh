#!/usr/bin/env bash
set -euo pipefail

DISPLAY_NUM="${DISPLAY_NUM:-99}"
DISPLAY_ID=":${DISPLAY_NUM}"
VNC_PORT="${VNC_PORT:-5900}"
APP_CMD="${APP_CMD:-python3 -m desktop.qt_main}"
LOG_DIR="${LOG_DIR:-/tmp/autotessell-gui}"

if [[ "${1:-}" == "--help" || "${1:-}" == "-h" ]]; then
  cat <<EOF
Usage: scripts/run_qt_headless_vnc.sh

Environment variables:
  DISPLAY_NUM   Xvfb display number (default: 99)
  VNC_PORT      x11vnc tcp port (default: 5900)
  APP_CMD       command to launch Qt app (default: python3 -m desktop.qt_main)
  LOG_DIR       log directory (default: /tmp/autotessell-gui)

Example:
  DISPLAY_NUM=99 VNC_PORT=5900 APP_CMD="python3 -m desktop.qt_main" \\
    scripts/run_qt_headless_vnc.sh
EOF
  exit 0
fi

need_cmd() {
  if ! command -v "$1" >/dev/null 2>&1; then
    echo "[ERROR] missing command: $1"
    return 1
  fi
}

need_cmd Xvfb
need_cmd x11vnc
need_cmd bash

mkdir -p "${LOG_DIR}"
XVFB_LOG="${LOG_DIR}/xvfb.log"
VNC_LOG="${LOG_DIR}/x11vnc.log"
APP_LOG="${LOG_DIR}/qt-app.log"

cleanup() {
  set +e
  [[ -n "${APP_PID:-}" ]] && kill "${APP_PID}" >/dev/null 2>&1
  [[ -n "${VNC_PID:-}" ]] && kill "${VNC_PID}" >/dev/null 2>&1
  [[ -n "${XVFB_PID:-}" ]] && kill "${XVFB_PID}" >/dev/null 2>&1
  set -e
}
trap cleanup EXIT INT TERM

echo "[INFO] starting Xvfb on ${DISPLAY_ID}"
Xvfb "${DISPLAY_ID}" -screen 0 1920x1080x24 >"${XVFB_LOG}" 2>&1 &
XVFB_PID=$!
sleep 0.4

if ! kill -0 "${XVFB_PID}" >/dev/null 2>&1; then
  echo "[ERROR] Xvfb failed to start. see ${XVFB_LOG}"
  exit 1
fi

echo "[INFO] starting x11vnc on 0.0.0.0:${VNC_PORT}"
x11vnc \
  -display "${DISPLAY_ID}" \
  -rfbport "${VNC_PORT}" \
  -forever \
  -shared \
  -nopw \
  >"${VNC_LOG}" 2>&1 &
VNC_PID=$!
sleep 0.4

if ! kill -0 "${VNC_PID}" >/dev/null 2>&1; then
  echo "[ERROR] x11vnc failed to start. see ${VNC_LOG}"
  exit 1
fi

echo "[INFO] starting Qt app: ${APP_CMD}"
DISPLAY="${DISPLAY_ID}" QT_QPA_PLATFORM=xcb bash -lc "${APP_CMD}" >"${APP_LOG}" 2>&1 &
APP_PID=$!
sleep 0.6

if ! kill -0 "${APP_PID}" >/dev/null 2>&1; then
  echo "[ERROR] Qt app exited immediately. see ${APP_LOG}"
  exit 1
fi

cat <<EOF
[READY] Qt GUI is running in virtual display.
  display: ${DISPLAY_ID}
  vnc:     vnc://127.0.0.1:${VNC_PORT}
  logs:    ${LOG_DIR}

Connect using any VNC viewer.
Keep this process running; Ctrl+C will stop all child processes.
EOF

wait "${APP_PID}"
