"""AutoTessell 메인 윈도우 — PySide6 최소 실행형 GUI."""
from __future__ import annotations

import json
from enum import StrEnum
from pathlib import Path


class QualityLevel(StrEnum):
    DRAFT = "draft"
    STANDARD = "standard"
    FINE = "fine"


class AutoTessellWindow:  # type: ignore[misc]
    """PySide6 QMainWindow 기반 메인 윈도우."""

    SUPPORTED_EXTENSIONS: tuple[str, ...] = (
        ".stl", ".obj", ".ply", ".off", ".3mf",
        ".step", ".stp", ".iges", ".igs", ".brep",
        ".msh", ".vtu", ".vtk",
    )
    TIER_PARAM_SPECS: tuple[tuple[str, str, str, str], ...] = (
        ("core_quality", "Core Quality", "float", "2.0"),
        ("core_max_vertices", "Core Max Vertices", "int", "auto"),
        ("netgen_grading", "Netgen Grading", "float", "0.3"),
        ("netgen_curvaturesafety", "Netgen CurvatureSafety", "float", "2.0"),
        ("netgen_segmentsperedge", "Netgen Segments/Edge", "float", "1.0"),
        ("ng_max_h", "Netgen maxh", "float", "auto"),
        ("ng_min_h", "Netgen minh", "float", "auto"),
        ("meshpy_min_angle", "MeshPy Min Angle", "float", "25.0"),
        ("jigsaw_optm_iter", "Jigsaw Opt Iter", "int", "32"),
        ("snappy_max_local_cells", "Snappy MaxLocalCells", "int", "1000000"),
        ("snappy_max_global_cells", "Snappy MaxGlobalCells", "int", "10000000"),
        ("snappy_min_refinement_cells", "Snappy MinRefCells", "int", "10"),
        ("snappy_n_cells_between_levels", "Snappy CellsBetweenLv", "int", "3"),
        ("snappy_snap_smooth_patch", "Snappy SmoothPatch", "int", "3"),
        ("snappy_snap_relax_iter", "Snappy RelaxIter", "int", "5"),
        ("snappy_feature_snap_iter", "Snappy FeatureSnapIter", "int", "10"),
        ("tetwild_edge_length", "TetWild Edge Length", "float", "auto"),
        ("tw_max_iterations", "TetWild Max Iter", "int", "80"),
        ("mmg_hmin", "MMG hmin", "float", "auto"),
        ("mmg_hmax", "MMG hmax", "float", "auto"),
        ("mmg_hgrad", "MMG hgrad", "float", "1.3"),
        ("mmg_hausd", "MMG hausd", "float", "0.01"),
    )
    PARAM_HELP: dict[str, str] = {
        "tier": "사용할 볼륨 메싱 엔진 계층을 선택합니다. auto/core/netgen/snappy/cfmesh/tetwild.",
        "element_size": "전역 표면 셀 크기 오버라이드입니다. 작을수록 촘촘하고 느립니다.",
        "max_cells": "총 셀 수 상한입니다. 초과 시 base_cell_size를 키워 상한을 맞춥니다.",
        "no_repair": "L1 표면 수리를 건너뜁니다. 입력 표면이 깨끗할 때만 권장.",
        "surface_remesh": "L1 gate 통과 여부와 무관하게 L2 표면 리메쉬를 강제합니다.",
        "allow_ai_fallback": "L3 AI 수리를 허용합니다(환경/모델 준비 필요).",
        "remesh_engine": "L2 리메쉬 엔진 선택입니다. auto/mmg/quadwild.",
        "snappy_snap_tolerance": "snappy snap tolerance. 큰 값은 더 공격적으로 표면에 맞춥니다.",
        "snappy_snap_iterations": "snappy nSolveIter. snap 해 반복 횟수입니다.",
        "snappy_castellated_level": "snappy castellated 레벨(min,max)입니다. 예: 2,3",
        "tetwild_epsilon": "TetWild epsilon. 작을수록 보수적/정밀합니다.",
        "tetwild_stop_energy": "TetWild stop energy. 종료 조건 민감도입니다.",
        "cfmesh_max_cell_size": "cfMesh 최대 셀 크기입니다.",
        "extra_tier_params": "추가 tier_specific_params JSON. 위 UI에 없는 키를 직접 전달합니다.",
    }
    # 파라미터별 적용 엔진 범위 (volume tier)
    _TIER_PARAM_SCOPE: dict[str, set[str]] = {
        "snappy_snap_tolerance": {"snappy"},
        "snappy_snap_iterations": {"snappy"},
        "snappy_castellated_level": {"snappy"},
        "tetwild_epsilon": {"tetwild"},
        "tetwild_stop_energy": {"tetwild"},
        "cfmesh_max_cell_size": {"cfmesh"},
        "core_quality": {"core"},
        "core_max_vertices": {"core"},
        "netgen_grading": {"netgen"},
        "netgen_curvaturesafety": {"netgen"},
        "netgen_segmentsperedge": {"netgen"},
        "ng_max_h": {"netgen"},
        "ng_min_h": {"netgen"},
        "snappy_max_local_cells": {"snappy"},
        "snappy_max_global_cells": {"snappy"},
        "snappy_min_refinement_cells": {"snappy"},
        "snappy_n_cells_between_levels": {"snappy"},
        "snappy_snap_smooth_patch": {"snappy"},
        "snappy_snap_relax_iter": {"snappy"},
        "snappy_feature_snap_iter": {"snappy"},
        "tetwild_edge_length": {"tetwild"},
        "tw_max_iterations": {"tetwild"},
    }
    # 파라미터별 적용 엔진 범위 (surface remesh engine)
    _REMESH_PARAM_SCOPE: dict[str, set[str]] = {
        "mmg_hmin": {"mmg"},
        "mmg_hmax": {"mmg"},
        "mmg_hgrad": {"mmg"},
        "mmg_hausd": {"mmg"},
    }

    def __init__(self) -> None:
        self._input_path: Path | None = None
        self._output_dir: Path | None = None
        self._quality_level: QualityLevel = QualityLevel.DRAFT
        self._worker: object | None = None

        self._mesh_viewer: object | None = None
        self._log_edit: object | None = None
        self._quality_combo: object | None = None
        self._tier_combo: object | None = None
        self._iter_spin: object | None = None
        self._dry_run_check: object | None = None
        self._input_edit: object | None = None
        self._output_edit: object | None = None
        self._status_label: object | None = None
        self._progress_bar: object | None = None
        self._drop_label: object | None = None
        self._run_btn: object | None = None
        self._open_output_btn: object | None = None
        self._element_size_edit: object | None = None
        self._max_cells_edit: object | None = None
        self._snappy_tol_edit: object | None = None
        self._snappy_iters_edit: object | None = None
        self._snappy_level_edit: object | None = None
        self._tetwild_eps_edit: object | None = None
        self._tetwild_energy_edit: object | None = None
        self._cfmesh_max_cell_edit: object | None = None
        self._no_repair_check: object | None = None
        self._surface_remesh_check: object | None = None
        self._allow_ai_fallback_check: object | None = None
        self._remesh_engine_combo: object | None = None
        self._extra_params_edit: object | None = None
        self._tier_param_edits: dict[str, object] = {}
        self._param_widgets: dict[str, list[object]] = {}
        self._help_title_label: object | None = None
        self._help_text_view: object | None = None

    def set_input_path(self, path: str | Path) -> None:
        resolved = Path(path).expanduser().resolve()
        if resolved.suffix.lower() not in self.SUPPORTED_EXTENSIONS:
            raise ValueError(
                f"지원하지 않는 파일 형식: {resolved.suffix!r}. "
                f"지원 형식: {self.SUPPORTED_EXTENSIONS}"
            )
        if not resolved.exists():
            raise ValueError(f"입력 파일이 존재하지 않습니다: {resolved}")
        self._input_path = resolved
        if self._output_dir is None:
            self._output_dir = resolved.parent / f"{resolved.stem}_case"
        if self._input_edit is not None:
            self._input_edit.setText(str(resolved))  # type: ignore[union-attr]
        if self._output_edit is not None and self._output_dir is not None:
            self._output_edit.setText(str(self._output_dir))  # type: ignore[union-attr]
        if self._drop_label is not None:
            self._drop_label.setText(f"입력 파일: {resolved.name}")  # type: ignore[union-attr]

    def get_input_path(self) -> Path | None:
        return self._input_path

    def set_output_dir(self, path: str | Path) -> None:
        resolved = Path(path).expanduser().resolve()
        self._output_dir = resolved
        if self._output_edit is not None:
            self._output_edit.setText(str(resolved))  # type: ignore[union-attr]

    def get_output_dir(self) -> Path | None:
        return self._output_dir

    def set_quality_level(self, level: QualityLevel | str) -> None:
        self._quality_level = QualityLevel(level)
        if self._quality_combo is not None:
            self._quality_combo.setCurrentText(self._quality_level.value)  # type: ignore[union-attr]

    def get_quality_level(self) -> QualityLevel:
        return self._quality_level

    def _build(self) -> None:  # pragma: no cover
        from PySide6.QtCore import Qt
        from PySide6.QtWidgets import (
            QCheckBox,
            QComboBox,
            QFileDialog,
            QFrame,
            QGridLayout,
            QHBoxLayout,
            QLabel,
            QLineEdit,
            QMainWindow,
            QPlainTextEdit,
            QProgressBar,
            QPushButton,
            QSplitter,
            QSpinBox,
            QTabWidget,
            QTextBrowser,
            QToolButton,
            QVBoxLayout,
            QWidget,
        )

        self._qt_file_dialog = QFileDialog
        self._qt_tool_button = QToolButton

        self._qmain = QMainWindow()
        self._qmain.setWindowTitle("AutoTessell Qt")
        self._qmain.resize(1600, 900)

        central = QWidget()
        self._qmain.setCentralWidget(central)
        root_layout = QVBoxLayout(central)

        # 상단 입력 패널
        form = QWidget()
        form_layout = QGridLayout(form)
        root_layout.addWidget(form)

        self._input_edit = QLineEdit()
        self._input_edit.setReadOnly(True)
        input_btn = QPushButton("입력 파일 선택")
        input_btn.clicked.connect(self._on_pick_input)
        form_layout.addWidget(QLabel("Input"), 0, 0)
        form_layout.addWidget(self._input_edit, 0, 1)
        form_layout.addWidget(input_btn, 0, 2)

        self._output_edit = QLineEdit()
        output_btn = QPushButton("출력 폴더 선택")
        output_btn.clicked.connect(self._on_pick_output)
        form_layout.addWidget(QLabel("Output"), 1, 0)
        form_layout.addWidget(self._output_edit, 1, 1)
        form_layout.addWidget(output_btn, 1, 2)

        self._drop_label = QLabel("파일을 여기로 드래그 앤 드롭")
        self._drop_label.setAlignment(Qt.AlignCenter)
        self._drop_label.setAcceptDrops(True)
        self._drop_label.setStyleSheet(
            "border: 2px dashed #666; border-radius: 8px; padding: 10px;"
        )
        self._drop_label.dragEnterEvent = self._on_drag_enter  # type: ignore[assignment]
        self._drop_label.dropEvent = self._on_drop  # type: ignore[assignment]
        root_layout.addWidget(self._drop_label)

        # 옵션/실행 패널
        row = QWidget()
        row_layout = QHBoxLayout(row)
        root_layout.addWidget(row)

        self._quality_combo = QComboBox()
        for lvl in QualityLevel:
            self._quality_combo.addItem(lvl.value)
        row_layout.addWidget(QLabel("Quality"))
        row_layout.addWidget(self._quality_combo)

        self._tier_combo = QComboBox()
        for tier in ("auto", "core", "netgen", "snappy", "cfmesh", "tetwild"):
            self._tier_combo.addItem(tier)
        row_layout.addWidget(QLabel("Tier"))
        row_layout.addWidget(self._tier_combo)
        row_layout.addWidget(self._make_help_button("tier"))

        self._iter_spin = QSpinBox()
        self._iter_spin.setRange(1, 10)
        self._iter_spin.setValue(3)
        row_layout.addWidget(QLabel("Max Iter"))
        row_layout.addWidget(self._iter_spin)

        self._dry_run_check = QCheckBox("Dry-run")
        row_layout.addWidget(self._dry_run_check)

        self._run_btn = QPushButton("파이프라인 실행")
        self._run_btn.clicked.connect(self._on_run_clicked)
        row_layout.addWidget(self._run_btn)

        self._open_output_btn = QPushButton("결과 폴더 열기")
        self._open_output_btn.setEnabled(False)
        self._open_output_btn.clicked.connect(self._on_open_output)
        row_layout.addWidget(self._open_output_btn)
        row_layout.addStretch()

        # 사용자 수동 파라미터 패널
        params = QWidget()
        params_layout = QGridLayout(params)
        root_layout.addWidget(params)

        self._element_size_edit = QLineEdit()
        self._element_size_edit.setPlaceholderText("auto")
        lbl_element_size = QLabel("Element Size")
        params_layout.addWidget(lbl_element_size, 0, 0)
        params_layout.addWidget(self._element_size_edit, 0, 1)
        btn_element_size = self._make_help_button("element_size")
        params_layout.addWidget(btn_element_size, 0, 2)
        self._register_param_widgets("element_size", lbl_element_size, self._element_size_edit, btn_element_size)

        self._max_cells_edit = QLineEdit()
        self._max_cells_edit.setPlaceholderText("none")
        lbl_max_cells = QLabel("Max Cells")
        params_layout.addWidget(lbl_max_cells, 0, 3)
        params_layout.addWidget(self._max_cells_edit, 0, 4)
        btn_max_cells = self._make_help_button("max_cells")
        params_layout.addWidget(btn_max_cells, 0, 5)
        self._register_param_widgets("max_cells", lbl_max_cells, self._max_cells_edit, btn_max_cells)

        self._snappy_tol_edit = QLineEdit()
        self._snappy_tol_edit.setPlaceholderText("auto")
        lbl_snappy_tol = QLabel("Snappy Tol")
        params_layout.addWidget(lbl_snappy_tol, 1, 0)
        params_layout.addWidget(self._snappy_tol_edit, 1, 1)
        btn_snappy_tol = self._make_help_button("snappy_snap_tolerance")
        params_layout.addWidget(btn_snappy_tol, 1, 2)
        self._register_param_widgets("snappy_snap_tolerance", lbl_snappy_tol, self._snappy_tol_edit, btn_snappy_tol)

        self._snappy_iters_edit = QLineEdit()
        self._snappy_iters_edit.setPlaceholderText("auto")
        lbl_snappy_iters = QLabel("Snappy Iter")
        params_layout.addWidget(lbl_snappy_iters, 1, 3)
        params_layout.addWidget(self._snappy_iters_edit, 1, 4)
        btn_snappy_iters = self._make_help_button("snappy_snap_iterations")
        params_layout.addWidget(btn_snappy_iters, 1, 5)
        self._register_param_widgets("snappy_snap_iterations", lbl_snappy_iters, self._snappy_iters_edit, btn_snappy_iters)

        self._snappy_level_edit = QLineEdit()
        self._snappy_level_edit.setPlaceholderText("e.g. 2,3")
        lbl_snappy_level = QLabel("Snappy Level")
        params_layout.addWidget(lbl_snappy_level, 2, 0)
        params_layout.addWidget(self._snappy_level_edit, 2, 1)
        btn_snappy_level = self._make_help_button("snappy_castellated_level")
        params_layout.addWidget(btn_snappy_level, 2, 2)
        self._register_param_widgets("snappy_castellated_level", lbl_snappy_level, self._snappy_level_edit, btn_snappy_level)

        self._tetwild_eps_edit = QLineEdit()
        self._tetwild_eps_edit.setPlaceholderText("auto")
        lbl_tetwild_eps = QLabel("TetWild Eps")
        params_layout.addWidget(lbl_tetwild_eps, 2, 3)
        params_layout.addWidget(self._tetwild_eps_edit, 2, 4)
        btn_tetwild_eps = self._make_help_button("tetwild_epsilon")
        params_layout.addWidget(btn_tetwild_eps, 2, 5)
        self._register_param_widgets("tetwild_epsilon", lbl_tetwild_eps, self._tetwild_eps_edit, btn_tetwild_eps)

        self._tetwild_energy_edit = QLineEdit()
        self._tetwild_energy_edit.setPlaceholderText("auto")
        lbl_tetwild_energy = QLabel("TetWild Energy")
        params_layout.addWidget(lbl_tetwild_energy, 3, 0)
        params_layout.addWidget(self._tetwild_energy_edit, 3, 1)
        btn_tetwild_energy = self._make_help_button("tetwild_stop_energy")
        params_layout.addWidget(btn_tetwild_energy, 3, 2)
        self._register_param_widgets("tetwild_stop_energy", lbl_tetwild_energy, self._tetwild_energy_edit, btn_tetwild_energy)

        self._cfmesh_max_cell_edit = QLineEdit()
        self._cfmesh_max_cell_edit.setPlaceholderText("auto")
        lbl_cfmesh_max = QLabel("cfMesh MaxCell")
        params_layout.addWidget(lbl_cfmesh_max, 3, 3)
        params_layout.addWidget(self._cfmesh_max_cell_edit, 3, 4)
        btn_cfmesh_max = self._make_help_button("cfmesh_max_cell_size")
        params_layout.addWidget(btn_cfmesh_max, 3, 5)
        self._register_param_widgets("cfmesh_max_cell_size", lbl_cfmesh_max, self._cfmesh_max_cell_edit, btn_cfmesh_max)

        self._no_repair_check = QCheckBox("No Repair")
        params_layout.addWidget(self._no_repair_check, 4, 0, 1, 2)
        btn_no_repair = self._make_help_button("no_repair")
        params_layout.addWidget(btn_no_repair, 4, 2)
        self._register_param_widgets("no_repair", self._no_repair_check, btn_no_repair)

        self._surface_remesh_check = QCheckBox("Force Surface Remesh")
        params_layout.addWidget(self._surface_remesh_check, 4, 3, 1, 2)
        btn_surface_remesh = self._make_help_button("surface_remesh")
        params_layout.addWidget(btn_surface_remesh, 4, 5)
        self._register_param_widgets("surface_remesh", self._surface_remesh_check, btn_surface_remesh)

        self._allow_ai_fallback_check = QCheckBox("Allow AI Fallback")
        params_layout.addWidget(self._allow_ai_fallback_check, 5, 0, 1, 2)
        btn_allow_ai = self._make_help_button("allow_ai_fallback")
        params_layout.addWidget(btn_allow_ai, 5, 2)
        self._register_param_widgets("allow_ai_fallback", self._allow_ai_fallback_check, btn_allow_ai)

        self._remesh_engine_combo = QComboBox()
        for engine in ("auto", "mmg", "quadwild"):
            self._remesh_engine_combo.addItem(engine)
        lbl_remesh_engine = QLabel("Remesh Engine")
        params_layout.addWidget(lbl_remesh_engine, 5, 3)
        params_layout.addWidget(self._remesh_engine_combo, 5, 4)
        btn_remesh_engine = self._make_help_button("remesh_engine")
        params_layout.addWidget(btn_remesh_engine, 5, 5)
        self._register_param_widgets("remesh_engine", lbl_remesh_engine, self._remesh_engine_combo, btn_remesh_engine)

        self._extra_params_edit = QLineEdit()
        self._extra_params_edit.setPlaceholderText('{"snappy_snap_iterations": 50}')
        lbl_extra_params = QLabel("Extra Tier Params (JSON)")
        params_layout.addWidget(lbl_extra_params, 6, 0)
        params_layout.addWidget(self._extra_params_edit, 6, 1, 1, 4)
        btn_extra_params = self._make_help_button("extra_tier_params")
        params_layout.addWidget(btn_extra_params, 6, 5)
        self._register_param_widgets("extra_tier_params", lbl_extra_params, self._extra_params_edit, btn_extra_params)

        # 고급 Tier 파라미터 패널 (모든 주요 키 노출)
        adv = QWidget()
        adv_layout = QGridLayout(adv)
        root_layout.addWidget(adv)
        adv_layout.addWidget(QLabel("Advanced Tier Params"), 0, 0, 1, 9)

        self._tier_param_edits = {}
        for i, (key, label, _kind, placeholder) in enumerate(self.TIER_PARAM_SPECS):
            row_i = 1 + (i // 3)
            col_base = (i % 3) * 3
            lbl = QLabel(label)
            edit = QLineEdit()
            edit.setPlaceholderText(placeholder)
            btn = self._make_help_button(key)
            self._tier_param_edits[key] = edit
            adv_layout.addWidget(lbl, row_i, col_base)
            adv_layout.addWidget(edit, row_i, col_base + 1)
            adv_layout.addWidget(btn, row_i, col_base + 2)
            self._register_param_widgets(key, lbl, edit, btn)

        # Help 패널 (팝업 대체)
        help_card = QFrame()
        help_card.setFrameShape(QFrame.StyledPanel)
        help_layout = QVBoxLayout(help_card)
        self._help_title_label = QLabel("Parameter Help")
        self._help_title_label.setStyleSheet("font-weight: 600;")
        self._help_text_view = QTextBrowser()
        self._help_text_view.setOpenExternalLinks(False)
        self._help_text_view.setMinimumHeight(120)
        help_layout.addWidget(self._help_title_label)
        help_layout.addWidget(self._help_text_view)
        root_layout.addWidget(help_card)
        self._set_help_topic("tier")
        if self._tier_combo is not None:
            self._tier_combo.currentTextChanged.connect(lambda _v: self._update_param_visibility())  # type: ignore[union-attr]
        if self._remesh_engine_combo is not None:
            self._remesh_engine_combo.currentTextChanged.connect(lambda _v: self._update_param_visibility())  # type: ignore[union-attr]
        self._update_param_visibility()

        self._status_label = QLabel("Ready")
        self._progress_bar = QProgressBar()
        self._progress_bar.setRange(0, 1)
        self._progress_bar.setValue(0)
        root_layout.addWidget(self._status_label)
        root_layout.addWidget(self._progress_bar)

        # Splitter layout: Log (left) + Mesh Viewer (right) — Fluent GUI style
        splitter = QSplitter(Qt.Horizontal)

        # Left: Log editor
        self._log_edit = QPlainTextEdit()
        self._log_edit.setReadOnly(True)
        splitter.addWidget(self._log_edit)

        # Right: Mesh viewer
        try:
            from desktop.qt_app.mesh_viewer import MeshViewerWidget
            self._mesh_viewer = MeshViewerWidget()
            splitter.addWidget(self._mesh_viewer)
        except ImportError:
            fallback_label = QLabel("[경고] PyVista 또는 메시 뷰어 모듈을 찾을 수 없습니다.")
            fallback_label.setAlignment(Qt.AlignCenter)
            splitter.addWidget(fallback_label)
            self._mesh_viewer = None

        # Set initial splitter sizes: 40% log, 60% viewer
        splitter.setSizes([640, 960])
        splitter.setCollapsible(0, False)
        splitter.setCollapsible(1, False)

        root_layout.addWidget(splitter, stretch=1)

    def show(self) -> None:  # pragma: no cover
        if not hasattr(self, "_qmain"):
            self._build()
        # 일부 WSL/X11 환경에서 초기 창이 오프스크린에 배치되는 현상 방지
        self._qmain.move(80, 80)
        self._qmain.showNormal()
        self._qmain.show()

    def _on_pick_input(self) -> None:  # pragma: no cover
        if not hasattr(self, "_qt_file_dialog"):
            return
        filt = "Mesh/CAD Files (*.stl *.obj *.ply *.off *.3mf *.step *.stp *.iges *.igs *.brep *.msh *.vtu *.vtk)"
        path, _ = self._qt_file_dialog.getOpenFileName(self._qmain, "입력 파일 선택", "", filt)
        if path:
            try:
                self.set_input_path(path)
                self._append_log(f"입력 설정: {path}")
                # 입력 파일 미리보기를 비동기로 로드 (UI 블로킹 방지)
                if self._mesh_viewer is not None:
                    from PySide6.QtCore import QTimer
                    self._append_log("[미리보기] 입력 파일을 3D 뷰어에 로드 중...")
                    QTimer.singleShot(
                        50,
                        lambda: self._load_input_preview()
                    )
            except ValueError as exc:
                self._append_log(f"[오류] {exc}")

    def _load_input_preview(self) -> None:  # pragma: no cover
        """입력 파일 미리보기를 별도 스레드에서 로드 (UI 블로킹 방지)."""
        if self._mesh_viewer is None or self._input_path is None:
            return
        try:
            from desktop.qt_app.mesh_preview_worker import MeshPreviewWorker

            loader = MeshPreviewWorker(self._mesh_viewer, self._input_path)
            loader.finished.connect(  # type: ignore[union-attr]
                lambda success: (
                    self._append_log(f"[미리보기] 입력 파일 로드 성공: {self._input_path.name}")
                    if success
                    else self._append_log("[미리보기] 입력 파일 로드 실패")
                )
            )
            loader.error.connect(  # type: ignore[union-attr]
                lambda msg: self._append_log(f"[미리보기] 오류: {msg}")
            )
            loader.start()  # type: ignore[union-attr]
        except Exception as exc:  # noqa: BLE001
            self._append_log(f"[미리보기] 워커 생성 실패: {exc}")

    def _on_pick_output(self) -> None:  # pragma: no cover
        if not hasattr(self, "_qt_file_dialog"):
            return
        path = self._qt_file_dialog.getExistingDirectory(self._qmain, "출력 폴더 선택")
        if path:
            self.set_output_dir(path)
            self._append_log(f"출력 설정: {path}")

    def _on_drag_enter(self, event: object) -> None:  # pragma: no cover
        mime = event.mimeData()  # type: ignore[attr-defined]
        if mime.hasUrls():
            event.acceptProposedAction()  # type: ignore[attr-defined]

    def _on_drop(self, event: object) -> None:  # pragma: no cover
        mime = event.mimeData()  # type: ignore[attr-defined]
        if not mime.hasUrls():
            return
        path = mime.urls()[0].toLocalFile()
        try:
            self.set_input_path(path)
            self._append_log(f"입력 설정(드롭): {path}")
        except ValueError as exc:
            self._append_log(f"[오류] {exc}")

    def _on_run_clicked(self) -> None:  # pragma: no cover
        from desktop.qt_app.pipeline_worker import PipelineWorker

        if self._input_path is None:
            self._append_log("[오류] 입력 파일을 먼저 선택하세요.")
            return

        if self._quality_combo is not None:
            self._quality_level = QualityLevel(self._quality_combo.currentText())  # type: ignore[union-attr]
        if self._output_edit is not None:
            text = self._output_edit.text().strip()  # type: ignore[union-attr]
            if text:
                self.set_output_dir(text)
        if self._output_dir is None:
            self._output_dir = self._input_path.parent / f"{self._input_path.stem}_case"

        tier = "auto"
        if self._tier_combo is not None:
            tier = self._tier_combo.currentText()  # type: ignore[union-attr]
        max_iterations = 3
        if self._iter_spin is not None:
            max_iterations = int(self._iter_spin.value())  # type: ignore[union-attr]
        dry_run = bool(self._dry_run_check.isChecked()) if self._dry_run_check is not None else False  # type: ignore[union-attr]
        element_size: float | None = None
        max_cells: int | None = None
        tier_params: dict[str, object] = {}
        no_repair = bool(self._no_repair_check.isChecked()) if self._no_repair_check is not None else False  # type: ignore[union-attr]
        surface_remesh = bool(self._surface_remesh_check.isChecked()) if self._surface_remesh_check is not None else False  # type: ignore[union-attr]
        allow_ai_fallback = bool(self._allow_ai_fallback_check.isChecked()) if self._allow_ai_fallback_check is not None else False  # type: ignore[union-attr]
        remesh_engine = (
            self._remesh_engine_combo.currentText() if self._remesh_engine_combo is not None else "auto"  # type: ignore[union-attr]
        )

        if self._element_size_edit is not None:
            raw = self._element_size_edit.text().strip()  # type: ignore[union-attr]
            if raw:
                try:
                    element_size = float(raw)
                    if element_size <= 0:
                        raise ValueError("element_size must be > 0")
                except Exception as exc:
                    self._append_log(f"[오류] Element Size 파싱 실패: {exc}")
                    return

        if self._max_cells_edit is not None:
            raw = self._max_cells_edit.text().strip()  # type: ignore[union-attr]
            if raw:
                try:
                    max_cells = int(raw)
                    if max_cells <= 0:
                        raise ValueError("max_cells must be > 0")
                except Exception as exc:
                    self._append_log(f"[오류] Max Cells 파싱 실패: {exc}")
                    return

        if self._snappy_tol_edit is not None:
            raw = self._snappy_tol_edit.text().strip()  # type: ignore[union-attr]
            if raw and self._is_param_active("snappy_snap_tolerance"):
                try:
                    tier_params["snappy_snap_tolerance"] = float(raw)
                except Exception as exc:
                    self._append_log(f"[오류] Snappy Tol 파싱 실패: {exc}")
                    return

        if self._snappy_iters_edit is not None:
            raw = self._snappy_iters_edit.text().strip()  # type: ignore[union-attr]
            if raw and self._is_param_active("snappy_snap_iterations"):
                try:
                    tier_params["snappy_snap_iterations"] = int(raw)
                except Exception as exc:
                    self._append_log(f"[오류] Snappy Iter 파싱 실패: {exc}")
                    return

        if self._snappy_level_edit is not None:
            raw = self._snappy_level_edit.text().strip()  # type: ignore[union-attr]
            if raw and self._is_param_active("snappy_castellated_level"):
                try:
                    parts = [int(x.strip()) for x in raw.split(",")]
                    if len(parts) != 2:
                        raise ValueError("need two ints: min,max")
                    tier_params["snappy_castellated_level"] = parts
                except Exception as exc:
                    self._append_log(f"[오류] Snappy Level 파싱 실패: {exc}")
                    return

        if self._tetwild_eps_edit is not None:
            raw = self._tetwild_eps_edit.text().strip()  # type: ignore[union-attr]
            if raw and self._is_param_active("tetwild_epsilon"):
                try:
                    val = float(raw)
                    if val <= 0:
                        raise ValueError("tetwild_epsilon must be > 0")
                    tier_params["tetwild_epsilon"] = val
                    tier_params["tw_epsilon"] = val
                except Exception as exc:
                    self._append_log(f"[오류] TetWild Eps 파싱 실패: {exc}")
                    return

        if self._tetwild_energy_edit is not None:
            raw = self._tetwild_energy_edit.text().strip()  # type: ignore[union-attr]
            if raw and self._is_param_active("tetwild_stop_energy"):
                try:
                    val = float(raw)
                    if val <= 0:
                        raise ValueError("tetwild_stop_energy must be > 0")
                    tier_params["tetwild_stop_energy"] = val
                    tier_params["tw_stop_energy"] = val
                except Exception as exc:
                    self._append_log(f"[오류] TetWild Energy 파싱 실패: {exc}")
                    return

        if self._cfmesh_max_cell_edit is not None:
            raw = self._cfmesh_max_cell_edit.text().strip()  # type: ignore[union-attr]
            if raw and self._is_param_active("cfmesh_max_cell_size"):
                try:
                    val = float(raw)
                    if val <= 0:
                        raise ValueError("cfmesh_max_cell_size must be > 0")
                    tier_params["cfmesh_max_cell_size"] = val
                    tier_params["cf_max_cell_size"] = val
                except Exception as exc:
                    self._append_log(f"[오류] cfMesh MaxCell 파싱 실패: {exc}")
                    return

        for key, _label, kind, _placeholder in self.TIER_PARAM_SPECS:
            edit = self._tier_param_edits.get(key)
            if edit is None:
                continue
            raw = edit.text().strip()  # type: ignore[union-attr]
            if not raw or not self._is_param_active(key):
                continue
            try:
                if kind == "int":
                    tier_params[key] = int(raw)
                elif kind == "float":
                    tier_params[key] = float(raw)
                else:
                    tier_params[key] = raw
            except Exception as exc:
                self._append_log(f"[오류] {key} 파싱 실패: {exc}")
                return

        if self._extra_params_edit is not None:
            raw = self._extra_params_edit.text().strip()  # type: ignore[union-attr]
            if raw:
                try:
                    data = json.loads(raw)
                    if not isinstance(data, dict):
                        raise ValueError("JSON object(dict)만 허용됩니다")
                    tier_params.update(data)
                except Exception as exc:
                    self._append_log(f"[오류] Extra Tier Params(JSON) 파싱 실패: {exc}")
                    return

        if self._run_btn is not None:
            self._run_btn.setEnabled(False)  # type: ignore[union-attr]
        if self._open_output_btn is not None:
            self._open_output_btn.setEnabled(False)  # type: ignore[union-attr]
        if self._status_label is not None:
            self._status_label.setText("Running...")  # type: ignore[union-attr]
        if self._progress_bar is not None:
            self._progress_bar.setRange(0, 100)  # type: ignore[union-attr]
            self._progress_bar.setValue(0)  # type: ignore[union-attr]

        self._append_log(
            f"실행: quality={self._quality_level.value} tier={tier} "
            f"max_iter={max_iterations} dry_run={dry_run} "
            f"element_size={element_size} max_cells={max_cells} "
            f"no_repair={no_repair} surface_remesh={surface_remesh} "
            f"remesh_engine={remesh_engine} allow_ai_fallback={allow_ai_fallback} "
            f"tier_params={tier_params}"
        )

        self._worker = PipelineWorker(
            self._input_path,
            self._quality_level,
            self._output_dir,
            tier_hint=tier,
            max_iterations=max_iterations,
            dry_run=dry_run,
            element_size=element_size,
            max_cells=max_cells,
            tier_specific_params=tier_params,
            no_repair=no_repair,
            surface_remesh=surface_remesh,
            remesh_engine=remesh_engine,
            allow_ai_fallback=allow_ai_fallback,
        )
        try:
            self._worker.progress.connect(self._append_log)  # type: ignore[union-attr]
            if hasattr(self._worker, "progress_percent"):
                self._worker.progress_percent.connect(self._on_progress_percent)  # type: ignore[union-attr]
            self._worker.finished.connect(self._on_pipeline_finished)  # type: ignore[union-attr]
            self._worker.start()  # type: ignore[union-attr]
        except Exception as exc:
            if self._run_btn is not None:
                self._run_btn.setEnabled(True)  # type: ignore[union-attr]
            if self._status_label is not None:
                self._status_label.setText("FAIL")  # type: ignore[union-attr]
            self._append_log(f"[오류] Worker 시작 실패: {exc.__class__.__name__}: {exc}")

    def _on_progress_percent(self, percent: int, message: str) -> None:  # pragma: no cover
        if self._progress_bar is not None:
            self._progress_bar.setRange(0, 100)  # type: ignore[union-attr]
            self._progress_bar.setValue(max(0, min(100, int(percent))))  # type: ignore[union-attr]
        if self._status_label is not None:
            self._status_label.setText(f"Running... {int(percent)}%")  # type: ignore[union-attr]

    def _on_pipeline_finished(self, result: object) -> None:  # pragma: no cover
        if self._run_btn is not None:
            self._run_btn.setEnabled(True)  # type: ignore[union-attr]
        if self._progress_bar is not None:
            self._progress_bar.setRange(0, 100)  # type: ignore[union-attr]
            self._progress_bar.setValue(100)  # type: ignore[union-attr]

        success = bool(getattr(result, "success", False))
        elapsed = float(getattr(result, "total_time_seconds", 0.0))
        err = getattr(result, "error", None)
        if result is None:
            success = False
            err = "Worker 내부 예외로 결과 객체를 만들지 못했습니다."

        if self._status_label is not None:
            self._status_label.setText("PASS" if success else "FAIL")  # type: ignore[union-attr]
        if self._open_output_btn is not None and self._output_dir is not None:
            self._open_output_btn.setEnabled(self._output_dir.exists())  # type: ignore[union-attr]

        self._append_log(f"[완료] {'성공' if success else '실패'} ({elapsed:.1f}s)")

        # 메시 뷰어에 메시 로드
        if success and self._output_dir is not None:
            self._load_mesh_to_viewer()

        if err:
            self._append_log(f"[오류] {err}")

    def _load_mesh_to_viewer(self) -> None:  # pragma: no cover
        """메시 파일을 뷰어에 로드."""
        if self._mesh_viewer is None or self._output_dir is None:
            return

        try:
            # polyMesh 또는 STL 파일 찾기
            constant_dir = self._output_dir / "constant" / "polyMesh"

            # 먼저 STL 파일 시도
            stl_files = list(self._output_dir.glob("**/*.stl"))
            if stl_files:
                mesh_file = stl_files[0]
                if self._mesh_viewer.load_mesh(str(mesh_file)):  # type: ignore[union-attr]
                    self._append_log(f"[메시 뷰어] 메시 로드 성공: {mesh_file.name}")
                    return

            # polyMesh 로드 시도
            if constant_dir.exists():
                if self._mesh_viewer.load_polymesh(str(self._output_dir)):  # type: ignore[union-attr]
                    self._append_log("[메시 뷰어] polyMesh 로드 성공")
                    return

            self._append_log("[경고] 로드할 메시 파일을 찾을 수 없습니다.")

        except Exception as exc:  # noqa: BLE001
            self._append_log(f"[경고] 메시 뷰어 로드 실패: {exc}")

    def _on_open_output(self) -> None:  # pragma: no cover
        if self._output_dir is None:
            self._append_log("[오류] 출력 폴더가 설정되지 않았습니다.")
            return
        if not self._output_dir.exists():
            self._append_log(f"[오류] 출력 폴더가 존재하지 않습니다: {self._output_dir}")
            return
        try:
            from PySide6.QtCore import QUrl
            from PySide6.QtGui import QDesktopServices

            QDesktopServices.openUrl(QUrl.fromLocalFile(str(self._output_dir)))
        except Exception as exc:  # noqa: BLE001
            self._append_log(f"[오류] 결과 폴더 열기 실패: {exc}")

    def _append_log(self, message: str) -> None:  # pragma: no cover
        if self._log_edit is not None:
            self._log_edit.appendPlainText(str(message))  # type: ignore[union-attr]

    def _make_help_button(self, key: str) -> object:  # pragma: no cover
        btn = self._qt_tool_button()
        btn.setText("i")
        btn.setFixedWidth(22)
        btn.setToolTip("설명 보기")
        btn.clicked.connect(lambda: self._set_help_topic(key))
        return btn

    def _set_help_topic(self, key: str) -> None:  # pragma: no cover
        text = self.PARAM_HELP.get(key)
        if text is None:
            meta = [x for x in self.TIER_PARAM_SPECS if x[0] == key]
            if meta:
                _key, label, kind, placeholder = meta[0]
                text = (
                    f"{label}\n"
                    f"- key: {key}\n"
                    f"- type: {kind}\n"
                    f"- default/placeholder: {placeholder}\n"
                    "- 이 값은 tier_specific_params로 전략에 직접 반영됩니다."
                )
                title = label
            else:
                text = f"{key}\n상세 설명이 아직 등록되지 않았습니다."
                title = key
        else:
            title = key

        if self._help_title_label is not None:
            self._help_title_label.setText(f"Parameter Help: {title}")  # type: ignore[union-attr]
        if self._help_text_view is not None:
            self._help_text_view.setPlainText(text)  # type: ignore[union-attr]

    def _register_param_widgets(self, key: str, *widgets: object) -> None:
        self._param_widgets.setdefault(key, []).extend(widgets)

    def _is_param_active(self, key: str) -> bool:
        widgets = self._param_widgets.get(key, [])
        if not widgets:
            return True
        for widget in widgets:
            if hasattr(widget, "isVisible") and widget.isVisible():  # type: ignore[union-attr]
                return True
        return False

    def _update_param_visibility(self) -> None:  # pragma: no cover
        tier = self._tier_combo.currentText() if self._tier_combo is not None else "auto"  # type: ignore[union-attr]
        remesh = self._remesh_engine_combo.currentText() if self._remesh_engine_combo is not None else "auto"  # type: ignore[union-attr]
        for key, widgets in self._param_widgets.items():
            visible = self._param_is_applicable(key, tier, remesh)
            for widget in widgets:
                if hasattr(widget, "setVisible"):
                    widget.setVisible(visible)  # type: ignore[union-attr]

    def _param_is_applicable(self, key: str, tier: str, remesh_engine: str) -> bool:
        # 항상 표시
        if key in {
            "element_size",
            "max_cells",
            "no_repair",
            "surface_remesh",
            "allow_ai_fallback",
            "remesh_engine",
            "extra_tier_params",
        }:
            return True

        tier_scope = self._TIER_PARAM_SCOPE.get(key)
        if tier_scope is not None:
            return tier == "auto" or tier in tier_scope

        remesh_scope = self._REMESH_PARAM_SCOPE.get(key)
        if remesh_scope is not None:
            return remesh_engine == "auto" or remesh_engine in remesh_scope

        return True
