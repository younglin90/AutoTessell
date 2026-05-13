"""AutoTessell Qt GUI 진입점.

헤드리스 환경에서 import 만 수행할 경우 QApplication 을 생성하지 않는다.
실제 GUI 실행은 __main__ 블록에서만 이루어진다.

실행 방법::

    python desktop/qt_main.py
    # 또는
    python -m desktop.qt_main
"""
from __future__ import annotations

import sys as _sys
from pathlib import Path as _Path

# 프로젝트 루트 (이 파일의 상위 디렉터리) 를 sys.path 에 삽입해
# `python desktop/qt_main.py` 직접 실행 시에도 `desktop.*` / `core.*` import 가 동작.
_PROJECT_ROOT = _Path(__file__).resolve().parent.parent
if str(_PROJECT_ROOT) not in _sys.path:
    _sys.path.insert(0, str(_PROJECT_ROOT))

try:
    from core.version import APP_VERSION
except ModuleNotFoundError:
    APP_VERSION = "1.0.0"


def _configure_pyvista_runtime() -> None:
    """GUI 실행 환경에 맞게 PyVista 렌더링 모드를 설정한다.

    실제 Windows/WSL X11/Wayland 디스플레이가 있으면 PyVistaQt가 네이티브
    OpenGL 컨텍스트를 쓰도록 두고, headless/offscreen 환경에서만 offscreen
    fallback을 켠다.
    """
    try:
        import os
        import sys as _sys
        import pyvista as pv

        qt_offscreen = os.environ.get("QT_QPA_PLATFORM") == "offscreen"
        has_display = bool(os.environ.get("DISPLAY") or os.environ.get("WAYLAND_DISPLAY"))
        is_windows = _sys.platform == "win32"
        # WSL2 감지 — kernel release 에 'microsoft' 포함.
        is_wsl = (
            os.path.exists("/proc/version")
            and "microsoft" in open("/proc/version").read().lower()
        )
        is_headless = qt_offscreen or (not is_windows and not has_display)

        # BETA2853 — WSL2+WSLg 에서 PyVistaQt 의 OpenGL context 생성이 hang 함
        # (Xwayland → mesa → llvmpipe 경로 문제). 디스플레이 있어도 OFF_SCREEN
        # mode (static PNG fallback) 강제 → GUI 정상 동작.
        # 사용자 명시 override: AUTO_TESSELL_PYVISTA_GLX=1 → real OpenGL 시도.
        force_glx = os.environ.get("AUTO_TESSELL_PYVISTA_GLX", "0") == "1"
        if is_wsl and not force_glx:
            pv.OFF_SCREEN = True
        else:
            pv.OFF_SCREEN = bool(is_headless)

        if is_windows:
            return

        # WSL/Linux X11 환경: xcb 플랫폼을 명시해야 VTK QtInteractor가
        # QApplication 생성 이전에 window ID를 올바르게 처리한다.
        # (없으면 XConfigureWindow BadWindow 오류로 프로세스가 죽음)
        if has_display and not qt_offscreen:
            os.environ.setdefault("QT_QPA_PLATFORM", "xcb")

        if is_headless:
            # WSL 환경 감지
            is_wsl = "wsl" in os.environ.get("PATH", "").lower() or (
                os.path.exists("/proc/version")
                and "microsoft" in open("/proc/version").read().lower()
            )
            if is_wsl:
                # WSL: OSMesa 강제
                os.environ.setdefault("PYOPENGL_PLATFORM", "osmesa")
            else:
                # 순수 Linux headless: Xvfb 시도 (deprecated 경고 억제)
                import warnings
                with warnings.catch_warnings():
                    warnings.simplefilter("ignore", DeprecationWarning)
                    try:
                        pv.start_xvfb()
                    except Exception:
                        pass

    except Exception:
        pass  # PyVista 미설치 또는 초기화 실패


_DEFAULT_ENV = {
    # GUI-DEFAULT / beta2810 — GUI 실행 시 즉시 최적 default 활성화.
    # 모든 self-impl tet 강화 + multi-fallback chain + BL aspect cap +
    # P4D pytetwild fallback + AGGR/L3 repair (extreme 입력 회복).
    "AUTO_TESSELL_STELLAR_KLINGNER": "1",   # Klingner edge contract (P2.1).
    "AUTO_TESSELL_BL_ASPECT_ENFORCE": "1",  # post-extrude aspect cap.
    "AUTO_TESSELL_BL_ASPECT_TARGET": "1000",
    "AUTO_TESSELL_P4C_PYTETWILD": "1",      # P4-C external fallback.
    "AUTO_TESSELL_VVV2_QUEUE": "1",         # Stellar swap queue.
    "AUTO_TESSELL_RRR2_TARGETED": "1",      # AMIPS targeted smoothing.
    "AUTO_TESSELL_P3_SSS_REVIVAL": "1",     # surface vertex relocate.
    "AUTO_TESSELL_CVT3D_QUALITY_WEIGHT": "0",  # opt-in only (heavier).
    "AUTO_TESSELL_AGGR_REPAIR": "0",        # off by default (heavier).
    "AUTO_TESSELL_L3_AI_REPAIR": "0",       # off by default (very heavy).
    "AUTO_TESSELL_POLY_GRADE_RETRY": "1",   # poly retry chain.
    # U-1 / U-3 / U-3b / U-13 / U-17 (2026-05-11) — bench 와 parity.
    # 이 env 들이 빠지면 GUI 21-STL 결과가 18/21 수준으로 떨어진다.
    # bench_cavity_eval.py 의 default 와 동일하게 설정.
    "AUTO_TESSELL_BL_TRIANGULATE_QUAD_SHORTEST": "1",      # U-1
    "AUTO_TESSELL_BL_DROP_NEG_VOL": "1",                   # U-3
    "AUTO_TESSELL_BL_DROP_SKEW_THRESHOLD": "10",           # U-3b + QA(2026-05-13)
    # QA-fix (2026-05-13) — skew threshold 18→10.  polyDualMesh on curved
    # STLs produces boundary sliver cells with skew >>20 (485 on test
    # input).  Threshold 10 drops these outliers (typically ≤50 cells of
    # ~10k) while preserving genuine BL skew up to 10.  Verified:
    # curved STL skew_max 485 → 9.86 with 37/8483 cells dropped.
    "AUTO_TESSELL_BL_DROP_MAX_ITER": "8",
    "AUTO_TESSELL_WILDMESH_TARGET_CELL_REMAP": "1",        # U-13
    "AUTO_TESSELL_WILDMESH_TARGET_CALIB_BASE": "14000",
    "AUTO_TESSELL_WILDMESH_TARGET_OVERSHOOT": "1.4",
    "AUTO_TESSELL_WILDMESH_BOX_TARGET_FRAC": "0.95",       # U-12
    "AUTO_TESSELL_WILDMESH_EXTRUSION_TARGET_FACTOR": "1.5",  # U-17
    "AUTO_TESSELL_WILDMESH_EXTRUSION_OUTER_FACTOR": "0.9",
    # H-1 / H-3 / H-6 / H-7 / H-10 / H-11 (2026-05-12) — hex+cfMesh loop.
    # bench_hex_cavity_eval.py default와 동일.  이 env 들이 빠지면
    # GUI 21-STL hex+BL 결과가 12/21 baseline 수준으로 떨어진다.
    "AUTO_TESSELL_ALLOW_EXTERNAL_OPENFOAM": "1",           # cfMesh는 OpenFOAM external
    "AUTO_TESSELL_HEX_CFMESH_TARGET_CALIB": "0.85",        # H-2
    "AUTO_TESSELL_HEX_CFMESH_REPAIR_SURFACE": "1",         # H-10 WildMesh repair
    "AUTO_TESSELL_BL_DROP_NEG_VOL_GEOM_CHECK": "0",        # H-6 hex-safe
    "AUTO_TESSELL_BL_DROP_NEG_VOL_TOPO_CHECK": "1",
    # tet loop default 8 < H-7's 24.  hex+BL 의 broken-input cleanup 에
    # 더 많은 iter 필요.  tet+BL bench도 8 → 24 로 올라가지만 (모든 카드
    # PASS) tet loop 측정상 negative effect 없음.
    "AUTO_TESSELL_BL_DROP_MAX_ITER": "24",
    # P-1 / P-2 / P-3 (2026-05-12) — poly+cfMesh loop.  cartesian_dual
    # backend bench로 6/21 → 21/21 PSS 도달.  pMesh segfault 우회.
    # QA-fix (2026-05-13) — user expects true polyhedral cells when picking
    # ``poly`` (pentagon/hexagon dominant), not the hex-like cartesian_dual
    # output.  Default switched to ``tet_dual`` (fTetWild + polyDualMesh).
    "AUTO_TESSELL_POLY_BACKEND": "tet_dual",         # P-3 QA upgrade
    "AUTO_TESSELL_POLY_TETDUAL_PRIMAL_SCALE": "3.0", # primal cell scale (target/2 dual cells)
    "AUTO_TESSELL_POLY_CFMESH_REPAIR_SURFACE": "1",  # P-1 WildMesh repair
    "AUTO_TESSELL_POLY_CFMESH_TARGET_CALIB": "1.4",  # P-2 pMesh density compensation
}


def _apply_default_env() -> None:
    """default 환경변수 적용 (사용자가 미리 설정하지 않은 것만)."""
    import os
    for k, v in _DEFAULT_ENV.items():
        os.environ.setdefault(k, v)


def main() -> None:  # pragma: no cover
    """QApplication 을 생성하고 AutoTessellWindow 를 표시한다."""
    import sys
    import signal
    import faulthandler
    faulthandler.enable()  # SIGSEGV 시 Python traceback 출력

    # BETA2854 — Ctrl+C 가 Qt event loop 까지 전달되도록 SIGINT default 복원.
    # PySide6 가 default 로 SIGINT 를 SIG_IGN 처리해 Ctrl+C 가 무시됨.
    signal.signal(signal.SIGINT, signal.SIG_DFL)

    _apply_default_env()
    _configure_pyvista_runtime()

    from PySide6.QtCore import QTimer, Qt
    from PySide6.QtWidgets import QApplication

    from desktop.qt_app.main_window import AutoTessellWindow

    app = QApplication(sys.argv)
    app.setApplicationName("AutoTessell")
    app.setApplicationVersion(APP_VERSION)

    # BETA2854 — QTimer 가 주기적으로 Python 인터프리터에게 제어권 → SIGINT 처리.
    # SIG_DFL 만으로는 Qt C++ 이벤트 루프 진입 후 Python signal handler 가
    # 호출되지 않음. 100ms 마다 빈 callback 으로 Python 으로 잠시 복귀.
    _sigint_timer = QTimer()
    _sigint_timer.start(100)
    _sigint_timer.timeout.connect(lambda: None)

    window = AutoTessellWindow()
    window.show()

    def _force_show_front() -> None:
        try:
            qmain = getattr(window, "_qmain", None)
            if qmain is None:
                return
            qmain.showNormal()
            qmain.setWindowState((qmain.windowState() & ~Qt.WindowMinimized) | Qt.WindowActive)
            qmain.raise_()
            qmain.activateWindow()
        except Exception:
            pass

    # WSL/X11/Wayland에서 초기 창이 뒤로 가거나 오프스크린으로 붙는 경우 보정
    QTimer.singleShot(120, _force_show_front)
    QTimer.singleShot(600, _force_show_front)

    sys.exit(app.exec())


if __name__ == "__main__":  # pragma: no cover
    main()
