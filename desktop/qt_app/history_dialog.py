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


class HistoryDialog(QDialog):
    """실행 이력 조회 + 필터."""

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("실행 이력")
        # 표준 LARGE 다이얼로그 크기
        self.setMinimumSize(960, 640)
        self.setStyleSheet(
            "QDialog { background: #0f1318; color: #e8ecf2; }"
            "QLabel { color: #b6bdc9; background: transparent; }"
            "QLineEdit, QComboBox { background: #161a20; color: #e8ecf2; "
            "border: 1px solid #323a46; border-radius: 4px; padding: 5px 8px; }"
            "QPushButton { background: #21262d; color: #e8ecf2; "
            "border: 1px solid #30363d; border-radius: 4px; "
            "padding: 6px 12px; }"
            "QPushButton:hover { background: #2d333b; border-color: #4ea3ff; }"
        )

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
        self.table = QTableWidget(0, 8)
        self.table.setHorizontalHeaderLabels([
            "시각", "입력", "Tier", "품질", "결과",
            "시간(s)", "셀수", "Non-ortho",
        ])
        self.table.setStyleSheet(
            "QTableWidget { background: #0f1318; color: #e8ecf2; "
            "gridline-color: #262c36; border: 1px solid #262c36; }"
            "QHeaderView::section { background: #161a20; color: #b6bdc9; "
            "border: none; border-right: 1px solid #262c36; "
            "border-bottom: 1px solid #262c36; padding: 6px 8px; }"
            "QTableWidget::item { padding: 4px 6px; }"
            "QTableWidget::item:selected { background: #1c2129; color: #e8ecf2; }"
        )
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
            lines = [
                "timestamp,input_file,tier,quality,success,"
                "elapsed_seconds,n_cells,max_aspect_ratio,"
                "max_skewness,max_non_orthogonality,error"
            ]
            for e in filtered:
                lines.append(
                    f'{e.timestamp},"{e.input_file}",{e.tier_used},{e.quality_level},'
                    f"{int(e.success)},{e.elapsed_seconds:.2f},{e.n_cells},"
                    f"{e.max_aspect_ratio or ''},{e.max_skewness or ''},"
                    f'{e.max_non_orthogonality or ""},"{(e.error or "").replace(chr(34), chr(39))}"'
                )
            Path(path).write_text("\n".join(lines) + "\n", encoding="utf-8")
            QMessageBox.information(self, "저장 완료", f"CSV 저장: {path}")
        except Exception as e:
            QMessageBox.warning(self, "저장 실패", str(e))
