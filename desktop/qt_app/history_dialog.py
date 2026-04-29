"""실행 이력 대시보드 다이얼로그."""
from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QAbstractItemView,
    QComboBox,
    QDialog,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
)

from desktop.qt_app import history
from desktop.qt_app.main_window import get_dialog_qss, get_table_qss
from desktop.qt_app.widgets.dialog_mixin import EscDismissMixin


class HistoryDialog(EscDismissMixin, QDialog):
    """실행 이력 조회 + 필터."""

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("실행 이력")
        # 표준 LARGE 다이얼로그 크기
        self.setMinimumSize(960, 640)
        self.setStyleSheet(get_dialog_qss())

        self._all_entries: list[history.HistoryEntry] = history.load_all()

        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 14, 16, 14)
        layout.setSpacing(10)

        # ── 요약 라벨 ──────────────────────────────────────────
        self.summary_label = QLabel()
        self.summary_label.setStyleSheet(
            "color: #b6bdc9; font-size: 12px; background: transparent;"
        )
        layout.addWidget(self.summary_label)

        # ── 필터 행 ────────────────────────────────────────────
        flt_row = QHBoxLayout()
        flt_row.addWidget(QLabel("필터:"))
        self.status_combo = QComboBox()
        self.status_combo.addItem("전체", "all")
        self.status_combo.addItem("성공만", "success")
        self.status_combo.addItem("실패만", "failure")
        self.status_combo.currentIndexChanged.connect(self._refresh)
        flt_row.addWidget(self.status_combo)

        flt_row.addWidget(QLabel("검색:"))
        self.search_edit = QLineEdit()
        self.search_edit.setPlaceholderText("파일명/Tier/에러 메시지…")
        self.search_edit.textChanged.connect(self._refresh)
        flt_row.addWidget(self.search_edit, stretch=1)
        layout.addLayout(flt_row)

        # ── 테이블 ─────────────────────────────────────────────
        # beta2303 — Hausdorff (rel) 컬럼 추가 (상용 툴 'Surface Deviation' 동등).
        # beta2352 — pre-BL Self-Intersect 컬럼 추가 (P2.6 chain).
        # C-GUI-1 / beta2411 — mesh_integrity_suspect 컬럼 (3-engine catastrophic flag).
        # C-GUI-6 / beta2416 — BL prism 컬럼 (Pointwise T-Rex / cfMesh 동등).
        self.table = QTableWidget(0, 12)
        self.table.setHorizontalHeaderLabels([
            "시각", "입력", "Tier", "품질", "결과",
            "시간(s)", "셀수", "Non-ortho", "Hausdorff(rel)", "pre-BL SI",
            "Integrity", "BL prism",
        ])
        self.table.setStyleSheet(get_table_qss())
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table.setSortingEnabled(True)
        header = self.table.horizontalHeader()
        header.setSectionResizeMode(1, QHeaderView.Stretch)
        layout.addWidget(self.table, stretch=1)

        # ── 하단 버튼 ──────────────────────────────────────────
        btn_row = QHBoxLayout()
        btn_refresh = QPushButton("새로고침")
        btn_refresh.clicked.connect(self._reload_and_refresh)
        btn_row.addWidget(btn_refresh)

        btn_clear = QPushButton("이력 삭제")
        btn_clear.clicked.connect(self._on_clear)
        btn_row.addWidget(btn_clear)

        btn_export = QPushButton("CSV 내보내기")
        btn_export.clicked.connect(self._on_export_csv)
        btn_row.addWidget(btn_export)

        btn_row.addStretch()
        btn_close = QPushButton("닫기")
        btn_close.clicked.connect(self.accept)
        btn_row.addWidget(btn_close)
        layout.addLayout(btn_row)

        self._refresh()

    # ------------------------------------------------------------------

    def _filter(self) -> list[history.HistoryEntry]:
        status_filter = self.status_combo.currentData()
        search = (self.search_edit.text() or "").strip().lower()
        out = []
        for e in self._all_entries:
            if status_filter == "success" and not e.success:
                continue
            if status_filter == "failure" and e.success:
                continue
            if search:
                blob = " ".join([
                    e.input_file, e.tier_used, e.quality_level,
                    e.error or "",
                ]).lower()
                if search not in blob:
                    continue
            out.append(e)
        return out

    def _refresh(self) -> None:
        filtered = self._filter()
        self.table.setRowCount(len(filtered))
        for row, e in enumerate(filtered):
            # beta2303 — Hausdorff(rel) 표시. 상용 툴 임계 0.01 (1%) 초과면 빨강.
            _hr = getattr(e, "hausdorff_relative", None)
            _hr_text = f"{_hr*100:.2f}%" if _hr is not None else ""
            _hr_item = QTableWidgetItem(_hr_text)
            if _hr is not None and _hr > 0.01:
                _hr_item.setForeground(QColor("#ef4444"))
            elif _hr is not None and _hr > 0.0:
                _hr_item.setForeground(QColor("#22c55e"))
            # beta2352 — pre-BL SI count 표시. >0 빨강, 0 초록, None 회색.
            _si = getattr(e, "n_self_intersect_pre", None)
            _si_text = str(int(_si)) if _si is not None else ""
            _si_item = QTableWidgetItem(_si_text)
            if _si is not None:
                if int(_si) > 0:
                    _si_item.setForeground(QColor("#ef4444"))
                else:
                    _si_item.setForeground(QColor("#22c55e"))
            # C-GUI-1 / beta2411 — mesh_integrity_suspect column.
            # True (의심) 빨강 + ⚠ 경고; False 초록 + ✓.
            _int = bool(getattr(e, "mesh_integrity_suspect", False))
            _int_item = QTableWidgetItem("⚠" if _int else "✓")
            _int_item.setForeground(QColor("#ef4444" if _int else "#22c55e"))
            if _int:
                _int_item.setToolTip(
                    "Mesh integrity suspect: 셀 수가 비정상적으로 적음 "
                    "(catastrophic collapse 의심)",
                )
            # C-GUI-12 / beta2437 — BL prism column with color-coding.
            # C-GUI-13 / beta2439 — max_aspect_ratio 추가.
            _bl_prism = int(getattr(e, "bl_n_prism_cells", 0) or 0)
            _bl_lcr = int(getattr(e, "bl_lcr_n_reduced_verts", 0) or 0)
            _bl_max_ar = float(getattr(e, "bl_max_aspect_ratio", 0.0) or 0.0)
            _bl_prism_item = QTableWidgetItem(f"{_bl_prism:,}" if _bl_prism > 0 else "—")
            if _bl_prism > 0:
                _bl_prism_item.setForeground(QColor("#22c55e"))
                _tooltip_parts = [f"prism cells: {_bl_prism:,}"]
                if _bl_max_ar > 0:
                    _aspect_label = (
                        "OK" if _bl_max_ar < 1000 else
                        "high" if _bl_max_ar < 10000 else
                        "extreme (사용자 mesh 검토 권장)"
                    )
                    _tooltip_parts.append(
                        f"max aspect: {_bl_max_ar:,.0f} ({_aspect_label})",
                    )
                if _bl_lcr > 0:
                    _tooltip_parts.append(
                        f"LCR reduced verts: {_bl_lcr} (Pointwise T-Rex 동등)"
                    )
                _bl_prism_item.setToolTip("\n".join(_tooltip_parts))
            else:
                _bl_prism_item.setForeground(QColor("#5a6270"))
                _bl_prism_item.setToolTip("BL not executed or 0 prisms")
            items = [
                QTableWidgetItem(e.timestamp.replace("T", " ")),
                QTableWidgetItem(Path(e.input_file).name),
                QTableWidgetItem(e.tier_used or "—"),
                QTableWidgetItem(e.quality_level),
                QTableWidgetItem("✓" if e.success else "✗"),
                QTableWidgetItem(f"{e.elapsed_seconds:.1f}"),
                QTableWidgetItem(f"{e.n_cells:,}" if e.n_cells else ""),
                QTableWidgetItem(
                    f"{e.max_non_orthogonality:.1f}" if e.max_non_orthogonality else ""
                ),
                _hr_item,
                _si_item,
                _int_item,
                # C-GUI-6 / beta2416 — BL prism 셀 수 (Pointwise T-Rex 동등).
                # C-GUI-12 / beta2437 — 회색 (BL 미실행) 또는 초록 (실행됨).
                _bl_prism_item,
            ]
            # 결과 컬러
            if e.success:
                items[4].setForeground(QColor("#22c55e"))
            else:
                items[4].setForeground(QColor("#ef4444"))
                items[4].setToolTip(e.error or "")
            for col, it in enumerate(items):
                self.table.setItem(row, col, it)

        # 요약 갱신
        total = len(self._all_entries)
        ok = sum(1 for e in self._all_entries if e.success)
        fail = total - ok
        shown = len(filtered)
        self.summary_label.setText(
            f"전체 {total}건  |  성공 {ok}  |  실패 {fail}  |  "
            f"표시 중 {shown}건"
        )

    def _reload_and_refresh(self) -> None:
        self._all_entries = history.load_all()
        self._refresh()

    def _on_clear(self) -> None:
        resp = QMessageBox.question(
            self, "이력 삭제 확인",
            f"전체 {len(self._all_entries)}건 이력을 삭제합니다. 계속?",
            QMessageBox.Yes | QMessageBox.No,
        )
        if resp != QMessageBox.Yes:
            return
        history.clear()
        self._all_entries = []
        self._refresh()

    def _on_export_csv(self) -> None:
        from PySide6.QtWidgets import QFileDialog

        path, _ = QFileDialog.getSaveFileName(
            self, "CSV로 저장", "autotessell_history.csv",
            "CSV files (*.csv)",
        )
        if not path:
            return
        filtered = self._filter()
        try:
            # beta2303 — CSV 에 Hausdorff (distance + relative) 컬럼 포함.
            # beta2353 — pre_bl_self_intersect 도 CSV 에 포함 (P2.6 chain).
            # C-GUI-1 / beta2411 — mesh_integrity_suspect 도 CSV 에 포함.
            # C-GUI-7 / beta2417 — BL prism / LCR / aniso_split 도 CSV 에 포함.
            lines = [
                "timestamp,input_file,tier,quality,success,"
                "elapsed_seconds,n_cells,max_aspect_ratio,"
                "max_skewness,max_non_orthogonality,"
                "hausdorff_distance,hausdorff_relative,"
                "pre_bl_self_intersect,mesh_integrity_suspect,"
                "bl_n_prism_cells,bl_lcr_n_reduced_verts,"
                "bl_aniso_split_n_would_split,error"
            ]
            for e in filtered:
                _hd = getattr(e, "hausdorff_distance", None)
                _hr = getattr(e, "hausdorff_relative", None)
                _si = getattr(e, "n_self_intersect_pre", None)
                _int = bool(getattr(e, "mesh_integrity_suspect", False))
                _bl = int(getattr(e, "bl_n_prism_cells", 0) or 0)
                _lcr = int(getattr(e, "bl_lcr_n_reduced_verts", 0) or 0)
                _asp = int(getattr(e, "bl_aniso_split_n_would_split", 0) or 0)
                lines.append(
                    f'{e.timestamp},"{e.input_file}",{e.tier_used},{e.quality_level},'
                    f"{int(e.success)},{e.elapsed_seconds:.2f},{e.n_cells},"
                    f"{e.max_aspect_ratio or ''},{e.max_skewness or ''},"
                    f'{e.max_non_orthogonality or ""},'
                    f'{_hd if _hd is not None else ""},'
                    f'{_hr if _hr is not None else ""},'
                    f'{_si if _si is not None else ""},'
                    f'{int(_int)},'
                    f'{_bl},{_lcr},{_asp},'
                    f'"{(e.error or "").replace(chr(34), chr(39))}"'
                )
            Path(path).write_text("\n".join(lines) + "\n", encoding="utf-8")
            QMessageBox.information(self, "저장 완료", f"CSV 저장: {path}")
        except Exception as e:
            QMessageBox.warning(self, "저장 실패", str(e))
