"""Tier Pipeline 하단 스트립 — 원형 노드 + 연결선.

상태:
- pending: 회색 링, 번호 표시
- active: accent 링 + 펄스 애니메이션, 번호 + 링 그림자
- done: ok 색 채움 + 체크마크
- fail: err 색 테두리 + X 마크
- skipped: 점선 테두리, 투명도 45%
"""
from __future__ import annotations

from typing import Literal

from PySide6.QtCore import QPropertyAnimation, QRectF, Qt, QTimer, Signal
from PySide6.QtGui import QColor, QFont, QPainter, QPen, QBrush, QPainterPath
from PySide6.QtWidgets import QFrame, QHBoxLayout, QLabel, QPushButton, QVBoxLayout, QWidget

TierStatus = Literal["pending", "active", "done", "fail", "skipped"]


class _TierNode(QWidget):
    """단일 Tier 원형 노드 (36×36) + 라벨."""

    def __init__(self, index: int, name: str, engine: str, parent=None) -> None:
        super().__init__(parent)
        self._index = index
        self._name = name
        self._engine = engine
        self._status: TierStatus = "pending"
        self._pulse_phase = 0.0
        self.setFixedWidth(120)
        self.setMinimumHeight(80)

        self._timer = QTimer(self)
        self._timer.timeout.connect(self._on_tick)

    def set_status(self, status: TierStatus) -> None:
        self._status = status
        if status == "active":
            self._timer.start(60)
        else:
            self._timer.stop()
        self.update()

    def _on_tick(self) -> None:
        self._pulse_phase = (self._pulse_phase + 0.06) % 1.0
        self.update()

    def paintEvent(self, _event) -> None:  # type: ignore[override]
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)

        cx = self.width() / 2
        cy = 18 + 4
        r = 18
        ring = QRectF(cx - r, cy - r, 2 * r, 2 * r)

        # 상태별 색상
        if self._status == "done":
            bg = QColor("#4ade80")
            fg = QColor("#0a1a10")
            pen_color = bg
            glow = True
        elif self._status == "active":
            bg = QColor("#101318")
            fg = QColor("#4ea3ff")
            pen_color = QColor("#4ea3ff")
            glow = True
        elif self._status == "fail":
            bg = QColor(255, 80, 80, 30)
            fg = QColor("#ff6b6b")
            pen_color = QColor("#ff6b6b")
            glow = False
        elif self._status == "skipped":
            bg = QColor("#161a20")
            fg = QColor("#5a6270")
            pen_color = QColor("#3e4757")
            glow = False
        else:  # pending
            bg = QColor("#161a20")
            fg = QColor("#818a99")
            pen_color = QColor("#3e4757")
            glow = False

        # 글로우 (active/done)
        if glow:
            glow_color = QColor(pen_color)
            glow_color.setAlpha(50)
            p.setPen(Qt.NoPen)
            p.setBrush(QBrush(glow_color))
            p.drawEllipse(ring.adjusted(-6, -6, 6, 6))

        # 활성 펄스 링
        if self._status == "active":
            pulse_r = r + 6 + self._pulse_phase * 8
            pulse_alpha = int((1.0 - self._pulse_phase) * 120)
            ring_color = QColor("#4ea3ff")
            ring_color.setAlpha(pulse_alpha)
            pen = QPen(ring_color, 1.5)
            p.setPen(pen)
            p.setBrush(Qt.NoBrush)
            p.drawEllipse(QRectF(cx - pulse_r, cy - pulse_r, 2 * pulse_r, 2 * pulse_r))

        # 원형 배경 + 테두리
        p.setBrush(QBrush(bg))
        pen_style = Qt.DashLine if self._status == "skipped" else Qt.SolidLine
        pen = QPen(pen_color, 1.5, pen_style)
        p.setPen(pen)
        p.drawEllipse(ring)

        # 중앙 심볼
        p.setPen(fg)
        font = QFont("JetBrains Mono", 10, QFont.Bold)
        p.setFont(font)
        if self._status == "done":
            p.setFont(QFont("Inter", 12, QFont.Bold))
            p.drawText(ring, Qt.AlignCenter, "✓")
        elif self._status == "fail":
            p.setFont(QFont("Inter", 12, QFont.Bold))
            p.drawText(ring, Qt.AlignCenter, "✕")
        else:
            p.drawText(ring, Qt.AlignCenter, str(self._index))

        # 이름
        name_color = QColor("#4ea3ff") if self._status == "active" else QColor("#e8ecf2")
        p.setPen(name_color)
        p.setFont(QFont("Inter", 9, QFont.DemiBold))
        name_rect = QRectF(0, cy + r + 6, self.width(), 14)
        p.drawText(name_rect, Qt.AlignCenter, self._name)

        # 엔진명
        p.setPen(QColor("#818a99"))
        p.setFont(QFont("JetBrains Mono", 8))
        eng_rect = QRectF(0, cy + r + 20, self.width(), 12)
        p.drawText(eng_rect, Qt.AlignCenter, self._engine)

        p.end()


class _PipelineBtn(QPushButton):
    def __init__(self, text: str, kind: str = "default", parent=None) -> None:
        super().__init__(text, parent)
        self.setCursor(Qt.PointingHandCursor)
        self.setFlat(True)
        self._kind = kind
        self._apply()

    def _apply(self) -> None:
        if self._kind == "primary":
            self.setStyleSheet(
                "QPushButton { background: #4ea3ff; border: 1px solid #4ea3ff; "
                "color: #05111e; border-radius: 4px; padding: 5px 12px; "
                "font-size: 11.5px; font-weight: 600; }"
                "QPushButton:hover { background: #6ab4ff; border-color: #6ab4ff; }"
            )
        elif self._kind == "stop":
            self.setStyleSheet(
                "QPushButton { background: rgba(255,60,60,0.08); "
                "border: 1px solid #5f2d2d; color: #ff8888; border-radius: 4px; "
                "padding: 5px 10px; font-size: 11.5px; }"
                "QPushButton:hover { background: rgba(255,60,60,0.15); color: #ff6b6b; }"
            )
        else:
            self.setStyleSheet(
                "QPushButton { background: #161a20; border: 1px solid #323a46; "
                "color: #b6bdc9; border-radius: 4px; padding: 5px 10px; "
                "font-size: 11.5px; }"
                "QPushButton:hover { background: #1c2129; color: #e8ecf2; border-color: #3e4757; }"
            )


class TierPipelineStrip(QFrame):
    """Pipeline 가로 스트립 — 여러 Tier 노드 + 연결선."""

    tier_clicked = Signal(int)
    resume_requested = Signal()
    stop_requested = Signal()
    rerun_requested = Signal()

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setFixedHeight(132)
        self.setStyleSheet(
            "TierPipelineStrip { "
            "background: #101318; "
            "border-top: 1px solid #262c36; "
            "}"
        )

        self._nodes: list[_TierNode] = []

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # 헤더 (제목 + Resume/Stop/다시 실행 버튼)
        header = QFrame()
        header.setFixedHeight(44)
        header.setStyleSheet("background: transparent; border-bottom: 1px solid #262c36;")
        h_layout = QHBoxLayout(header)
        h_layout.setContentsMargins(14, 0, 14, 0)
        h_layout.setSpacing(8)

        self._title_label = QLabel()
        self._title_label.setTextFormat(Qt.RichText)
        self._title_label.setStyleSheet(
            "color: #e8ecf2; font-size: 12px; font-weight: 600; "
            "letter-spacing: 0.5px; background: transparent;"
        )
        self.set_title_info(current=0, total=0)
        h_layout.addWidget(self._title_label)
        h_layout.addStretch()

        self.resume_btn = _PipelineBtn("▶  Resume", "default")
        self.resume_btn.clicked.connect(self.resume_requested.emit)
        h_layout.addWidget(self.resume_btn)

        self.stop_btn = _PipelineBtn("■  Stop", "stop")
        self.stop_btn.clicked.connect(self.stop_requested.emit)
        h_layout.addWidget(self.stop_btn)

        self.rerun_btn = _PipelineBtn("다시 실행", "primary")
        self.rerun_btn.clicked.connect(self.rerun_requested.emit)
        h_layout.addWidget(self.rerun_btn)

        root.addWidget(header)

        # 노드 컨테이너 (custom paint로 연결선 그림)
        self._nodes_container = _NodesContainer(self)
        root.addWidget(self._nodes_container, stretch=1)

    def set_title_info(self, current: int, total: int) -> None:
        self._title_label.setText(
            f"파이프라인 진행 "
            f"<span style='color:#5a6270'>·</span> "
            f"Tier <b style='color:#4ea3ff'>{current}</b> / {total}"
        )

    def set_tiers(self, tiers: list[tuple[str, str]]) -> None:
        """tiers: [(name, engine), ...]"""
        self._nodes_container.set_tiers(tiers)
        self._nodes = self._nodes_container.nodes()
        self.set_title_info(current=0, total=len(tiers))

    def set_status(self, index: int, status: TierStatus) -> None:
        if 0 <= index < len(self._nodes):
            self._nodes[index].set_status(status)
            self._nodes_container.update()
            # 현재 진행 tier 번호 업데이트
            active_idx = next(
                (i for i, n in enumerate(self._nodes) if n._status == "active"),
                None,
            )
            done_count = sum(1 for n in self._nodes if n._status == "done")
            cur = (active_idx + 1) if active_idx is not None else done_count
            self.set_title_info(current=cur, total=len(self._nodes))


class _NodesContainer(QWidget):
    """노드 + 연결선 그리기."""

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._nodes: list[_TierNode] = []
        self._layout = QHBoxLayout(self)
        self._layout.setContentsMargins(12, 8, 12, 8)
        self._layout.setSpacing(0)

    def set_tiers(self, tiers: list[tuple[str, str]]) -> None:
        # 기존 노드 제거
        while self._layout.count():
            item = self._layout.takeAt(0)
            w = item.widget()
            if w:
                w.deleteLater()
        self._nodes.clear()

        for i, (name, engine) in enumerate(tiers, start=1):
            node = _TierNode(i, name, engine, self)
            self._nodes.append(node)
            self._layout.addWidget(node, 1)

    def nodes(self) -> list[_TierNode]:
        return self._nodes

    def paintEvent(self, event) -> None:  # type: ignore[override]
        super().paintEvent(event)
        if len(self._nodes) < 2:
            return
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        for i in range(len(self._nodes) - 1):
            a = self._nodes[i]
            b = self._nodes[i + 1]
            ax = a.x() + a.width() / 2 + 22
            bx = b.x() + b.width() / 2 - 22
            y = a.y() + 22  # 원형 중앙 높이

            status_a = a._status
            status_b = b._status
            if status_a == "done" and status_b in ("done", "active"):
                line_color = QColor("#4ade80")
            elif status_a == "done" and status_b == "pending":
                line_color = QColor("#4ade80")
            else:
                line_color = QColor("#323a46")

            pen = QPen(line_color, 2)
            p.setPen(pen)
            p.drawLine(int(ax), int(y), int(bx), int(y))
        p.end()
