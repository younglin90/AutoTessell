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


def main() -> None:  # pragma: no cover
    """QApplication 을 생성하고 AutoTessellWindow 를 표시한다."""
    import sys

    # PyVista 오프스크린 렌더링 초기화 (WSL 감지)
    try:
        import pyvista as pv
        import os

        pv.OFF_SCREEN = True

        # WSL 환경 감지
        is_wsl = "wsl" in os.environ.get("PATH", "").lower() or (
            os.path.exists("/proc/version") and "microsoft" in open("/proc/version").read().lower()
        )

        if not is_wsl:
            # Linux/Mac: Xvfb 시도
            try:
                try:
                    pv.start_xvfb(suppress_messages=True)
                except TypeError:
                    pv.start_xvfb()
            except Exception:
                pass
        else:
            # WSL: OSMesa 강제
            try:
                os.environ["PYOPENGL_PLATFORM"] = "osmesa"
            except Exception:
                pass

    except Exception:
        pass  # PyVista 미설치 또는 초기화 실패

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
