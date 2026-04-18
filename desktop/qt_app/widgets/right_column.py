"""우측 340px 컬럼 — Job / Quality / Export 3탭.

디자인 스펙 기반:
- Job: 상태카드 + KPI 그리드 2×2 + 로그 (필터 chip + 검색)
- Quality: checkMesh 메트릭 바 + 셀 구성 + 합격 기준
- Export: 출력 경로 + 포맷 라디오 + 후처리 체크 + 저장 버튼
"""
from __future__ import annotations

try:
    import matplotlib
    matplotlib.use("QtAgg")
    from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg
    from matplotlib.figure import Figure
    _MPL_AVAILABLE = True
except Exception:
    _MPL_AVAILABLE = False
    FigureCanvasQTAgg = None  # type: ignore[assignment, misc]
    Figure = None  # type: ignore[assignment]

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QIntValidator
from PySide6.QtWidgets import (
    QButtonGroup,
    QCheckBox,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPlainTextEdit,
    QPushButton,
    QRadioButton,
    QScrollArea,
    QStackedWidget,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)


# ═══════════════════════════════════════════════════════════════════════════
# 공통 스타일
# ═══════════════════════════════════════════════════════════════════════════
_SECTION_TITLE_CSS = (
    "color: #5a6270; font-size: 11px; font-weight: 600; "
    "letter-spacing: 1.5px; text-transform: uppercase; background: transparent;"
)


def _section_title(text: str, subtitle: str | None = None) -> QLabel:
    lbl = QLabel()
    lbl.setTextFormat(Qt.RichText)
    html = f"<span style='color:#5a6270;font-weight:600;letter-spacing:1.5px'>{text.upper()}</span>"
    if subtitle:
        html += (
            f"<span style='color:#818a99;font-weight:400;letter-spacing:0;"
            f"font-family:JetBrains Mono,monospace;font-size:10.5px'>  {subtitle}</span>"
        )
    lbl.setText(html)
    lbl.setStyleSheet("background: transparent;")
    return lbl


# ═══════════════════════════════════════════════════════════════════════════
# Job 탭
# ═══════════════════════════════════════════════════════════════════════════
class _StatusCard(QFrame):
    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setStyleSheet(
            "_StatusCard { background: transparent; border: none; "
            "border-bottom: 1px solid #262c36; }"
        )
        layout = QVBoxLayout(self)
        layout.setContentsMargins(14, 14, 14, 14)
        layout.setSpacing(8)

        row1 = QHBoxLayout()
        row1.setSpacing(8)
        self._badge = QLabel("READY")
        self._badge.setStyleSheet(
            "background: rgba(78,163,255,0.15); color: #4ea3ff; "
            "border: 1px solid rgba(78,163,255,0.3); border-radius: 3px; "
            "padding: 3px 8px; font-size: 10px; font-weight: 600; "
            "letter-spacing: 1px; font-family: 'JetBrains Mono', monospace;"
        )
        row1.addWidget(self._badge)
        row1.addStretch()
        self._job_id = QLabel("#—")
        self._job_id.setStyleSheet(
            "color: #5a6270; font-size: 11px; font-family: 'JetBrains Mono', monospace; "
            "background: transparent;"
        )
        row1.addWidget(self._job_id)
        layout.addLayout(row1)

        self._file = QLabel("No file loaded")
        self._file.setWordWrap(True)
        self._file.setStyleSheet(
            "color: #e8ecf2; font-size: 13.5px; font-weight: 600; background: transparent;"
        )
        layout.addWidget(self._file)

        self._sub = QLabel("—")
        self._sub.setStyleSheet(
            "color: #818a99; font-size: 11px; "
            "font-family: 'JetBrains Mono', monospace; background: transparent;"
        )
        layout.addWidget(self._sub)

    def set_state(
        self,
        badge: str = "READY",
        badge_level: str = "info",
        job_id: str | None = None,
        filename: str | None = None,
        subtitle: str | None = None,
    ) -> None:
        colors = {
            "info": ("rgba(78,163,255,0.15)", "#4ea3ff", "rgba(78,163,255,0.3)"),
            "running": ("rgba(78,163,255,0.15)", "#4ea3ff", "rgba(78,163,255,0.3)"),
            "ok": ("rgba(74,222,128,0.15)", "#4ade80", "rgba(74,222,128,0.3)"),
            "warn": ("rgba(245,180,84,0.15)", "#f5b454", "rgba(245,180,84,0.3)"),
            "err": ("rgba(255,107,107,0.15)", "#ff6b6b", "rgba(255,107,107,0.3)"),
        }
        bg, fg, br = colors.get(badge_level, colors["info"])
        self._badge.setText(badge.upper())
        self._badge.setStyleSheet(
            f"background: {bg}; color: {fg}; border: 1px solid {br}; "
            f"border-radius: 3px; padding: 3px 8px; font-size: 10px; font-weight: 600; "
            f"letter-spacing: 1px; font-family: 'JetBrains Mono', monospace;"
        )
        if job_id is not None:
            self._job_id.setText(f"#{job_id}")
        if filename is not None:
            self._file.setText(filename)
        if subtitle is not None:
            self._sub.setText(subtitle)


class _KPICell(QFrame):
    def __init__(self, label: str, parent=None) -> None:
        super().__init__(parent)
        self.setStyleSheet("_KPICell { background: #101318; border: none; }")
        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(2)
        lbl = QLabel(label.upper())
        lbl.setStyleSheet(
            "color: #5a6270; font-size: 9.5px; font-weight: 600; "
            "letter-spacing: 1.5px; background: transparent;"
        )
        layout.addWidget(lbl)

        self._val = QLabel("—")
        self._val.setTextFormat(Qt.RichText)
        self._val.setStyleSheet(
            "color: #e8ecf2; font-size: 19px; font-weight: 600; "
            "font-family: 'JetBrains Mono', monospace; background: transparent;"
        )
        layout.addWidget(self._val)

        self._trend = QLabel("")
        self._trend.setStyleSheet(
            "color: #818a99; font-size: 10px; "
            "font-family: 'JetBrains Mono', monospace; background: transparent;"
        )
        layout.addWidget(self._trend)

    def set_value(self, value: str, unit: str = "", trend: str = "", trend_kind: str = "") -> None:
        html = value
        if unit:
            html += f"<span style='font-size:11px;color:#5a6270;font-weight:400'>  {unit}</span>"
        self._val.setText(html)
        color = {"up": "#4ade80", "dn": "#f5b454"}.get(trend_kind, "#818a99")
        self._trend.setText(trend)
        self._trend.setStyleSheet(
            f"color: {color}; font-size: 10px; "
            f"font-family: 'JetBrains Mono', monospace; background: transparent;"
        )


class _LogFilterChip(QPushButton):
    def __init__(self, name: str, color: str, parent=None) -> None:
        super().__init__(parent)
        self._name = name
        self._color = color
        self._count = 0
        self._active = False
        self.setCursor(Qt.PointingHandCursor)
        self.setFlat(True)
        self.setCheckable(True)
        self._refresh()

    def set_count(self, count: int) -> None:
        self._count = count
        self._refresh()

    def set_active(self, active: bool) -> None:
        self._active = active
        self.setChecked(active)
        self._refresh()

    def _refresh(self) -> None:
        self.setText(f"{self._name}  {self._count}")
        if self._active:
            bg = f"rgba(78,163,255,0.12)"
            border = "#4ea3ff"
        else:
            bg = "#161a20"
            border = "#323a46"
        self.setStyleSheet(
            f"QPushButton {{ background: {bg}; border: 1px solid {border}; "
            f"border-radius: 3px; padding: 2px 8px; color: {self._color}; "
            f"font-size: 10px; letter-spacing: 0.5px; "
            f"font-family: 'JetBrains Mono', monospace; }}"
        )


class JobPane(QWidget):
    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # 상태 카드
        self.status_card = _StatusCard()
        root.addWidget(self.status_card)

        # KPI 그리드 2×2
        kpi_frame = QFrame()
        kpi_frame.setStyleSheet(
            "QFrame { background: #262c36; border: none; border-bottom: 1px solid #262c36; }"
        )
        grid = QGridLayout(kpi_frame)
        grid.setContentsMargins(0, 0, 0, 0)
        grid.setSpacing(1)
        self.kpi_elapsed = _KPICell("경과")
        self.kpi_cells = _KPICell("셀 수")
        self.kpi_hex = _KPICell("Hex 비율")
        self.kpi_ram = _KPICell("Peak RAM")
        grid.addWidget(self.kpi_elapsed, 0, 0)
        grid.addWidget(self.kpi_cells, 0, 1)
        grid.addWidget(self.kpi_hex, 1, 0)
        grid.addWidget(self.kpi_ram, 1, 1)
        root.addWidget(kpi_frame)

        # 로그 툴바 — 필터 chip + 검색
        log_toolbar = QFrame()
        log_toolbar.setStyleSheet(
            "QFrame { background: #101318; border: none; border-bottom: 1px solid #262c36; }"
        )
        lt_layout = QVBoxLayout(log_toolbar)
        lt_layout.setContentsMargins(12, 10, 12, 10)
        lt_layout.setSpacing(8)

        chip_row = QHBoxLayout()
        chip_row.setSpacing(4)
        self.chip_all = _LogFilterChip("ALL", "#b6bdc9")
        self.chip_info = _LogFilterChip("INFO", "#4ea3ff")
        self.chip_warn = _LogFilterChip("WARN", "#f5b454")
        self.chip_err = _LogFilterChip("ERR", "#ff6b6b")
        self.chip_dbg = _LogFilterChip("DBG", "#5a6270")
        self.chip_all.set_active(True)
        for chip in (self.chip_all, self.chip_info, self.chip_warn, self.chip_err, self.chip_dbg):
            chip_row.addWidget(chip)
        chip_row.addStretch()
        lt_layout.addLayout(chip_row)

        self.log_search = QLineEdit()
        self.log_search.setPlaceholderText("검색…")
        self.log_search.setStyleSheet(
            "QLineEdit { background: #05070a; border: 1px solid #323a46; "
            "color: #b6bdc9; font-family: 'JetBrains Mono', monospace; "
            "font-size: 11.5px; padding: 5px 8px; border-radius: 4px; }"
            "QLineEdit:focus { border-color: #4ea3ff; }"
        )
        lt_layout.addWidget(self.log_search)
        root.addWidget(log_toolbar)

        # 로그 박스
        self.log_box = QPlainTextEdit()
        self.log_box.setReadOnly(True)
        self.log_box.setStyleSheet(
            "QPlainTextEdit { background: #05070a; color: #b6bdc9; "
            "font-family: 'JetBrains Mono', monospace; font-size: 11px; "
            "border: none; line-height: 1.65; }"
        )
        self.log_box.setToolTip("우클릭 → 로그 복사 / 파일로 저장 / 지우기")
        self.log_box.setContextMenuPolicy(Qt.CustomContextMenu)
        self.log_box.customContextMenuRequested.connect(self._on_log_context_menu)

        _log_hint = QLabel("💡 우클릭으로 복사·저장")
        _log_hint.setStyleSheet(
            "QLabel { color: #5a6270; font-size: 10px; padding: 1px 4px; }"
        )
        _log_hint.setAlignment(Qt.AlignRight)
        root.addWidget(_log_hint)
        root.addWidget(self.log_box, stretch=1)

    def _on_log_context_menu(self, pos) -> None:
        """로그 박스 우클릭 컨텍스트 메뉴."""
        from PySide6.QtWidgets import QMenu, QFileDialog, QApplication
        menu = QMenu(self)
        menu.setStyleSheet(
            "QMenu { background: #1c2129; border: 1px solid #323a46; "
            "border-radius: 6px; padding: 4px; color: #b6bdc9; }"
            "QMenu::item { padding: 6px 18px 6px 12px; border-radius: 4px; font-size: 12px; }"
            "QMenu::item:selected { background: #4ea3ff; color: #05111e; }"
            "QMenu::separator { height: 1px; background: #262c36; margin: 4px 2px; }"
        )
        act_copy = menu.addAction("로그 복사")
        menu.addSeparator()
        act_save = menu.addAction("로그 저장...")
        act_clear = menu.addAction("로그 지우기")

        action = menu.exec(self.log_box.mapToGlobal(pos))
        if action == act_copy:
            text = self.log_box.toPlainText()
            QApplication.clipboard().setText(text)
        elif action == act_save:
            path, _ = QFileDialog.getSaveFileName(
                self, "로그 저장", "autotessell.log.txt",
                "텍스트 파일 (*.txt);;모든 파일 (*)"
            )
            if path:
                try:
                    from pathlib import Path as _Path
                    _Path(path).write_text(
                        self.log_box.toPlainText(), encoding="utf-8"
                    )
                except Exception as e:
                    from PySide6.QtWidgets import QMessageBox
                    QMessageBox.warning(self, "저장 실패", str(e))
        elif action == act_clear:
            self.log_box.clear()


# ═══════════════════════════════════════════════════════════════════════════
# Quality 탭
# ═══════════════════════════════════════════════════════════════════════════
class _QualityBar(QFrame):
    """qname (110px) | 바 (flex) | qval (52px)"""

    def __init__(self, name: str, parent=None) -> None:
        super().__init__(parent)
        self.setStyleSheet("_QualityBar { background: transparent; border: none; }")
        row = QHBoxLayout(self)
        row.setContentsMargins(0, 3, 0, 3)
        row.setSpacing(10)

        self._name_lbl = QLabel(name)
        self._name_lbl.setFixedWidth(110)
        self._name_lbl.setStyleSheet(
            "color: #b6bdc9; font-size: 11.5px; background: transparent;"
        )
        row.addWidget(self._name_lbl)

        self._bar_bg = QFrame()
        self._bar_bg.setFixedHeight(4)
        self._bar_bg.setStyleSheet(
            "background: #1c2129; border-radius: 2px;"
        )
        self._fill = QFrame(self._bar_bg)
        self._fill.setStyleSheet(
            "background: qlineargradient(x1:0, y1:0, x2:1, y2:0, "
            "stop:0 #4ade80, stop:1 #6ee6a0); border-radius: 2px;"
        )
        row.addWidget(self._bar_bg, stretch=1)

        self._val_lbl = QLabel("—")
        self._val_lbl.setFixedWidth(60)
        self._val_lbl.setAlignment(Qt.AlignRight)
        self._val_lbl.setStyleSheet(
            "color: #e8ecf2; font-size: 11px; font-weight: 500; "
            "font-family: 'JetBrains Mono', monospace; background: transparent;"
        )
        row.addWidget(self._val_lbl)

    def set_value(self, fill_ratio: float, text: str, warn: bool = False) -> None:
        self._fill_ratio = max(0.0, min(1.0, fill_ratio))
        w = int(self._bar_bg.width() * self._fill_ratio)
        if w <= 0:
            w = 1
        self._fill.setGeometry(0, 0, w, 4)
        if warn:
            self._fill.setStyleSheet(
                "background: qlineargradient(x1:0, y1:0, x2:1, y2:0, "
                "stop:0 #f5b454, stop:1 #ffcc6b); border-radius: 2px;"
            )
        self._val_lbl.setText(text)

    def resizeEvent(self, event):  # type: ignore[override]
        super().resizeEvent(event)
        # fill 비율을 유지하면서 바 너비 재계산
        w = self._bar_bg.width()
        if not hasattr(self, "_fill_ratio") or w <= 0:
            return
        self._fill.setGeometry(0, 0, max(1, int(w * self._fill_ratio)), 4)


class _PassRow(QFrame):
    def __init__(self, text: str, parent=None) -> None:
        super().__init__(parent)
        self.setStyleSheet(
            "_PassRow { background: transparent; border: none; "
            "border-bottom: 1px dashed #262c36; }"
        )
        row = QHBoxLayout(self)
        row.setContentsMargins(0, 6, 0, 6)
        row.setSpacing(8)
        self._dot = QLabel()
        self._dot.setFixedSize(8, 8)
        self._dot.setStyleSheet("background: #5a6270; border-radius: 4px;")
        row.addWidget(self._dot)
        self._txt = QLabel(text)
        self._txt.setStyleSheet(
            "color: #b6bdc9; font-size: 11.5px; background: transparent;"
        )
        row.addWidget(self._txt)
        row.addStretch()
        self._verdict = QLabel("PEND")
        self._verdict.setStyleSheet(
            "color: #5a6270; font-size: 10.5px; font-weight: 600; "
            "font-family: 'JetBrains Mono', monospace; background: transparent;"
        )
        row.addWidget(self._verdict)

    def set_verdict(self, kind: str, label: str) -> None:
        colors = {"ok": "#4ade80", "warn": "#f5b454", "err": "#ff6b6b", "pend": "#5a6270"}
        c = colors.get(kind, "#5a6270")
        self._dot.setStyleSheet(f"background: {c}; border-radius: 4px;")
        self._verdict.setText(label)
        self._verdict.setStyleSheet(
            f"color: {c}; font-size: 10.5px; font-weight: 600; "
            f"font-family: 'JetBrains Mono', monospace; background: transparent;"
        )


class _HistogramCanvas(QWidget):
    """matplotlib FigureCanvas 기반 품질 분포 히스토그램 (3개 서브플롯).

    Aspect Ratio / Skewness / Non-orthogonality — CFD 핵심 메트릭.
    """

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setMinimumHeight(200)
        self._canvas = None
        self._fig = None
        self._layout = None

        if _MPL_AVAILABLE and Figure is not None:
            self._fig = Figure(figsize=(4.5, 2.0), dpi=90, tight_layout=True)
            self._fig.patch.set_facecolor("#101318")
            self._canvas = FigureCanvasQTAgg(self._fig)  # type: ignore[misc]
            from PySide6.QtWidgets import QVBoxLayout as _VBox
            lay = _VBox(self)
            lay.setContentsMargins(0, 0, 0, 0)
            lay.addWidget(self._canvas)
        else:
            from PySide6.QtWidgets import QLabel as _QLabel, QVBoxLayout as _VBox
            lay = _VBox(self)
            lbl = _QLabel("matplotlib 미설치 — 히스토그램 비활성")
            lbl.setStyleSheet("color: #5a6270; font-size: 11px;")
            lay.addWidget(lbl)

    def update_histograms(
        self,
        aspect_data: list[float] | None = None,
        skew_data: list[float] | None = None,
        non_ortho_data: list[float] | None = None,
    ) -> None:
        if self._fig is None or self._canvas is None:
            return
        self._fig.clear()
        axs = self._fig.subplots(1, 3)
        _style = {"edgecolor": "none", "alpha": 0.85}

        def _draw(ax, data, title: str, color: str, threshold: float | None = None) -> None:
            ax.set_facecolor("#161a20")
            ax.tick_params(colors="#818a99", labelsize=7)
            for spine in ax.spines.values():
                spine.set_edgecolor("#323a46")
            ax.set_title(title, color="#b6bdc9", fontsize=8, pad=3)
            if data and len(data) > 1:
                import numpy as _np
                arr = _np.asarray(data, dtype=float)
                _d = _np.clip(arr, 0, _np.percentile(arr, 99))
                ax.hist(_d, bins=30, color=color, **_style)
                # OpenFOAM 한계선 표시 (있는 경우)
                if threshold is not None:
                    ax.axvline(
                        x=threshold, color="#ff6b6b", linestyle="--",
                        linewidth=1.0, alpha=0.7,
                    )
            else:
                ax.text(0.5, 0.5, "데이터 없음", ha="center", va="center",
                        transform=ax.transAxes, color="#5a6270", fontsize=8)

        # OpenFOAM 전형적 임계값
        _draw(axs[0], aspect_data, "Aspect Ratio", "#4ea3ff", threshold=100.0)
        _draw(axs[1], skew_data, "Skewness", "#f5b454", threshold=4.0)
        _draw(axs[2], non_ortho_data, "Non-ortho °", "#ff7b54", threshold=65.0)
        self._canvas.draw()


class QualityPane(QWidget):
    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setStyleSheet("QScrollArea { border: none; background: transparent; }")
        root_layout = QVBoxLayout(self)
        root_layout.setContentsMargins(0, 0, 0, 0)
        root_layout.setSpacing(0)
        root_layout.addWidget(scroll)

        inner = QWidget()
        scroll.setWidget(inner)
        v = QVBoxLayout(inner)
        v.setContentsMargins(14, 14, 14, 14)
        v.setSpacing(14)

        # ── checkMesh 품질 ─────────────────────────────────
        sec1 = QFrame()
        sec1.setStyleSheet(
            "QFrame { border: none; border-bottom: 1px solid #262c36; }"
        )
        sec1_v = QVBoxLayout(sec1)
        sec1_v.setContentsMargins(0, 0, 0, 14)
        sec1_v.setSpacing(4)
        sec1_v.addWidget(_section_title("checkMesh 품질", "preview"))

        self.q_aspect = _QualityBar("Max aspect ratio")
        self.q_skew = _QualityBar("Max skewness")
        self.q_nonortho = _QualityBar("Max non-ortho")
        self.q_min_area = _QualityBar("Min face area")
        self.q_min_vol = _QualityBar("Min volume")
        self.q_neg_vols = _QualityBar("Negative vols")
        for b in (
            self.q_aspect, self.q_skew, self.q_nonortho,
            self.q_min_area, self.q_min_vol, self.q_neg_vols,
        ):
            sec1_v.addWidget(b)
        v.addWidget(sec1)

        # ── 품질 분포 히스토그램 (인터랙티브 matplotlib) ──────────────
        sec_hist = QFrame()
        sec_hist.setStyleSheet(
            "QFrame { border: none; border-bottom: 1px solid #262c36; }"
        )
        sec_hist_v = QVBoxLayout(sec_hist)
        sec_hist_v.setContentsMargins(0, 0, 0, 14)
        sec_hist_v.setSpacing(6)
        sec_hist_v.addWidget(_section_title("품질 분포"))
        self.histogram = _HistogramCanvas()
        sec_hist_v.addWidget(self.histogram)
        v.addWidget(sec_hist)

        # ── 셀 구성 ─────────────────────────────────
        sec2 = QFrame()
        sec2.setStyleSheet(
            "QFrame { border: none; border-bottom: 1px solid #262c36; }"
        )
        sec2_v = QVBoxLayout(sec2)
        sec2_v.setContentsMargins(0, 0, 0, 14)
        sec2_v.setSpacing(6)
        sec2_v.addWidget(_section_title("셀 구성"))

        self.cell_comp_rows: dict[str, _QualityBar] = {}
        for name, color in [
            ("Hexahedra", "#9b87ff"),
            ("Prisms", "#4ea3ff"),
            ("Polyhedra", "#5ee5d6"),
            ("Tetrahedra", "#f5b454"),
        ]:
            row = _QualityBar(name)
            row._fill.setStyleSheet(
                f"background: {color}; border-radius: 2px;"
            )
            self.cell_comp_rows[name] = row
            sec2_v.addWidget(row)
        v.addWidget(sec2)

        # ── 합격 기준 ─────────────────────────────────
        sec3 = QFrame()
        sec3.setStyleSheet("QFrame { border: none; }")
        sec3_v = QVBoxLayout(sec3)
        sec3_v.setContentsMargins(0, 0, 0, 0)
        sec3_v.setSpacing(0)
        sec3_v.addWidget(_section_title("합격 기준"))

        self.pass_rows: dict[str, _PassRow] = {}
        for key, label in [
            ("nonortho", "Non-ortho < 65°"),
            ("skew", "Skewness < 4.0"),
            ("aspect", "Aspect ratio < 100"),
            ("negvol", "Negative volumes = 0"),
        ]:
            row = _PassRow(label)
            self.pass_rows[key] = row
            sec3_v.addWidget(row)
        v.addWidget(sec3)

        v.addStretch()

    def set_metric(self, key: str, fill: float, text: str, warn: bool = False) -> None:
        m = {
            "aspect": self.q_aspect, "skew": self.q_skew,
            "nonortho": self.q_nonortho, "min_area": self.q_min_area,
            "min_vol": self.q_min_vol, "neg_vols": self.q_neg_vols,
        }
        if key in m:
            m[key].set_value(fill, text, warn)


# ═══════════════════════════════════════════════════════════════════════════
# Export 탭
# ═══════════════════════════════════════════════════════════════════════════
class ExportPane(QWidget):
    save_requested = Signal(str)  # 선택된 format

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setStyleSheet("QScrollArea { border: none; background: transparent; }")
        root_layout = QVBoxLayout(self)
        root_layout.setContentsMargins(0, 0, 0, 0)
        root_layout.setSpacing(0)
        root_layout.addWidget(scroll, stretch=1)

        inner = QWidget()
        scroll.setWidget(inner)
        v = QVBoxLayout(inner)
        v.setContentsMargins(14, 14, 14, 14)
        v.setSpacing(14)

        # 출력 디렉토리
        sec1 = QFrame()
        sec1.setStyleSheet(
            "QFrame { border: none; border-bottom: 1px solid #262c36; }"
        )
        sec1_v = QVBoxLayout(sec1)
        sec1_v.setContentsMargins(0, 0, 0, 14)
        sec1_v.setSpacing(6)
        sec1_v.addWidget(_section_title("출력 디렉토리"))

        path_row = QHBoxLayout()
        path_row.setSpacing(6)
        self.path_box = QLineEdit()
        self.path_box.setPlaceholderText("~/meshes/…")
        self.path_box.setStyleSheet(
            "QLineEdit { background: #161a20; border: 1px solid #323a46; "
            "color: #b6bdc9; font-family: 'JetBrains Mono', monospace; "
            "font-size: 11.5px; padding: 6px 10px; border-radius: 4px; }"
            "QLineEdit:focus { border-color: #4ea3ff; }"
        )
        path_row.addWidget(self.path_box)
        self.browse_btn = QPushButton("⋯")
        self.browse_btn.setFixedSize(34, 32)
        self.browse_btn.setStyleSheet(
            "QPushButton { background: #161a20; border: 1px solid #323a46; "
            "color: #818a99; border-radius: 4px; font-size: 14px; }"
            "QPushButton:hover { background: #1c2129; border-color: #3e4757; color: #e8ecf2; }"
        )
        path_row.addWidget(self.browse_btn)
        sec1_v.addLayout(path_row)
        v.addWidget(sec1)

        # 포맷 선택
        sec2 = QFrame()
        sec2.setStyleSheet(
            "QFrame { border: none; border-bottom: 1px solid #262c36; }"
        )
        sec2_v = QVBoxLayout(sec2)
        sec2_v.setContentsMargins(0, 0, 0, 14)
        sec2_v.setSpacing(2)
        sec2_v.addWidget(_section_title("포맷 선택"))

        self._fmt_group = QButtonGroup(self)
        self._fmt_value = "openfoam"
        for value, label, ext in [
            ("openfoam", "OpenFOAM", "polyMesh/"),
            ("vtu", "VTU", ".vtu"),
            ("cgns", "CGNS", ".cgns"),
            ("nastran", "Nastran", ".nas"),
            ("fluent", "Fluent MSH", ".msh"),
            ("gmsh", "Gmsh", ".msh2"),
        ]:
            row = QFrame()
            row.setStyleSheet(
                "QFrame { background: transparent; border: none; }"
                "QFrame:hover { background: #161a20; border-radius: 4px; }"
            )
            rl = QHBoxLayout(row)
            rl.setContentsMargins(8, 4, 8, 4)
            rl.setSpacing(8)

            rb = QRadioButton()
            if value == "openfoam":
                rb.setChecked(True)
            rb.toggled.connect(lambda checked, v=value: self._on_fmt(v) if checked else None)
            self._fmt_group.addButton(rb)
            rl.addWidget(rb)

            name = QLabel(label)
            name.setStyleSheet(
                "color: #b6bdc9; font-size: 11.5px; background: transparent;"
            )
            rl.addWidget(name, stretch=1)

            ext_lbl = QLabel(ext)
            ext_lbl.setStyleSheet(
                "color: #5a6270; font-size: 10.5px; "
                "font-family: 'JetBrains Mono', monospace; background: transparent;"
            )
            rl.addWidget(ext_lbl)

            sec2_v.addWidget(row)
        v.addWidget(sec2)

        # 후처리
        sec3 = QFrame()
        sec3.setStyleSheet("QFrame { border: none; }")
        sec3_v = QVBoxLayout(sec3)
        sec3_v.setContentsMargins(0, 0, 0, 10)
        sec3_v.setSpacing(6)
        sec3_v.addWidget(_section_title("후처리"))

        self.chk_report = QCheckBox("checkMesh 리포트 생성 (JSON)")
        self.chk_report.setChecked(True)
        self.chk_histo = QCheckBox("품질 요약 차트 PNG")
        self.chk_histo.setChecked(True)
        self.chk_paraview = QCheckBox("Paraview state 파일 첨부")
        self.chk_zip = QCheckBox("ZIP으로 압축")
        for chk in (self.chk_report, self.chk_histo, self.chk_paraview, self.chk_zip):
            chk.setStyleSheet(
                "QCheckBox { color: #b6bdc9; font-size: 11.5px; "
                "background: transparent; padding: 2px 0; }"
            )
            sec3_v.addWidget(chk)
        v.addWidget(sec3)

        v.addStretch()

        # 저장 버튼 바 (sticky bottom)
        save_bar = QFrame()
        save_bar.setStyleSheet(
            "QFrame { background: #101318; border: none; border-top: 1px solid #262c36; }"
        )
        save_layout = QHBoxLayout(save_bar)
        save_layout.setContentsMargins(14, 12, 14, 12)
        save_layout.setSpacing(8)

        self.open_folder_btn = QPushButton("폴더 열기")
        self.open_folder_btn.setStyleSheet(
            "QPushButton { background: #161a20; border: 1px solid #323a46; "
            "color: #b6bdc9; border-radius: 5px; padding: 9px 12px; "
            "font-size: 12px; font-weight: 500; }"
            "QPushButton:hover { background: #1c2129; border-color: #3e4757; color: #e8ecf2; }"
        )
        save_layout.addWidget(self.open_folder_btn, stretch=1)

        self.save_btn = QPushButton("저장하기")
        self.save_btn.setStyleSheet(
            "QPushButton { background: #4ea3ff; border: 1px solid #4ea3ff; "
            "color: #05111e; border-radius: 5px; padding: 9px 12px; "
            "font-size: 12px; font-weight: 600; }"
            "QPushButton:hover { background: #6ab4ff; border-color: #6ab4ff; }"
        )
        self.save_btn.clicked.connect(lambda: self.save_requested.emit(self._fmt_value))
        save_layout.addWidget(self.save_btn, stretch=1)

        root_layout.addWidget(save_bar)

    def _on_fmt(self, value: str) -> None:
        self._fmt_value = value

    def get_export_options(self) -> dict:
        """현재 선택된 export 설정 반환."""
        return {
            "format": self._fmt_value,
            "output_dir": self.path_box.text().strip(),
            "report_json": self.chk_report.isChecked(),
            "quality_hist": self.chk_histo.isChecked(),
            "paraview_state": self.chk_paraview.isChecked(),
            "zip_output": self.chk_zip.isChecked(),
        }


# ═══════════════════════════════════════════════════════════════════════════
# 메인 우측 컬럼 컨테이너
# ═══════════════════════════════════════════════════════════════════════════
class RightColumn(QWidget):
    """디자인 스펙의 3-탭 우측 340px 컬럼 전체."""

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setFixedWidth(340)
        self.setStyleSheet(
            "background: #101318; border-left: 1px solid #262c36;"
        )

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        self.tabs = QTabWidget()
        self.tabs.setDocumentMode(True)
        self.tabs.setTabPosition(QTabWidget.North)
        self.tabs.setStyleSheet(
            "QTabWidget::pane { border: none; background: #101318; }"
            "QTabBar { background: transparent; }"
            "QTabBar::tab { background: transparent; color: #818a99; "
            "padding: 10px 16px; border: none; border-bottom: 2px solid transparent; "
            "font-size: 12px; font-weight: 500; min-width: 80px; }"
            "QTabBar::tab:selected { color: #e8ecf2; border-bottom-color: #4ea3ff; }"
            "QTabBar::tab:hover:!selected { color: #b6bdc9; }"
        )

        self.job_pane = JobPane()
        self.quality_pane = QualityPane()
        self.export_pane = ExportPane()

        self.tabs.addTab(self.job_pane, "Job")
        self.tabs.addTab(self.quality_pane, "Quality")
        self.tabs.addTab(self.export_pane, "Export")

        root.addWidget(self.tabs)
