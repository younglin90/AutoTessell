"""Titlebar 신호등 데코레이티브 스트립.

OS 시스템 크롬을 유지하면서 디자인 스펙의 Titlebar 룩을 재현한다.
컨텐츠 영역 최상단에 36px 높이로 배치한다.
"""
from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QFrame, QHBoxLayout, QLabel, QWidget


class TrafficLight(QLabel):
    def __init__(self, color: str, parent=None) -> None:
        super().__init__(parent)
        self.setFixedSize(12, 12)
        self.setStyleSheet(
            f"background: {color}; border-radius: 6px; "
            f"border: 1px solid rgba(0,0,0,0.4);"
        )


class TitlebarStrip(QFrame):
    """가로 36px. 왼쪽: 3개 traffic light, 중앙: 타이틀, 오른쪽: 윈도우 컨트롤."""

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setFixedHeight(36)
        self.setStyleSheet(
            "TitlebarStrip { "
            "background: qlineargradient(x1:0, y1:0, x2:0, y2:1, "
            "  stop:0 #1a1f27, stop:1 #151a21); "
            "border: none; border-bottom: 1px solid #262c36; "
            "}"
        )

        layout = QHBoxLayout(self)
        layout.setContentsMargins(12, 0, 12, 0)
        layout.setSpacing(12)

        lights = QWidget()
        lights.setStyleSheet("background: transparent;")
        lights_layout = QHBoxLayout(lights)
        lights_layout.setContentsMargins(0, 0, 0, 0)
        lights_layout.setSpacing(7)
        for color in ("#ff5f57", "#febc2e", "#28c840"):
            lights_layout.addWidget(TrafficLight(color))
        layout.addWidget(lights, 0, Qt.AlignVCenter)

        layout.addStretch(1)

        self._title = QLabel()
        self._title.setAlignment(Qt.AlignCenter)
        self._title.setStyleSheet(
            "color: #b6bdc9; font-size: 12px; font-weight: 500; "
            "letter-spacing: 0.3px; background: transparent;"
        )
        layout.addWidget(self._title, 0, Qt.AlignVCenter)

        layout.addStretch(1)

        # 오른쪽 반대편 spacer (traffic lights 폭만큼 밸런스용 공간)
        spacer = QWidget()
        spacer.setFixedWidth(50)
        spacer.setStyleSheet("background: transparent;")
        layout.addWidget(spacer)

        self.set_title("AutoTessell", subtitle=None, path=None)

    def set_title(self, app_name: str, subtitle: str | None, path: str | None) -> None:
        parts = [f"<b style='color:#e8ecf2;font-weight:600'>{app_name}</b>"]
        if subtitle:
            parts.append(f"<span style='color:#5a6270'> — </span>{subtitle}")
        if path:
            parts.append(
                f"<span style='color:#5a6270'> — </span>"
                f"<span style='color:#818a99;"
                f"font-family:JetBrains Mono,monospace;font-size:11px'>{path}</span>"
            )
        self._title.setText("".join(parts))
