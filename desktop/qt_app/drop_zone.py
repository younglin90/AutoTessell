"""DropZone — 드래그앤드롭 파일 투하 영역 위젯.

PySide6에서 monkey-patching(self._label.dragEnterEvent = handler) 방식은
C++ virtual dispatch 때문에 작동하지 않으므로 반드시 QLabel 서브클래스로 구현한다.
"""
from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QDragEnterEvent, QDragLeaveEvent, QDropEvent
from PySide6.QtWidgets import QLabel


class DropZone(QLabel):
    """드래그앤드롭 가능한 파일 투하 영역."""

    file_dropped = Signal(str)  # 드롭된 파일 경로

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.setAcceptDrops(True)
        self._set_idle_style()
        self.setText("Drop STL / STEP / OBJ file\nor click to browse")

    def dragEnterEvent(self, event: QDragEnterEvent) -> None:  # type: ignore[override]
        if event.mimeData().hasUrls():
            event.acceptProposedAction()
            self._set_hover_style()
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

    def _set_idle_style(self) -> None:
        self.setStyleSheet(
            "QLabel { "
            "border: 2px dashed #3f4852; "
            "border-radius: 8px; "
            "background: #1c1b1b; "
            "color: #4a5568; "
            "padding: 16px; "
            "font-size: 11px; "
            "}"
        )

    def _set_hover_style(self) -> None:
        self.setStyleSheet(
            "QLabel { "
            "border: 2px dashed #0078d4; "
            "border-radius: 8px; "
            "background: #0a1a2a; "
            "color: #98cbff; "
            "padding: 16px; "
            "font-size: 11px; "
            "}"
        )
