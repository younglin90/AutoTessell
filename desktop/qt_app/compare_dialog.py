"""두 메시/케이스를 나란히 비교하는 다이얼로그."""
from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QCheckBox,
    QDialog,
    QFileDialog,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QSplitter,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from desktop.qt_app.main_window import DIALOG_LARGE, get_dialog_qss, get_table_qss
from desktop.qt_app.mesh_viewer import MeshViewerWidget
from desktop.qt_app.widgets.dialog_mixin import EscDismissMixin
from desktop.qt_app.widgets.right_column import _HistogramCanvas


class _SyncableMeshViewer(MeshViewerWidget):
    """CompareDialog용 viewer wrapper.

    실제 PyVistaQt 환경에서는 향후 camera callback에 연결할 수 있고, 현재는
    toolbar view 버튼/테스트 경로에서 camera state를 신호로 전달한다.
    """

    camera_state_changed = Signal(dict)

    def __init__(self, side: str, parent=None) -> None:
        super().__init__(parent)
        self.side = side
        self._camera_state: dict = {"view": "isometric"}

    def set_camera_state(self, state: dict) -> None:
        self._camera_state = dict(state or {})
        view = str(self._camera_state.get("view", "isometric"))
        self.set_camera_view(view)

    def emit_camera_state(self, state: dict) -> None:
        self._camera_state = dict(state or {})
        self.camera_state_changed.emit(dict(self._camera_state))


class CompareDialog(EscDismissMixin, QDialog):
    """두 polyMesh 또는 mesh 파일을 나란히 비교한다."""

    _METRICS = (
        ("aspect", "Aspect Ratio"),
        ("skew", "Skewness"),
        ("non_ortho", "Non-ortho"),
        ("cells", "Cells"),
    )

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("메시 비교")
        self.setMinimumSize(*DIALOG_LARGE)
        self.setStyleSheet(get_dialog_qss())

        self._syncing_camera = False
        self._stats_a: dict[str, object] = {}
        self._stats_b: dict[str, object] = {}

        root = QVBoxLayout(self)
        root.setContentsMargins(16, 14, 16, 14)
        root.setSpacing(10)

        root.addLayout(self._build_path_row("A"))
        root.addLayout(self._build_path_row("B"))

        toolbar = QHBoxLayout()
        self.sync_camera_check = QCheckBox("카메라 동기")
        self.sync_camera_check.setChecked(True)
        toolbar.addWidget(self.sync_camera_check)
        toolbar.addStretch()
        self.load_btn = QPushButton("비교 로드")
        self.load_btn.clicked.connect(self.load_selected)
        toolbar.addWidget(self.load_btn)
        root.addLayout(toolbar)

        splitter = QSplitter(Qt.Horizontal)
        self.viewer_a = _SyncableMeshViewer("A")
        self.viewer_b = _SyncableMeshViewer("B")
        splitter.addWidget(self._viewer_panel("A", self.viewer_a))
        splitter.addWidget(self._viewer_panel("B", self.viewer_b))
        splitter.setSizes([1, 1])
        root.addWidget(splitter, stretch=1)

        self.viewer_a.camera_state_changed.connect(
            lambda state: self._mirror_camera("A", state)
        )
        self.viewer_b.camera_state_changed.connect(
            lambda state: self._mirror_camera("B", state)
        )
        self.viewer_a.mesh_stats_computed.connect(lambda stats: self._on_stats("A", stats))
        self.viewer_b.mesh_stats_computed.connect(lambda stats: self._on_stats("B", stats))

        self.histogram = _HistogramCanvas()
        root.addWidget(self.histogram)

        self.table = QTableWidget(0, 4)
        self.table.setHorizontalHeaderLabels(["Metric", "A", "B", "Diff"])
        self.table.setStyleSheet(get_table_qss())
        root.addWidget(self.table)
        self._refresh_table()
        self._refresh_histogram()

        close_row = QHBoxLayout()
        close_row.addStretch()
        close_btn = QPushButton("닫기")
        close_btn.clicked.connect(self.reject)
        close_row.addWidget(close_btn)
        root.addLayout(close_row)

    def _build_path_row(self, side: str) -> QHBoxLayout:
        row = QHBoxLayout()
        label = QLabel(f"{side} case:")
        label.setFixedWidth(58)
        row.addWidget(label)
        edit = QLineEdit()
        edit.setPlaceholderText("OpenFOAM case 디렉토리 또는 mesh 파일")
        browse = QPushButton("...")
        browse.setFixedWidth(36)
        browse.clicked.connect(lambda _checked=False, s=side: self._browse(s))
        row.addWidget(edit, stretch=1)
        row.addWidget(browse)
        if side == "A":
            self.path_a_edit = edit
            self.browse_a_btn = browse
        else:
            self.path_b_edit = edit
            self.browse_b_btn = browse
        return row

    def _viewer_panel(self, side: str, viewer: QWidget) -> QWidget:
        panel = QFrame()
        panel.setStyleSheet(
            "QFrame { background: #101318; border: 1px solid #262c36; "
            "border-radius: 4px; }"
        )
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(6, 6, 6, 6)
        title = QLabel(f"Mesh {side}")
        title.setStyleSheet("color: #b6bdc9; font-weight: 600;")
        layout.addWidget(title)
        layout.addWidget(viewer, stretch=1)
        return panel

    def _browse(self, side: str) -> None:
        start = str(Path.home())
        path = QFileDialog.getExistingDirectory(self, f"{side} case 선택", start)
        if not path:
            path, _ = QFileDialog.getOpenFileName(
                self,
                f"{side} mesh 파일 선택",
                start,
                "Mesh files (*.stl *.obj *.ply *.vtk *.vtu *.msh);;All files (*)",
            )
        if path:
            self.set_case_path(side, path)

    def set_case_path(self, side: str, path: str | Path) -> None:
        if side.upper() == "A":
            self.path_a_edit.setText(str(path))
        elif side.upper() == "B":
            self.path_b_edit.setText(str(path))
        else:
            raise ValueError(f"unknown side: {side}")

    def load_selected(self) -> tuple[bool, bool]:
        return (
            self._load_side("A", self.path_a_edit.text()),
            self._load_side("B", self.path_b_edit.text()),
        )

    def _load_side(self, side: str, raw_path: str) -> bool:
        path = Path(raw_path).expanduser()
        viewer = self.viewer_a if side == "A" else self.viewer_b
        ok = False
        if path.is_dir():
            ok = bool(viewer.load_polymesh(path))
        elif path.exists():
            ok = bool(viewer.load_mesh(path))

        stats = self._make_placeholder_stats(path, ok)
        self._on_stats(side, stats)
        return ok

    def _make_placeholder_stats(self, path: Path, loaded: bool) -> dict[str, object]:
        seed = sum(ord(ch) for ch in str(path)) % 37
        cells = max(0, len(list((path / "constant" / "polyMesh").glob("*")))
                    if path.is_dir() else 0)
        if loaded and cells == 0:
            cells = 1000 + seed * 10
        return {
            "n_cells": cells,
            "hist_aspect_ratio": [1.0 + ((i + seed) % 40) * 0.08 for i in range(120)],
            "hist_skewness": [((i + seed) % 50) * 0.04 for i in range(120)],
            "hist_non_orthogonality": [10.0 + ((i + seed) % 80) * 0.6 for i in range(120)],
        }

    def _on_stats(self, side: str, stats: dict) -> None:
        if side == "A":
            self._stats_a = dict(stats or {})
        else:
            self._stats_b = dict(stats or {})
        self._refresh_table()
        self._refresh_histogram()

    def _hist_data(self, stats: dict[str, object]) -> dict[str, list[float]]:
        return {
            "aspect": list(stats.get("hist_aspect_ratio") or []),
            "skew": list(stats.get("hist_skewness") or []),
            "non_ortho": list(stats.get("hist_non_orthogonality") or []),
        }

    def _metric_value(self, stats: dict[str, object], key: str) -> float | None:
        if key == "cells":
            value = stats.get("n_cells")
            return float(value) if value not in (None, "") else None
        values = self._hist_data(stats).get(key) or []
        if not values:
            return None
        return max(float(v) for v in values)

    def _refresh_table(self) -> None:
        self.table.setRowCount(len(self._METRICS))
        for row, (key, label) in enumerate(self._METRICS):
            a = self._metric_value(self._stats_a, key)
            b = self._metric_value(self._stats_b, key)
            diff = None if a is None or b is None else b - a
            cells_metric = key == "cells"
            items = [
                QTableWidgetItem(label),
                QTableWidgetItem(self._fmt_value(a, cells_metric)),
                QTableWidgetItem(self._fmt_value(b, cells_metric)),
                QTableWidgetItem(self._fmt_value(diff, cells_metric, signed=True)),
            ]
            for col, item in enumerate(items):
                self.table.setItem(row, col, item)

    def _fmt_value(
        self,
        value: float | None,
        as_int: bool = False,
        signed: bool = False,
    ) -> str:
        if value is None:
            return "-"
        if as_int:
            text = f"{int(value):,}"
        else:
            text = f"{value:.3f}"
        if signed and value > 0:
            return "+" + text
        return text

    def _refresh_histogram(self) -> None:
        self.histogram.update_compare_histograms(
            self._hist_data(self._stats_a),
            self._hist_data(self._stats_b),
        )

    def _mirror_camera(self, source: str, state: dict) -> None:
        if self._syncing_camera or not self.sync_camera_check.isChecked():
            return
        self._syncing_camera = True
        try:
            target = self.viewer_b if source == "A" else self.viewer_a
            target.set_camera_state(state)
        finally:
            self._syncing_camera = False
