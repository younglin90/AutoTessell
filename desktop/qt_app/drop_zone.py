"""DropZone — 드래그앤드롭 파일 투하 영역 위젯.

PySide6에서 monkey-patching(self._label.dragEnterEvent = handler) 방식은
C++ virtual dispatch 때문에 작동하지 않으므로 반드시 QLabel 서브클래스로 구현한다.
"""
from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QDragEnterEvent, QDragLeaveEvent, QDropEvent, QEnterEvent
from PySide6.QtWidgets import QLabel


class DropZone(QLabel):
    """드래그앤드롭 가능한 파일 투하 영역."""

    file_dropped = Signal(str)  # 드롭된 파일 경로

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.setAcceptDrops(True)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self._set_idle_style()
        self.setText("Drop STL / STEP / OBJ file\nor click to browse")

    # ── 마우스 hover ──────────────────────────────────────────────────
    def enterEvent(self, event: QEnterEvent) -> None:  # type: ignore[override]
        self._set_mouse_hover_style()
        super().enterEvent(event)

    def leaveEvent(self, event: object) -> None:  # type: ignore[override]
        self._set_idle_style()
        super().leaveEvent(event)  # type: ignore[arg-type]

    # ── 드래그앤드롭 ──────────────────────────────────────────────────
    def dragEnterEvent(self, event: QDragEnterEvent) -> None:  # type: ignore[override]
        if event.mimeData().hasUrls():
            event.acceptProposedAction()
            self._set_drag_hover_style()
        else:
            event.ignore()

    def dragLeaveEvent(self, event: QDragLeaveEvent) -> None:  # type: ignore[override]
        self._set_idle_style()

    def dropEvent(self, event: QDropEvent) -> None:  # type: ignore[override]
        urls = event.mimeData().urls()
        if urls:
            path = urls[0].toLocalFile()
            self._set_idle_style()
            self.file_dropped.emit(path)

    # ── 스타일 ───────────────────────────────────────────────────────
    def _set_idle_style(self) -> None:
        self.setStyleSheet(
            "QLabel { "
            "border: 2px dashed #3f4852; "
            "border-radius: 8px; "
            "background: #1c1b1b; "
            "color: #6b7280; "
            "padding: 16px; "
            "font-size: 13px; "
            "}"
        )

    def _set_mouse_hover_style(self) -> None:
        """마우스 커서가 올라왔을 때 (클릭 가능 힌트)."""
        self.setStyleSheet(
            "QLabel { "
            "border: 2px dashed #6b7280; "
            "border-radius: 8px; "
            "background: #222222; "
            "color: #bec7d4; "
            "padding: 16px; "
            "font-size: 13px; "
            "}"
        )

    def _set_drag_hover_style(self) -> None:
        """파일을 끌고 왔을 때 (드롭 가능 힌트)."""
        self.setStyleSheet(
            "QLabel { "
            "border: 2px dashed #0078d4; "
            "border-radius: 8px; "
            "background: #0a1a2a; "
            "color: #98cbff; "
            "padding: 16px; "
            "font-size: 13px; "
            "}"
        )
