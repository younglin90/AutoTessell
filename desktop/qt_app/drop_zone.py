"""DropZone — 드래그앤드롭 파일 투하 영역 위젯.

PySide6에서 monkey-patching(self._label.dragEnterEvent = handler) 방식은
C++ virtual dispatch 때문에 작동하지 않으므로 반드시 QLabel 서브클래스로 구현한다.
"""
from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QDragEnterEvent, QDragLeaveEvent, QDropEvent, QEnterEvent, QMouseEvent
from PySide6.QtWidgets import QLabel


class DropZone(QLabel):
    """드래그앤드롭 가능한 파일 투하 영역."""

    file_dropped = Signal(str)  # 드롭된 파일 경로
    clicked = Signal()          # 클릭으로 파일 선택 다이얼로그 열기

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.setAcceptDrops(True)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self._set_idle_style()
        self.setText("STL · OBJ · PLY · STEP · IGES\nOFF · 3MF · MSH · VTK · LAS/LAZ\nDrop file or click to browse")

    def mousePressEvent(self, event: QMouseEvent) -> None:  # type: ignore[override]
        self.clicked.emit()
        super().mousePressEvent(event)

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
            "border: 1px dashed #3e4757; "
            "border-radius: 6px; "
            "background: #161a20; "
            "color: #818a99; "
            "padding: 18px 12px; "
            "font-size: 12px; "
            "line-height: 1.5; "
            "}"
        )

    def _set_mouse_hover_style(self) -> None:
        """마우스 커서가 올라왔을 때 (클릭 가능 힌트)."""
        self.setStyleSheet(
            "QLabel { "
            "border: 1px dashed #4ea3ff; "
            "border-radius: 6px; "
            "background: #1c2129; "
            "color: #b6bdc9; "
            "padding: 18px 12px; "
            "font-size: 12px; "
            "line-height: 1.5; "
            "}"
        )

    def _set_drag_hover_style(self) -> None:
        """파일을 끌고 왔을 때 (드롭 가능 힌트)."""
        self.setStyleSheet(
            "QLabel { "
            "border: 1px solid #4ea3ff; "
            "border-radius: 6px; "
            "background: qlineargradient(x1:0, y1:0, x2:0, y2:1, "
            "  stop:0 rgba(78,163,255,0.12), stop:1 rgba(78,163,255,0.04)); "
            "color: #6ab4ff; "
            "padding: 18px 12px; "
            "font-size: 12px; "
            "font-weight: 500; "
            "line-height: 1.5; "
            "}"
        )
