"""뷰포트 상단 오버레이 — breadcrumbs (좌상단) + actions toolbar (우상단)."""
from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import QFrame, QHBoxLayout, QLabel, QPushButton, QWidget


class _Breadcrumbs(QLabel):
    """좌상단: Mode / File / Step 정보."""

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setStyleSheet(
            "QLabel { "
            "color: #818a99; font-size: 11px; "
            "font-family: 'JetBrains Mono', monospace; "
            "background: transparent; padding: 4px 0; "
            "}"
        )
        self.setTextFormat(Qt.RichText)
        self.set_crumbs([])

    def set_crumbs(self, parts: list[str]) -> None:
        if not parts:
            parts = ["—"]
        fragments = []
        for i, part in enumerate(parts):
            color = "#e8ecf2" if i == len(parts) - 1 else "#b6bdc9"
            fragments.append(f"<b style='color:{color};font-weight:500'>{part}</b>")
            if i < len(parts) - 1:
                fragments.append("<span style='color:#3e4757'> / </span>")
        self.setText("".join(fragments))


class _VpButton(QPushButton):
    def __init__(self, text: str, parent=None) -> None:
        super().__init__(text, parent)
        self.setCursor(Qt.PointingHandCursor)
        self.setFlat(True)
        self._active = False
        self._apply_style()

    def set_active(self, active: bool) -> None:
        self._active = active
        self._apply_style()

    def _apply_style(self) -> None:
        if self._active:
            self.setStyleSheet(
                "QPushButton { background: rgba(78,163,255,0.12); "
                "color: #e8ecf2; border: 1px solid #4ea3ff; "
                "border-radius: 4px; padding: 4px 10px; font-size: 11px; }"
            )
        else:
            self.setStyleSheet(
                "QPushButton { background: transparent; color: #818a99; "
                "border: 1px solid transparent; border-radius: 4px; "
                "padding: 4px 10px; font-size: 11px; } "
                "QPushButton:hover { background: rgba(255,255,255,0.06); color: #e8ecf2; }"
            )


class ViewportChromeOverlay(QWidget):
    """뷰포트 투명 오버레이 — 상단 bar."""

    view_mode_changed = Signal(str)  # 'solid' / 'wire' / 'combined'
    screenshot_requested = Signal()

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setAttribute(Qt.WA_TransparentForMouseEvents, False)
        self.setStyleSheet("background: transparent;")

        layout = QHBoxLayout(self)
        layout.setContentsMargins(24, 24, 24, 0)
        layout.setSpacing(12)

        # ── Breadcrumbs (왼쪽) ─────────────────────────────────
        self._crumbs = _Breadcrumbs()
        layout.addWidget(self._crumbs, 0, Qt.AlignTop | Qt.AlignLeft)

        layout.addStretch(1)

        # ── Actions toolbar (오른쪽) — pill 컨테이너 ─────────────
        actions = QFrame()
        actions.setStyleSheet(
            "QFrame { "
            "background: rgba(15,19,25,0.78); "
            "border: 1px solid #323a46; border-radius: 6px; "
            "}"
        )
        actions_row = QHBoxLayout(actions)
        actions_row.setContentsMargins(2, 2, 2, 2)
        actions_row.setSpacing(1)

        self._view_buttons: dict[str, _VpButton] = {}
        for mode, label in [("solid", "Solid"), ("wire", "Wire"), ("combined", "Hybrid")]:
            btn = _VpButton(label)
            btn.clicked.connect(lambda _, m=mode: self._on_view_mode(m))
            actions_row.addWidget(btn)
            self._view_buttons[mode] = btn

        divider = QFrame()
        divider.setFrameShape(QFrame.VLine)
        divider.setStyleSheet("background: #323a46; max-width: 1px;")
        divider.setFixedWidth(1)
        actions_row.addWidget(divider)

        screenshot_btn = _VpButton("⊡ Shot")
        screenshot_btn.clicked.connect(self.screenshot_requested.emit)
        actions_row.addWidget(screenshot_btn)

        layout.addWidget(actions, 0, Qt.AlignTop | Qt.AlignRight)

        self.set_view_mode("solid")

    def set_crumbs(self, parts: list[str]) -> None:
        self._crumbs.set_crumbs(parts)

    def set_view_mode(self, mode: str) -> None:
        for m, btn in self._view_buttons.items():
            btn.set_active(m == mode)

    def _on_view_mode(self, mode: str) -> None:
        self.set_view_mode(mode)
        self.view_mode_changed.emit(mode)
