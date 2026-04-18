"""Pipeline 범례 인라인 스트립 — DONE / ACTIVE / PENDING / SKIPPED / FAIL."""
from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QFrame, QHBoxLayout, QLabel, QWidget


class _Swatch(QFrame):
    def __init__(self, css_bg: str, border: str | None = None, parent=None) -> None:
        super().__init__(parent)
        self.setFixedSize(7, 7)
        style = f"background: {css_bg}; border-radius: 2px;"
        if border:
            style += f" border: 1px {border};"
        self.setStyleSheet(style)


class PipelineLegendStrip(QFrame):
    """가로 40px 높이, Pipeline 아래 범례 스트립."""

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setFixedHeight(34)
        self.setStyleSheet(
            "PipelineLegendStrip { "
            "background: #101318; "
            "border-top: 1px dashed #262c36; "
            "}"
        )

        layout = QHBoxLayout(self)
        layout.setContentsMargins(16, 0, 16, 0)
        layout.setSpacing(16)

        legend = QLabel("LEGEND")
        legend.setStyleSheet(
            "color: #5a6270; font-size: 10px; font-weight: 600; "
            "letter-spacing: 1.8px; background: transparent;"
        )
        layout.addWidget(legend)

        items = [
            ("#4ade80", None, "Done"),
            ("#4ea3ff", None, "Active"),
            ("#1c2129", "solid #3e4757", "Pending"),
            ("transparent", "dashed #3e4757", "Skipped"),
            ("#ff6b6b", None, "Failed"),
        ]
        for bg, border, text in items:
            item = QWidget()
            item.setStyleSheet("background: transparent;")
            row = QHBoxLayout(item)
            row.setContentsMargins(0, 0, 0, 0)
            row.setSpacing(6)
            row.addWidget(_Swatch(bg, border))
            lbl = QLabel(text)
            lbl.setStyleSheet(
                "color: #818a99; font-size: 10.5px; background: transparent;"
            )
            row.addWidget(lbl)
            layout.addWidget(item)

        layout.addStretch()
