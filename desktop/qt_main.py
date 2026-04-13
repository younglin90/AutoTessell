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

    # PyVista 오프스크린 렌더링 초기화
    try:
        import pyvista as pv
        pv.OFF_SCREEN = True
        try:
            try:
                pv.start_xvfb(suppress_messages=True)
            except TypeError:
                # suppress_messages 파라미터 미지원 시
                pv.start_xvfb()
        except Exception:
            pass  # Xvfb 이미 실행 또는 사용 불가능
    except Exception:
        pass  # PyVista 미설치

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
