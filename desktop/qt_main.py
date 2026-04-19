"""AutoTessell Qt GUI 진입점.

헤드리스 환경에서 import 만 수행할 경우 QApplication 을 생성하지 않는다.
실제 GUI 실행은 __main__ 블록에서만 이루어진다.

실행 방법::

    python desktop/qt_main.py
    # 또는
    python -m desktop.qt_main
"""
from __future__ import annotations

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
        is_headless = qt_offscreen or (not is_windows and not has_display)

        pv.OFF_SCREEN = bool(is_headless)

        if is_windows:
            return

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


def main() -> None:  # pragma: no cover
    """QApplication 을 생성하고 AutoTessellWindow 를 표시한다."""
    import sys

    _configure_pyvista_runtime()

    from PySide6.QtCore import QTimer, Qt
    from PySide6.QtWidgets import QApplication

    from desktop.qt_app.main_window import AutoTessellWindow

    app = QApplication(sys.argv)
    app.setApplicationName("AutoTessell")
    app.setApplicationVersion(APP_VERSION)

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
