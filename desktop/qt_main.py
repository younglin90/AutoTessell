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

from core.version import APP_VERSION


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


# GUI-DEFAULT / beta2810 — GUI 실행 시 즉시 최적 default 활성화.
# (beta-web) 이 dict 와 apply 함수는 web GUI 서버(desktop/server.py)와 공유하기
# 위해 Qt-비의존 모듈 ``desktop/default_env.py`` 로 이관됐다.  아래 alias 는
# 기존 import (``from desktop.qt_main import _DEFAULT_ENV``) 하위호환용.
from desktop.default_env import DEFAULT_ENV as _DEFAULT_ENV
from desktop.default_env import apply_default_env as _apply_default_env


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
