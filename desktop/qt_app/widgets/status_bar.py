"""하단 상태바 — Phase | 경과 | CPU | GPU | I/O 셀."""
from __future__ import annotations

from PySide6.QtCore import QTimer, Qt
from PySide6.QtWidgets import QFrame, QHBoxLayout, QLabel, QWidget


class _StatusDot(QLabel):
    def __init__(self, busy: bool = False, parent=None) -> None:
        super().__init__(parent)
        self.setFixedSize(7, 7)
        self._busy = busy
        self._blink = False
        self._apply()
        if busy:
            self._timer = QTimer(self)
            self._timer.timeout.connect(self._on_blink)
            self._timer.start(600)

    def _on_blink(self) -> None:
        self._blink = not self._blink
        self._apply()

    def _apply(self) -> None:
        if self._busy:
            alpha = "0.45" if self._blink else "1.0"
            self.setStyleSheet(
                f"background: rgba(78,163,255,{alpha}); border-radius: 3px;"
            )
        else:
            self.setStyleSheet("background: #4ade80; border-radius: 3px;")


class _StatusCell(QFrame):
    def __init__(self, key: str, val: str, parent=None) -> None:
        super().__init__(parent)
        self.setFixedHeight(26)
        self.setStyleSheet(
            "_StatusCell { background: transparent; border: none; border-right: 1px solid #262c36; }"
        )
        row = QHBoxLayout(self)
        row.setContentsMargins(12, 0, 12, 0)
        row.setSpacing(6)
        self._k = QLabel(key)
        self._k.setStyleSheet(
            "color: #818a99; font-size: 11px; background: transparent;"
        )
        self._v = QLabel(val)
        self._v.setStyleSheet(
            "color: #e8ecf2; font-size: 11px; font-weight: 500; "
            "font-family: 'JetBrains Mono', monospace; background: transparent;"
        )
        row.addWidget(self._k)
        row.addWidget(self._v)

    def set_value(self, value: str) -> None:
        self._v.setText(value)


class CustomStatusBar(QFrame):
    """디자인 스펙의 26px 상태바."""

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setFixedHeight(26)
        self.setStyleSheet(
            "CustomStatusBar { "
            "background: qlineargradient(x1:0, y1:0, x2:0, y2:1, "
            "  stop:0 #121720, stop:1 #0e1219); "
            "border-top: 1px solid #262c36; "
            "}"
        )
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # Phase 셀 (busy 도트 + 텍스트)
        phase_cell = QFrame()
        phase_cell.setFixedHeight(26)
        phase_cell.setStyleSheet(
            "background: transparent; border: none; border-right: 1px solid #262c36;"
        )
        phase_row = QHBoxLayout(phase_cell)
        phase_row.setContentsMargins(12, 0, 12, 0)
        phase_row.setSpacing(8)
        self._dot = _StatusDot(busy=True)
        self._phase_lbl = QLabel("Ready")
        self._phase_lbl.setStyleSheet(
            "color: #e8ecf2; font-size: 11px; font-weight: 500; background: transparent;"
        )
        phase_row.addWidget(self._dot)
        phase_row.addWidget(self._phase_lbl)
        layout.addWidget(phase_cell)

        # 가변 spacer
        layout.addStretch(1)

        # CPU/GPU/IO 셀
        self._cpu = _StatusCell("CPU", "—")
        self._gpu = _StatusCell("GPU", "—")
        self._io = _StatusCell("I/O", "—")
        # 마지막 셀은 오른쪽 보더 제거
        self._io.setStyleSheet(
            "_StatusCell { background: transparent; border: none; }"
        )
        layout.addWidget(self._cpu)
        layout.addWidget(self._gpu)
        layout.addWidget(self._io)

    def set_phase(self, text: str, busy: bool = True) -> None:
        self._phase_lbl.setText(text)
        self._dot._busy = busy
        self._dot._apply()

    def set_cpu(self, value: str) -> None:
        self._cpu.set_value(value)

    def set_gpu(self, value: str) -> None:
        self._gpu.set_value(value)

    def set_io(self, value: str) -> None:
        self._io.set_value(value)
