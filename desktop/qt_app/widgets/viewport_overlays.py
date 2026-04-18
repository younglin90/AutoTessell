"""뷰포트 오버레이 — 링 진행률, 축 기즈모, 코너 브래킷, KPI 스탯.

모두 투명 배경 위젯으로, 뷰포트 위에 겹쳐 배치한다.
"""
from __future__ import annotations

from PySide6.QtCore import QRectF, Qt, QTimer
from PySide6.QtGui import QBrush, QColor, QFont, QPainter, QPen, QPainterPath
from PySide6.QtWidgets import QFrame, QHBoxLayout, QLabel, QVBoxLayout, QWidget


# ═════════════════════════════════════════════════════════════════════════════
# 1) 코너 브래킷 (viewport 사각형 네 모서리에 ┐┌└┘ 표시)
# ═════════════════════════════════════════════════════════════════════════════
class CornerBrackets(QWidget):
    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setAttribute(Qt.WA_TransparentForMouseEvents)
        self.setStyleSheet("background: transparent;")

    def paintEvent(self, _event) -> None:  # type: ignore[override]
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing, False)
        pen = QPen(QColor("#3e4757"), 1)
        p.setPen(pen)

        L = 14
        W, H = self.width(), self.height()
        margin = 12

        # top-left
        p.drawLine(margin, margin, margin + L, margin)
        p.drawLine(margin, margin, margin, margin + L)
        # top-right
        p.drawLine(W - margin - L, margin, W - margin, margin)
        p.drawLine(W - margin, margin, W - margin, margin + L)
        # bottom-left
        p.drawLine(margin, H - margin - L, margin, H - margin)
        p.drawLine(margin, H - margin, margin + L, H - margin)
        # bottom-right
        p.drawLine(W - margin - L, H - margin, W - margin, H - margin)
        p.drawLine(W - margin, H - margin - L, W - margin, H - margin)
        p.end()


# ═════════════════════════════════════════════════════════════════════════════
# 2) 링 진행률 (110×110 원형 프로그레스 바)
# ═════════════════════════════════════════════════════════════════════════════
class RingProgressOverlay(QWidget):
    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setFixedSize(180, 170)
        self.setAttribute(Qt.WA_TransparentForMouseEvents)
        self.setStyleSheet("background: transparent;")
        self._pct = 0.0
        self._label = "Idle"
        self._eta = ""
        self._visible = False
        self.setVisible(False)

    def set_progress(self, pct: float, label: str = "", eta: str = "") -> None:
        self._pct = max(0.0, min(1.0, pct))
        if label:
            self._label = label
        if eta:
            self._eta = eta
        self._visible = True
        self.setVisible(True)
        self.update()

    def hide_overlay(self) -> None:
        self._visible = False
        self.setVisible(False)

    def paintEvent(self, _event) -> None:  # type: ignore[override]
        if not self._visible:
            return
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)

        ring_size = 110
        cx = self.width() / 2
        cy = 8 + ring_size / 2
        rect = QRectF(cx - ring_size / 2, cy - ring_size / 2, ring_size, ring_size)

        # 배경 트랙
        pen_bg = QPen(QColor(255, 255, 255, 20), 4, Qt.SolidLine, Qt.RoundCap)
        p.setPen(pen_bg)
        p.drawArc(rect, 0, 360 * 16)

        # 진행 호 (12시부터 시계방향)
        pen_fg = QPen(QColor("#4ea3ff"), 4, Qt.SolidLine, Qt.RoundCap)
        p.setPen(pen_fg)
        span_deg = int(self._pct * 360)
        p.drawArc(rect, 90 * 16, -span_deg * 16)

        # 퍼센트 텍스트
        p.setPen(QColor("#e8ecf2"))
        p.setFont(QFont("JetBrains Mono", 22, QFont.DemiBold))
        pct_rect = QRectF(cx - 50, cy - 18, 100, 24)
        p.drawText(pct_rect, Qt.AlignCenter, f"{int(self._pct * 100)}%")

        # "PROGRESS" 서브라벨
        p.setPen(QColor("#5a6270"))
        p.setFont(QFont("Inter", 8, QFont.Bold))
        sub_rect = QRectF(cx - 50, cy + 8, 100, 14)
        p.drawText(sub_rect, Qt.AlignCenter, "PROGRESS")

        # 라벨 (링 하단)
        if self._label:
            p.setPen(QColor("#b6bdc9"))
            p.setFont(QFont("Inter", 11, QFont.DemiBold))
            lbl_rect = QRectF(0, cy + ring_size / 2 + 8, self.width(), 18)
            p.drawText(lbl_rect, Qt.AlignCenter, self._label)

        # ETA
        if self._eta:
            p.setPen(QColor("#5a6270"))
            p.setFont(QFont("JetBrains Mono", 10))
            eta_rect = QRectF(0, cy + ring_size / 2 + 26, self.width(), 14)
            p.drawText(eta_rect, Qt.AlignCenter, self._eta)

        p.end()


# ═════════════════════════════════════════════════════════════════════════════
# 3) 축 기즈모 (72×72 3D 좌표축 아이콘)
# ═════════════════════════════════════════════════════════════════════════════
class AxisGizmoOverlay(QWidget):
    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setFixedSize(72, 72)
        self.setAttribute(Qt.WA_TransparentForMouseEvents)
        self.setStyleSheet("background: transparent;")

    def paintEvent(self, _event) -> None:  # type: ignore[override]
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)

        cx, cy = 36, 36
        # X axis — red, 오른쪽 아래 30도
        self._draw_axis(p, cx, cy, 22, -8, "#ff6b6b", "X")
        # Y axis — green, 왼쪽 아래 30도
        self._draw_axis(p, cx, cy, -22, -8, "#4ade80", "Y")
        # Z axis — blue, 수직 위
        self._draw_axis(p, cx, cy, 0, -22, "#4ea3ff", "Z")

        # 중앙 원점
        p.setPen(Qt.NoPen)
        p.setBrush(QBrush(QColor("#323a46")))
        p.drawEllipse(cx - 3, cy - 3, 6, 6)
        p.end()

    def _draw_axis(self, p: QPainter, x0, y0, dx, dy, color_hex, label) -> None:
        color = QColor(color_hex)
        pen = QPen(color, 2, Qt.SolidLine, Qt.RoundCap)
        p.setPen(pen)
        x1, y1 = x0 + dx, y0 + dy
        p.drawLine(x0, y0, x1, y1)

        # 엔드포인트 원
        p.setBrush(QBrush(color))
        p.drawEllipse(int(x1 - 3), int(y1 - 3), 6, 6)

        # 라벨
        p.setPen(color)
        p.setFont(QFont("JetBrains Mono", 9, QFont.Bold))
        lbl_x = x1 + (3 if dx >= 0 else -12)
        lbl_y = y1 + (3 if dy >= 0 else -3)
        p.drawText(int(lbl_x), int(lbl_y), label)


# ═════════════════════════════════════════════════════════════════════════════
# 4) KPI Stats 오버레이 (우측 상단)
# ═════════════════════════════════════════════════════════════════════════════
class KPIStatsOverlay(QFrame):
    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setFixedWidth(190)
        self.setStyleSheet(
            "KPIStatsOverlay { "
            "background: rgba(15,19,25,0.85); "
            "border: 1px solid #323a46; border-radius: 6px; "
            "}"
        )

        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 10, 12, 10)
        layout.setSpacing(4)

        title = QLabel("STATS")
        title.setStyleSheet(
            "color: #5a6270; font-size: 10px; font-weight: 600; "
            "letter-spacing: 1.5px; background: transparent;"
        )
        layout.addWidget(title)

        self._rows: dict[str, QLabel] = {}
        for key, default in (
            ("Cells", "—"),
            ("Points", "—"),
            ("Faces", "—"),
            ("Quality", "—"),
        ):
            row = QWidget()
            row.setStyleSheet("background: transparent;")
            rl = QHBoxLayout(row)
            rl.setContentsMargins(0, 0, 0, 0)
            rl.setSpacing(6)
            k = QLabel(key)
            k.setStyleSheet(
                "color: #818a99; font-size: 11px; background: transparent;"
            )
            v = QLabel(default)
            v.setAlignment(Qt.AlignRight)
            v.setStyleSheet(
                "color: #e8ecf2; font-size: 11px; font-weight: 500; "
                "font-family: 'JetBrains Mono', monospace; background: transparent;"
            )
            rl.addWidget(k)
            rl.addStretch()
            rl.addWidget(v)
            layout.addWidget(row)
            self._rows[key] = v

    def set_value(self, key: str, value: str, highlight: bool = False) -> None:
        if key in self._rows:
            color = "#4ea3ff" if highlight else "#e8ecf2"
            self._rows[key].setStyleSheet(
                f"color: {color}; font-size: 11px; font-weight: 500; "
                f"font-family: 'JetBrains Mono', monospace; background: transparent;"
            )
            self._rows[key].setText(value)


# ═════════════════════════════════════════════════════════════════════════════
# 5) 종합 컨테이너 — viewer 위에 투명 레이어로 배치
# ═════════════════════════════════════════════════════════════════════════════
class ViewportOverlayContainer(QWidget):
    """뷰포트 위 투명 오버레이 컨테이너. 크기 조정 시 자식 위치 재계산."""

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setAttribute(Qt.WA_TransparentForMouseEvents)
        self.setStyleSheet("background: transparent;")

        self.brackets = CornerBrackets(self)
        self.gizmo = AxisGizmoOverlay(self)
        self.gizmo.setAttribute(Qt.WA_TransparentForMouseEvents, False)
        self.kpi = KPIStatsOverlay(self)
        self.kpi.setAttribute(Qt.WA_TransparentForMouseEvents, False)
        self.progress = RingProgressOverlay(self)

    def resizeEvent(self, event) -> None:  # type: ignore[override]
        W, H = self.width(), self.height()
        self.brackets.setGeometry(0, 0, W, H)
        # 좌하단 기즈모
        self.gizmo.move(12, H - self.gizmo.height() - 12)
        # 우상단 KPI
        self.kpi.adjustSize()
        self.kpi.move(W - self.kpi.width() - 12, 12)
        # 중앙 진행률
        self.progress.move(
            int((W - self.progress.width()) / 2),
            int((H - self.progress.height()) / 2),
        )
        super().resizeEvent(event)
