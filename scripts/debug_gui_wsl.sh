#!/usr/bin/env bash
# WSL2에서 AutoTessell Qt GUI 디버그 실행
#
# WSL2 + WSLg + PyVista/VTK 조합은 X_ConfigureWindow (BadWindow) 에러가 발생한다.
# 해결: Mesa 소프트웨어 렌더링(llvmpipe) + Qt xcb 플랫폼 강제.
#
# 사용법:
#   ./scripts/debug_gui_wsl.sh           # 일반 실행
#   ./scripts/debug_gui_wsl.sh --trace   # Qt/VTK 디버그 로그 출력
#   ./scripts/debug_gui_wsl.sh --offscreen  # 창 없이, QSS/위젯만 검증

set -e
cd "$(dirname "$0")/.."

# ── 렌더링 환경 변수 ────────────────────────────────────────────
export LIBGL_ALWAYS_SOFTWARE=1       # Mesa llvmpipe (GL hw accel 비활성화)
export MESA_GL_VERSION_OVERRIDE=3.3   # VTK가 3.2+ 요구
export QT_QPA_PLATFORM=xcb            # Wayland 대신 X11 (WSLg Xwayland)
export PYOPENGL_PLATFORM=            # 빈 값 → 기본값 사용
unset WAYLAND_DISPLAY                 # Wayland 경로 차단

# ── 옵션 처리 ───────────────────────────────────────────────────
if [[ "$1" == "--offscreen" ]]; then
    export QT_QPA_PLATFORM=offscreen
    echo "[debug] QT_QPA_PLATFORM=offscreen — 창 없이 실행"
elif [[ "$1" == "--trace" ]]; then
    export QT_LOGGING_RULES="qt.qpa.*=true;*.debug=true"
    export VTK_DEBUG_LEAKS=1
    echo "[debug] Qt/VTK 디버그 로그 활성화"
fi

echo "[debug] LIBGL_ALWAYS_SOFTWARE=$LIBGL_ALWAYS_SOFTWARE"
echo "[debug] QT_QPA_PLATFORM=$QT_QPA_PLATFORM"
echo "[debug] DISPLAY=$DISPLAY"
echo "[debug] 실행 중... (Ctrl+C로 종료)"
echo ""

python3 -m desktop.qt_main
