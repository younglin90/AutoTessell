"""QDialog 공통 키 처리 mixin."""
from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtGui import QKeyEvent


class EscDismissMixin:
    """Esc 키 입력 시 QDialog.reject()를 호출한다."""

    def keyPressEvent(self, event: QKeyEvent) -> None:
        if event.key() == Qt.Key_Escape:
            self.reject()  # type: ignore[attr-defined]
            return
        super().keyPressEvent(event)  # type: ignore[misc]
