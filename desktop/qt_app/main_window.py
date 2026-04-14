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
        # ── Core (geogram) ──────────────────────────────────────────
        ("core_quality", "Core Quality", "float", "2.0"),
        ("core_max_vertices", "Core Max Vertices", "int", "auto"),
        # ── Netgen ──────────────────────────────────────────────────
        ("netgen_grading", "Netgen Grading", "float", "0.3"),
        ("netgen_curvaturesafety", "Netgen CurvatureSafety", "float", "2.0"),
        ("netgen_segmentsperedge", "Netgen Segments/Edge", "float", "1.0"),
        ("netgen_closeedgefac", "Netgen CloseEdgeFac", "float", "2.0"),
        ("ng_max_h", "Netgen maxh", "float", "auto"),
        ("ng_min_h", "Netgen minh", "float", "auto"),
        # ── MeshPy (TetGen) ─────────────────────────────────────────
        ("meshpy_min_angle", "MeshPy Min Angle", "float", "25.0"),
        ("meshpy_max_volume", "MeshPy MaxVolume", "float", "auto"),
        ("meshpy_max_area_2d", "MeshPy MaxArea2D", "float", "auto"),
        # ── JIGSAW ──────────────────────────────────────────────────
        ("jigsaw_hmax", "JIGSAW hmax", "float", "auto"),
        ("jigsaw_hmin", "JIGSAW hmin", "float", "auto"),
        ("jigsaw_optm_iter", "JIGSAW Opt Iter", "int", "32"),
        # ── SnappyHexMesh ───────────────────────────────────────────
        ("snappy_max_local_cells", "Snappy MaxLocalCells", "int", "1000000"),
        ("snappy_max_global_cells", "Snappy MaxGlobalCells", "int", "10000000"),
        ("snappy_min_refinement_cells", "Snappy MinRefCells", "int", "10"),
        ("snappy_n_cells_between_levels", "Snappy CellsBetweenLv", "int", "3"),
        ("snappy_snap_smooth_patch", "Snappy SmoothPatch", "int", "3"),
        ("snappy_snap_relax_iter", "Snappy RelaxIter", "int", "5"),
        ("snappy_feature_snap_iter", "Snappy FeatureSnapIter", "int", "10"),
        # ── TetWild ─────────────────────────────────────────────────
        ("tetwild_edge_length", "TetWild Edge Length", "float", "auto"),
        ("tw_max_iterations", "TetWild Max Iter", "int", "80"),
        # ── MMG ─────────────────────────────────────────────────────
        ("mmg_hmin", "MMG hmin", "float", "auto"),
        ("mmg_hmax", "MMG hmax", "float", "auto"),
        ("mmg_hgrad", "MMG hgrad", "float", "1.3"),
        ("mmg_hausd", "MMG hausd", "float", "0.01"),
        # ── Polyhedral ──────────────────────────────────────────────
        ("feature_angle", "Polyhedral FeatureAngle", "float", "5.0"),
        ("concave_multi_cells", "Polyhedral ConcaveCells", "bool", "true"),
    )
    PARAM_HELP: dict[str, str] = {
        "tier": (
            "사용할 볼륨 메싱 엔진을 선택합니다.\n"
            "auto: 형상에 따라 자동 선택\n"
            "core: geogram CDT (빠름)\n"
            "netgen: Netgen/ngsolve (고품질 tet)\n"
            "snappy: snappyHexMesh (hex dominant)\n"
            "cfmesh: cfMesh (hex dominant)\n"
            "tetwild: TetWild (강건한 tet)\n"
            "jigsaw: JIGSAW (복잡 형상)\n"
            "mmg: MMG3D (fine quality)\n"
            "polyhedral: OpenFOAM polyDualMesh"
        ),
        "element_size": "전역 표면 셀 크기 오버라이드입니다. 작을수록 촘촘하고 느립니다.",
        "max_cells": "총 셀 수 상한입니다. 초과 시 base_cell_size를 키워 상한을 맞춥니다.",
        "no_repair": "L1 표면 수리를 건너뜁니다. 입력 표면이 깨끗할 때만 권장.",
        "surface_remesh": "L1 gate 통과 여부와 무관하게 L2 표면 리메쉬를 강제합니다.",
        "allow_ai_fallback": (
            "L3 AI 표면 수리를 허용합니다 (볼륨 메쉬 생성과 무관).\n"
            "L1(pymeshfix)/L2(pyACVD) 수리 후에도 표면이 닫히지 않을 때,\n"
            "MeshAnything(GPU 딥러닝)으로 표면을 재생성합니다.\n"
            "GPU(CUDA)와 모델 파일이 없으면 자동으로 건너뜁니다."
        ),
        "remesh_engine": "L2 리메쉬 엔진 선택입니다. auto/mmg/quadwild.",
        # Netgen
        "netgen_grading": "인접 요소 크기 비율. 작을수록 급격한 크기 변화 허용 (0.1~1.0).",
        "netgen_curvaturesafety": "곡률 기반 메싱 강도. 클수록 곡선부를 세밀하게 (1.0~5.0).",
        "netgen_segmentsperedge": "엣지당 분할 수. 클수록 엣지가 촘촘 (0.3~3.0).",
        "netgen_closeedgefac": (
            "근접 엣지 처리 인자. 0으로 설정 시 근접 엣지 검출 비활성화 — "
            "'too many attempts' 에러 발생 시 0으로 설정하세요."
        ),
        "ng_max_h": "Netgen 최대 요소 크기 (maxh). 비워두면 element_size 사용.",
        "ng_min_h": "Netgen 최소 요소 크기 (minh). 비워두면 자동 결정.",
        # MeshPy
        "meshpy_min_angle": "MeshPy(TetGen) 최소 다면체 각도. 클수록 품질 우수 (10~35도).",
        "meshpy_max_volume": "MeshPy 최대 사면체 부피. 작을수록 촘촘. 비워두면 element_size³/6.",
        "meshpy_max_area_2d": "MeshPy 2D 최대 삼각형 면적. 비워두면 element_size²/2.",
        # JIGSAW
        "jigsaw_hmax": "JIGSAW 최대 요소 크기. 비워두면 element_size 사용.",
        "jigsaw_hmin": "JIGSAW 최소 요소 크기. 비워두면 min_cell_size 사용.",
        "jigsaw_optm_iter": "JIGSAW 최적화 반복 횟수. 클수록 품질 우수, 느림 (기본 32).",
        # Snappy
        "snappy_snap_tolerance": "snappy snap tolerance. 큰 값은 더 공격적으로 표면에 맞춥니다.",
        "snappy_snap_iterations": "snappy nSolveIter. snap 해 반복 횟수입니다.",
        "snappy_castellated_level": "snappy castellated 레벨(min,max)입니다. 예: 2,3",
        # TetWild
        "tetwild_epsilon": "TetWild epsilon. 작을수록 보수적/정밀합니다.",
        "tetwild_stop_energy": "TetWild stop energy. 종료 조건 민감도입니다.",
        # cfMesh
        "cfmesh_max_cell_size": "cfMesh 최대 셀 크기입니다.",
        "cfmesh_surface_refinement": "cfMesh 표면 정제 구역 (JSON). 예: {\"patch\": 2}",
        "cfmesh_local_refinement": "cfMesh 국소 정제 구역 (JSON). 예: {\"box\": [0,0,0,1,1,1]}",
        # Polyhedral
        "feature_angle": "Polyhedral 특징선 보존 각도(도). 이 각도 미만의 엣지는 피처로 보존.",
        "concave_multi_cells": "Polyhedral 오목 경계 셀 분할 여부. true/false.",
        # 기타
        "extra_tier_params": "추가 tier_specific_params JSON. 위 UI에 없는 키를 직접 전달합니다.",
    }
    # 파라미터별 적용 엔진 범위 (volume tier)
    _TIER_PARAM_SCOPE: dict[str, set[str]] = {
        # Snappy
        "snappy_snap_tolerance": {"snappy"},
        "snappy_snap_iterations": {"snappy"},
        "snappy_castellated_level": {"snappy"},
        "snappy_max_local_cells": {"snappy"},
        "snappy_max_global_cells": {"snappy"},
        "snappy_min_refinement_cells": {"snappy"},
        "snappy_n_cells_between_levels": {"snappy"},
        "snappy_snap_smooth_patch": {"snappy"},
        "snappy_snap_relax_iter": {"snappy"},
        "snappy_feature_snap_iter": {"snappy"},
        # TetWild
        "tetwild_epsilon": {"tetwild"},
        "tetwild_stop_energy": {"tetwild"},
        "tetwild_edge_length": {"tetwild"},
        "tw_max_iterations": {"tetwild"},
        # cfMesh
        "cfmesh_max_cell_size": {"cfmesh"},
        "cfmesh_surface_refinement": {"cfmesh"},
        "cfmesh_local_refinement": {"cfmesh"},
        # Core
        "core_quality": {"core"},
        "core_max_vertices": {"core"},
        # Netgen
        "netgen_grading": {"netgen"},
        "netgen_curvaturesafety": {"netgen"},
        "netgen_segmentsperedge": {"netgen"},
        "netgen_closeedgefac": {"netgen"},
        "ng_max_h": {"netgen"},
        "ng_min_h": {"netgen"},
        # MeshPy
        "meshpy_min_angle": {"core", "jigsaw"},
        "meshpy_max_volume": {"core", "jigsaw"},
        "meshpy_max_area_2d": {"core", "jigsaw"},
        # JIGSAW
        "jigsaw_hmax": {"jigsaw"},
        "jigsaw_hmin": {"jigsaw"},
        "jigsaw_optm_iter": {"jigsaw"},
        # Polyhedral
        "feature_angle": {"polyhedral"},
        "concave_multi_cells": {"polyhedral"},
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
        self._preview_loader: object | None = None

        self._mesh_viewer: object | None = None
        self._log_edit: object | None = None
        self._quality_combo: object | None = None
        self._quality_seg_btns: dict[str, object] = {}  # 세그먼트 버튼 (DRAFT/STANDARD/FINE)
        self._tier_combo: object | None = None      # container widget (legacy compat)
        self._engine_combo: object | None = None    # inner QComboBox (engine list)
        self._mesh_type_group: object | None = None # QButtonGroup (radio buttons)
        self._mesh_type_cards: dict[str, object] = {}  # 카드형 메시 타입 선택 위젯
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
        self._cfmesh_surface_ref_edit: object | None = None
        self._cfmesh_local_ref_edit: object | None = None
        self._no_repair_check: object | None = None
        self._surface_remesh_check: object | None = None
        self._allow_ai_fallback_check: object | None = None
        self._remesh_engine_combo: object | None = None
        self._extra_params_edit: object | None = None
        self._tier_param_edits: dict[str, object] = {}
        self._param_widgets: dict[str, list[object]] = {}
        self._help_title_label: object | None = None
        self._help_text_view: object | None = None
        # 파이프라인 스텝 인디케이터
        self._pipeline_step_labels: list[object] = []
        # KPI 스코어카드
        self._kpi_labels: dict[str, object] = {}
        # 신규 UI 컴포넌트
        self._active_tier_label: object | None = None
        self._mesh_stats_overlay: object | None = None
        self._report_widget: object | None = None
        self._status_progress: object | None = None
        self._status_stage_labels: list[object] = []
        # Report 탭 내부 레이블 참조
        self._report_placeholder: object | None = None
        self._report_content: object | None = None
        self._main_tab_widget: object | None = None
        # Advanced 접이식 컨텐츠 위젯
        self._adv_content: object | None = None
        self._adv_toggle_btn: object | None = None

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
            size_kb = resolved.stat().st_size // 1024
            self._drop_label.setText(  # type: ignore[union-attr]
                f"{resolved.name}\n{size_kb} KB"
            )

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
        self._refresh_quality_seg_btns()

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
            QScrollArea,
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
        self._qmain.setWindowTitle("AutoTessell")
        self._qmain.resize(1400, 900)

        DARK_STYLE = """
QMainWindow, QWidget {
    background-color: #131313;
    color: #e5e2e1;
    font-family: 'JetBrains Mono', 'Consolas', monospace;
    font-size: 11px;
}
QComboBox {
    background: #201f1f; border: 1px solid #3f4852;
    border-radius: 4px; padding: 4px 8px; color: #e5e2e1;
}
QComboBox::drop-down { border: none; }
QComboBox QAbstractItemView { background: #1c1b1b; selection-background-color: #00629d; }
QLineEdit {
    background: #201f1f; border: 1px solid #3f4852;
    border-radius: 4px; padding: 4px 8px; color: #e5e2e1;
}
QPushButton {
    background: #201f1f; border: 1px solid #3f4852;
    border-radius: 4px; padding: 4px 10px; color: #e5e2e1;
}
QPushButton:hover { background: #2a2a2a; border-color: #98cbff; }
QPushButton:pressed { background: #00629d; }
QLabel { color: #e5e2e1; }
QScrollBar:vertical { background: #1c1b1b; width: 6px; }
QScrollBar::handle:vertical { background: #3f4852; border-radius: 3px; }
QScrollBar:horizontal { background: #1c1b1b; height: 6px; }
QScrollBar::handle:horizontal { background: #3f4852; border-radius: 3px; }
QPlainTextEdit, QTextBrowser {
    background: #0d0d16; border: none; color: #bec7d4;
    font-family: 'JetBrains Mono', monospace; font-size: 10px;
}
QSpinBox { background: #201f1f; border: 1px solid #3f4852; border-radius: 4px; padding: 3px; color: #e5e2e1; }
QCheckBox { color: #bec7d4; spacing: 6px; }
QCheckBox::indicator { width: 14px; height: 14px; border: 1px solid #3f4852; border-radius: 2px; background: #201f1f; }
QCheckBox::indicator:checked { background: #00629d; border-color: #98cbff; }
QProgressBar { background: #1c1b1b; border: none; border-radius: 2px; height: 6px; }
QProgressBar::chunk { background: #98cbff; border-radius: 2px; }
QTabWidget::pane { border: none; border-top: 1px solid #3f4852; }
QTabBar::tab { background: #1c1b1b; color: #bec7d4; padding: 6px 16px; border: none; border-bottom: 2px solid transparent; }
QTabBar::tab:selected { color: #98cbff; border-bottom: 2px solid #98cbff; background: #131313; }
QTabBar::tab:hover { color: #e5e2e1; background: #201f1f; }
QScrollArea { border: none; }
"""
        self._qmain.setStyleSheet(DARK_STYLE)

        central = QWidget()
        self._qmain.setCentralWidget(central)

        # ── 최상위 레이아웃: 수직 (메인 영역 + 하단 상태바) ──────────
        root_vbox = QVBoxLayout(central)
        root_vbox.setContentsMargins(0, 0, 0, 0)
        root_vbox.setSpacing(0)

        # 메인 영역: 수평 (사이드바 + 콘텐츠)
        main_hbox = QHBoxLayout()
        main_hbox.setContentsMargins(0, 0, 0, 0)
        main_hbox.setSpacing(0)
        root_vbox.addLayout(main_hbox, stretch=1)

        # ════════════════════════════════════════════════════════════════
        # [1] 사이드바 (300px 고정)
        # ════════════════════════════════════════════════════════════════
        sidebar_scroll = QScrollArea()
        sidebar_scroll.setFixedWidth(300)
        sidebar_scroll.setWidgetResizable(True)
        sidebar_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        sidebar_scroll.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        sidebar_scroll.setStyleSheet("QScrollArea { background: #1c1b1b; border: none; border-right: 1px solid #3f4852; }")

        sidebar_inner = QWidget()
        sidebar_inner.setStyleSheet("background: #1c1b1b;")
        sidebar_layout = QVBoxLayout(sidebar_inner)
        sidebar_layout.setContentsMargins(12, 12, 12, 12)
        sidebar_layout.setSpacing(12)
        sidebar_scroll.setWidget(sidebar_inner)

        main_hbox.addWidget(sidebar_scroll)

        # ── [A] 로고 영역 (48px) ─────────────────────────────────────
        logo_frame = QFrame()
        logo_frame.setFixedHeight(48)
        logo_frame.setStyleSheet(
            "QFrame { background: #1c1b1b; border: none; border-bottom: 1px solid #2a2a2a; }"
        )
        logo_layout = QHBoxLayout(logo_frame)
        logo_layout.setContentsMargins(0, 0, 0, 0)
        logo_layout.setSpacing(8)

        icon_badge = QLabel("⬡")
        icon_badge.setFixedSize(32, 32)
        icon_badge.setAlignment(Qt.AlignCenter)
        icon_badge.setStyleSheet(
            "background: #0078d4; border-radius: 8px; color: #ffffff; "
            "font-size: 16px; font-weight: bold;"
        )
        logo_text = QLabel("AutoTessell")
        logo_text.setStyleSheet(
            "color: #e5e2e1; font-size: 14px; font-weight: bold; background: transparent;"
        )
        logo_layout.addWidget(icon_badge)
        logo_layout.addWidget(logo_text)
        logo_layout.addStretch()

        sidebar_layout.addWidget(logo_frame)

        # ── [B] 드롭존 (100px) ───────────────────────────────────────
        from desktop.qt_app.drop_zone import DropZone
        drop_zone = DropZone()
        drop_zone.setFixedHeight(100)
        self._drop_label = drop_zone
        drop_zone.file_dropped.connect(self._on_file_dropped)
        drop_zone.mousePressEvent = lambda _e: self._on_pick_input()  # type: ignore[method-assign]
        sidebar_layout.addWidget(drop_zone)

        # hidden input/output edits for API compatibility
        self._input_edit = QLineEdit()
        self._input_edit.setVisible(False)
        self._output_edit = QLineEdit()
        self._output_edit.setVisible(False)
        sidebar_layout.addWidget(self._input_edit)
        sidebar_layout.addWidget(self._output_edit)

        # ── [C] Mesh Engine 드롭다운 ─────────────────────────────────
        engine_section_lbl = QLabel("Mesh Engine")
        engine_section_lbl.setStyleSheet(
            "color: #bec7d4; font-size: 9px; letter-spacing: 1px; "
            "text-transform: uppercase; background: transparent;"
        )
        sidebar_layout.addWidget(engine_section_lbl)

        engine_combo = QComboBox()
        engine_combo.setFixedHeight(32)

        # 엔진 목록 (그룹 구분자 포함)
        _ENGINE_GROUPS = [
            (None, "── Automatic ──"),
            ("auto", "  Auto (best tier)"),
            (None, "── Tetrahedral ──"),
            ("netgen", "  Netgen"),
            ("wildmesh", "  WildMesh"),
            ("tetwild", "  TetWild"),
            ("jigsaw", "  JIGSAW"),
            ("mmg", "  MMG3D"),
            (None, "── Hex-dominant ──"),
            ("snappy", "  SnappyHexMesh"),
            ("cfmesh", "  cfMesh"),
            ("cinolib_hex", "  Cinolib Hex"),
            (None, "── Polyhedral ──"),
            ("polyhedral", "  PolyDualMesh"),
            (None, "── Specialty ──"),
            ("meshpy", "  MeshPy (2D)"),
        ]
        for engine_key, display_text in _ENGINE_GROUPS:
            engine_combo.addItem(display_text)
            idx = engine_combo.count() - 1
            if engine_key is None:
                # separator — not selectable
                from PySide6.QtCore import Qt as _Qt
                engine_combo.model().item(idx).setEnabled(False)  # type: ignore[union-attr]
                engine_combo.model().item(idx).setData(  # type: ignore[union-attr]
                    "#4a5568", _Qt.ForegroundRole
                )
            else:
                engine_combo.model().item(idx).setData(engine_key, _Qt.UserRole)  # type: ignore[union-attr]

        # 기본 선택: "auto" (index 1)
        engine_combo.setCurrentIndex(1)
        self._engine_combo = engine_combo
        self._mesh_type_group = None
        self._mesh_type_cards = {}
        self._tier_combo = engine_combo  # legacy compat

        sidebar_layout.addWidget(engine_combo)
        engine_combo.currentTextChanged.connect(lambda _v: self._update_param_visibility())

        # ── [D] Quality Level 토글 버튼 ──────────────────────────────
        quality_section_lbl = QLabel("Quality Level")
        quality_section_lbl.setStyleSheet(
            "color: #bec7d4; font-size: 9px; letter-spacing: 1px; "
            "text-transform: uppercase; background: transparent;"
        )
        sidebar_layout.addWidget(quality_section_lbl)

        self._quality_combo = None  # legacy 호환 유지
        seg_frame = QFrame()
        seg_frame.setStyleSheet(
            "QFrame { background: #131313; border: 1px solid #3f4852; border-radius: 4px; }"
        )
        seg_layout = QHBoxLayout(seg_frame)
        seg_layout.setContentsMargins(2, 2, 2, 2)
        seg_layout.setSpacing(2)

        self._quality_seg_btns = {}
        for lvl_key, lvl_label in (("draft", "Draft"), ("standard", "Standard"), ("fine", "Fine")):
            btn = QPushButton(lvl_label)
            btn.setCheckable(False)
            btn.setFixedHeight(28)
            from PySide6.QtWidgets import QSizePolicy
            btn.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
            btn.setStyleSheet(
                "QPushButton { background: transparent; border: none; color: #bec7d4; "
                "border-radius: 3px; padding: 2px 8px; font-size: 11px; }"
                "QPushButton:hover { background: #2a2a2a; color: #e5e2e1; }"
            )
            self._quality_seg_btns[lvl_key] = btn
            seg_layout.addWidget(btn)

            def _make_quality_handler(k: str):
                def _on_quality_seg_clicked() -> None:
                    self._quality_level = QualityLevel(k)
                    self._refresh_quality_seg_btns()
                    if k == "fine":
                        import shutil as _shutil
                        from PySide6.QtWidgets import QMessageBox
                        if not _shutil.which("snappyHexMesh"):
                            QMessageBox.warning(
                                self._qmain,
                                "OpenFOAM 필요",
                                "Fine 품질은 snappyHexMesh(OpenFOAM)가 필요합니다.\n"
                                "OpenFOAM을 설치 후 재시도하세요.",
                            )
                return _on_quality_seg_clicked

            btn.clicked.connect(_make_quality_handler(lvl_key))

        sidebar_layout.addWidget(seg_frame)
        self._refresh_quality_seg_btns()

        # ── [E] Advanced Parameters 접이식 섹션 ─────────────────────
        adv_header = QFrame()
        adv_header.setStyleSheet(
            "QFrame { background: #201f1f; border: 1px solid #3f4852; "
            "border-radius: 4px; }"
        )
        adv_header.setFixedHeight(36)
        adv_header.setCursor(Qt.PointingHandCursor)
        adv_header_layout = QHBoxLayout(adv_header)
        adv_header_layout.setContentsMargins(8, 0, 8, 0)

        adv_toggle_btn = QPushButton("▶  Advanced Parameters")
        adv_toggle_btn.setStyleSheet(
            "QPushButton { background: transparent; border: none; color: #bec7d4; "
            "font-size: 11px; text-align: left; }"
            "QPushButton:hover { color: #e5e2e1; }"
        )
        self._adv_toggle_btn = adv_toggle_btn

        adv_gear = QLabel("⚙")
        adv_gear.setStyleSheet("color: #4a5568; background: transparent; font-size: 13px;")

        adv_header_layout.addWidget(adv_toggle_btn)
        adv_header_layout.addStretch()
        adv_header_layout.addWidget(adv_gear)
        sidebar_layout.addWidget(adv_header)

        # Advanced 내용 위젯 (기본 숨김)
        adv_content = QWidget()
        adv_content.setVisible(False)
        adv_content.setStyleSheet(
            "QWidget { background: #201f1f; border: 1px solid #3f4852; "
            "border-top: none; border-radius: 0 0 4px 4px; }"
        )
        adv_content_layout = QVBoxLayout(adv_content)
        adv_content_layout.setContentsMargins(8, 8, 8, 8)
        adv_content_layout.setSpacing(6)
        self._adv_content = adv_content

        def _toggle_advanced() -> None:
            visible = not adv_content.isVisible()
            adv_content.setVisible(visible)
            adv_toggle_btn.setText(
                ("▼  Advanced Parameters" if visible else "▶  Advanced Parameters")
            )

        adv_toggle_btn.clicked.connect(_toggle_advanced)
        adv_header.mousePressEvent = lambda _e: _toggle_advanced()  # type: ignore[method-assign]

        # Advanced 파라미터들
        def _add_adv_line_edit(label_text: str, attr: str, placeholder: str) -> QLineEdit:
            row = QWidget()
            row.setStyleSheet("background: transparent; border: none;")
            row_layout = QHBoxLayout(row)
            row_layout.setContentsMargins(0, 0, 0, 0)
            row_layout.setSpacing(4)
            lbl = QLabel(label_text)
            lbl.setFixedWidth(100)
            lbl.setStyleSheet("color: #bec7d4; font-size: 10px; background: transparent; border: none;")
            edit = QLineEdit()
            edit.setPlaceholderText(placeholder)
            edit.setFixedHeight(24)
            row_layout.addWidget(lbl)
            row_layout.addWidget(edit)
            adv_content_layout.addWidget(row)
            setattr(self, attr, edit)
            return edit

        self._element_size_edit = _add_adv_line_edit("Element Size:", "_element_size_edit", "auto")
        self._max_cells_edit = _add_adv_line_edit("Max Cells:", "_max_cells_edit", "none")

        # Max Iter spin
        iter_row = QWidget()
        iter_row.setStyleSheet("background: transparent; border: none;")
        iter_row_layout = QHBoxLayout(iter_row)
        iter_row_layout.setContentsMargins(0, 0, 0, 0)
        iter_row_layout.setSpacing(4)
        iter_lbl = QLabel("Max Iter:")
        iter_lbl.setFixedWidth(100)
        iter_lbl.setStyleSheet("color: #bec7d4; font-size: 10px; background: transparent; border: none;")
        self._iter_spin = QSpinBox()
        self._iter_spin.setRange(1, 10)  # type: ignore[union-attr]
        self._iter_spin.setValue(3)  # type: ignore[union-attr]
        self._iter_spin.setFixedHeight(24)  # type: ignore[union-attr]
        iter_row_layout.addWidget(iter_lbl)
        iter_row_layout.addWidget(self._iter_spin)
        adv_content_layout.addWidget(iter_row)

        # Checkboxes
        self._no_repair_check = QCheckBox("No Repair")
        self._no_repair_check.setStyleSheet("background: transparent; border: none;")  # type: ignore[union-attr]
        adv_content_layout.addWidget(self._no_repair_check)

        self._surface_remesh_check = QCheckBox("Force Surface Remesh")
        self._surface_remesh_check.setStyleSheet("background: transparent; border: none;")  # type: ignore[union-attr]
        adv_content_layout.addWidget(self._surface_remesh_check)

        self._allow_ai_fallback_check = QCheckBox("Allow AI Surface Repair")
        self._allow_ai_fallback_check.setStyleSheet("background: transparent; border: none;")  # type: ignore[union-attr]
        adv_content_layout.addWidget(self._allow_ai_fallback_check)

        # Remesh Engine
        remesh_row = QWidget()
        remesh_row.setStyleSheet("background: transparent; border: none;")
        remesh_row_layout = QHBoxLayout(remesh_row)
        remesh_row_layout.setContentsMargins(0, 0, 0, 0)
        remesh_row_layout.setSpacing(4)
        remesh_lbl = QLabel("Remesh Engine:")
        remesh_lbl.setFixedWidth(100)
        remesh_lbl.setStyleSheet("color: #bec7d4; font-size: 10px; background: transparent; border: none;")
        self._remesh_engine_combo = QComboBox()
        for eng in ("auto", "mmg", "quadwild"):
            self._remesh_engine_combo.addItem(eng)  # type: ignore[union-attr]
        self._remesh_engine_combo.setFixedHeight(24)  # type: ignore[union-attr]
        remesh_row_layout.addWidget(remesh_lbl)
        remesh_row_layout.addWidget(self._remesh_engine_combo)
        adv_content_layout.addWidget(remesh_row)
        self._remesh_engine_combo.currentTextChanged.connect(lambda _v: self._update_param_visibility())  # type: ignore[union-attr]

        # Legacy hidden edits (파라미터 수집 호환)
        for attr in (
            "_snappy_tol_edit", "_snappy_iters_edit", "_snappy_level_edit",
            "_tetwild_eps_edit", "_tetwild_energy_edit",
            "_cfmesh_max_cell_edit", "_cfmesh_surface_ref_edit", "_cfmesh_local_ref_edit",
            "_extra_params_edit",
        ):
            hidden_edit = QLineEdit()
            hidden_edit.setVisible(False)
            adv_content_layout.addWidget(hidden_edit)
            setattr(self, attr, hidden_edit)

        # Tier param edits (hidden)
        self._tier_param_edits = {}
        for key, _label, _kind, placeholder in self.TIER_PARAM_SPECS:
            hidden_edit = QLineEdit()
            hidden_edit.setPlaceholderText(placeholder)
            hidden_edit.setVisible(False)
            adv_content_layout.addWidget(hidden_edit)
            self._tier_param_edits[key] = hidden_edit

        sidebar_layout.addWidget(adv_content)

        # hidden help widgets (API compat)
        self._help_title_label = QLabel("")
        self._help_title_label.setVisible(False)
        sidebar_layout.addWidget(self._help_title_label)
        self._help_text_view = QTextBrowser()
        self._help_text_view.setVisible(False)
        sidebar_layout.addWidget(self._help_text_view)

        # Dry-run hidden checkbox (API compat)
        self._dry_run_check = QCheckBox("Dry-run")
        self._dry_run_check.setVisible(False)
        sidebar_layout.addWidget(self._dry_run_check)

        # Open output button (hidden, compat)
        self._open_output_btn = QPushButton("결과 폴더 열기")
        self._open_output_btn.setEnabled(False)
        self._open_output_btn.setVisible(False)
        self._open_output_btn.clicked.connect(self._on_open_output)
        sidebar_layout.addWidget(self._open_output_btn)

        # ── [F] 스페이서 ─────────────────────────────────────────────
        sidebar_layout.addStretch()

        # ── [G] Run 버튼 (하단 고정, full-width) ─────────────────────
        self._run_btn = QPushButton("▶  Run Meshing")
        self._run_btn.setFixedHeight(44)  # type: ignore[union-attr]
        self._run_btn.setStyleSheet(  # type: ignore[union-attr]
            "QPushButton { background: #40e56c; border: none; color: #0a1a10; "
            "border-radius: 6px; font-size: 13px; font-weight: bold; }"
            "QPushButton:hover { background: #55f07f; }"
            "QPushButton:pressed { background: #2bb54e; }"
            "QPushButton:disabled { background: #2a2a2a; color: #4a5568; }"
        )
        self._run_btn.clicked.connect(self._on_run_clicked)
        sidebar_layout.addWidget(self._run_btn)

        self._update_param_visibility()

        # ════════════════════════════════════════════════════════════════
        # [2] 메인 콘텐츠 (오른쪽)
        # ════════════════════════════════════════════════════════════════
        content_widget = QWidget()
        content_widget.setStyleSheet("background: #131313;")
        content_layout = QVBoxLayout(content_widget)
        content_layout.setContentsMargins(0, 0, 0, 0)
        content_layout.setSpacing(0)
        main_hbox.addWidget(content_widget, stretch=1)

        # ── 탭바 ─────────────────────────────────────────────────────
        tab_widget = QTabWidget()
        self._main_tab_widget = tab_widget
        content_layout.addWidget(tab_widget, stretch=1)

        # ── [탭 1] 3D Viewer ─────────────────────────────────────────
        viewer_tab = QWidget()
        viewer_tab.setStyleSheet("background: #131313;")
        viewer_tab_layout = QVBoxLayout(viewer_tab)
        viewer_tab_layout.setContentsMargins(0, 0, 0, 0)
        viewer_tab_layout.setSpacing(0)

        try:
            from desktop.qt_app.mesh_viewer import MeshViewerWidget
            self._mesh_viewer = MeshViewerWidget()
            viewer_tab_layout.addWidget(self._mesh_viewer, stretch=1)
        except ImportError:
            fallback_frame = QFrame()
            fallback_frame.setStyleSheet("background: #131313;")
            fallback_layout = QVBoxLayout(fallback_frame)
            fallback_lbl = QLabel("Drop a geometry file to preview")
            fallback_lbl.setAlignment(Qt.AlignCenter)
            fallback_lbl.setStyleSheet(
                "color: #4a5568; font-size: 16px; background: transparent;"
            )
            fallback_layout.addWidget(fallback_lbl)
            viewer_tab_layout.addWidget(fallback_frame, stretch=1)
            self._mesh_viewer = None

        # 메시 통계 오버레이 (좌상단 카드)
        stats_overlay = QFrame(viewer_tab)
        stats_overlay.setStyleSheet(
            "QFrame { background: rgba(28,27,27,220); border: 1px solid #3f4852; "
            "border-radius: 6px; }"
        )
        stats_overlay.setFixedWidth(160)
        stats_overlay.move(12, 12)
        stats_overlay.setVisible(False)
        stats_layout = QVBoxLayout(stats_overlay)
        stats_layout.setContentsMargins(10, 8, 10, 8)
        stats_layout.setSpacing(2)

        stats_title = QLabel("Mesh Statistics")
        stats_title.setStyleSheet(
            "color: #98cbff; font-size: 10px; font-weight: bold; background: transparent; border: none;"
        )
        stats_layout.addWidget(stats_title)

        self._kpi_labels = {}
        for stat_key, stat_title, stat_default in [
            ("vertices", "Vertices:", "—"),
            ("cells", "Cells:", "—"),
            ("quality", "Quality:", "—"),
            ("non_ortho", "Non-Ortho:", "—"),
            ("skewness", "Skewness:", "—"),
            ("aspect_ratio", "Aspect Ratio:", "—"),
        ]:
            stat_row = QWidget()
            stat_row.setStyleSheet("background: transparent; border: none;")
            stat_row_layout = QHBoxLayout(stat_row)
            stat_row_layout.setContentsMargins(0, 0, 0, 0)
            stat_row_layout.setSpacing(4)
            stat_lbl = QLabel(stat_title)
            stat_lbl.setStyleSheet("color: #bec7d4; font-size: 9px; background: transparent; border: none;")
            stat_val = QLabel(stat_default)
            stat_val.setStyleSheet("color: #e5e2e1; font-size: 9px; font-weight: bold; background: transparent; border: none;")
            stat_row_layout.addWidget(stat_lbl)
            stat_row_layout.addStretch()
            stat_row_layout.addWidget(stat_val)
            stats_layout.addWidget(stat_row)
            self._kpi_labels[stat_key] = stat_val

        stats_overlay.adjustSize()
        self._mesh_stats_overlay = stats_overlay

        # 파이프라인 스텝 인디케이터 (뷰어 탭 내 hidden, compat)
        self._pipeline_step_labels = []
        _PIPELINE_STEPS = [
            ("01", "ANALYZE"),
            ("02", "PREPROCESS"),
            ("03", "GENERATE"),
            ("04", "EVALUATE"),
        ]
        for _num, _name in _PIPELINE_STEPS:
            step_label = QLabel(f" {_num} {_name} ")
            step_label.setVisible(False)
            viewer_tab_layout.addWidget(step_label)
            self._pipeline_step_labels.append(step_label)

        tab_widget.addTab(viewer_tab, "3D Viewer")

        # ── [탭 2] Log ───────────────────────────────────────────────
        log_tab = QWidget()
        log_tab_layout = QVBoxLayout(log_tab)
        log_tab_layout.setContentsMargins(0, 0, 0, 0)
        log_tab_layout.setSpacing(0)

        # 터미널 헤더
        terminal_header = QFrame()
        terminal_header.setFixedHeight(28)
        terminal_header.setStyleSheet(
            "QFrame { background: #1c1b1b; border: none; border-bottom: 1px solid #3f4852; }"
        )
        terminal_header_layout = QHBoxLayout(terminal_header)
        terminal_header_layout.setContentsMargins(10, 0, 10, 0)
        terminal_header_layout.setSpacing(6)

        for dot_color in ("#ff5f56", "#ffbd2e", "#27c93f"):
            dot = QLabel("●")
            dot.setStyleSheet(f"color: {dot_color}; font-size: 10px; background: transparent;")
            terminal_header_layout.addWidget(dot)

        terminal_title = QLabel("autotessell — bash")
        terminal_title.setStyleSheet(
            "color: #bec7d4; font-size: 10px; background: transparent;"
        )
        terminal_header_layout.addWidget(terminal_title)
        terminal_header_layout.addStretch()

        log_tab_layout.addWidget(terminal_header)

        self._log_edit = QPlainTextEdit()
        self._log_edit.setReadOnly(True)  # type: ignore[union-attr]
        self._log_edit.setStyleSheet(  # type: ignore[union-attr]
            "QPlainTextEdit { background: #0d0d16; color: #bec7d4; "
            "font-family: 'JetBrains Mono', monospace; font-size: 10px; border: none; }"
        )
        log_tab_layout.addWidget(self._log_edit, stretch=1)

        tab_widget.addTab(log_tab, "Log")

        # ── [탭 3] Report ─────────────────────────────────────────────
        report_tab = QWidget()
        report_tab.setStyleSheet("background: #131313;")
        report_tab_layout = QVBoxLayout(report_tab)
        report_tab_layout.setContentsMargins(0, 0, 0, 0)

        # Placeholder (처리 전)
        report_placeholder = QLabel("Run the mesh generation to see quality metrics")
        report_placeholder.setAlignment(Qt.AlignCenter)
        report_placeholder.setStyleSheet(
            "color: #4a5568; font-size: 14px; background: transparent;"
        )
        self._report_placeholder = report_placeholder
        report_tab_layout.addWidget(report_placeholder, stretch=1)

        # Report 콘텐츠 위젯 (처리 후)
        report_content = QScrollArea()
        report_content.setWidgetResizable(True)
        report_content.setVisible(False)
        report_content.setStyleSheet("border: none; background: #131313;")
        self._report_content = report_content
        self._report_widget = report_content
        report_tab_layout.addWidget(report_content, stretch=1)

        tab_widget.addTab(report_tab, "Report")

        # ════════════════════════════════════════════════════════════════
        # [3] 하단 상태바 (48px 고정)
        # ════════════════════════════════════════════════════════════════
        status_bar = QFrame()
        status_bar.setFixedHeight(48)
        status_bar.setStyleSheet(
            "QFrame { background: #1c1b1b; border: none; border-top: 1px solid #3f4852; }"
        )
        status_bar_layout = QHBoxLayout(status_bar)
        status_bar_layout.setContentsMargins(12, 0, 12, 0)
        status_bar_layout.setSpacing(12)

        # 왼쪽: QProgressBar + 퍼센트
        status_progress = QProgressBar()
        status_progress.setFixedWidth(180)
        status_progress.setFixedHeight(8)
        status_progress.setRange(0, 100)
        status_progress.setValue(0)
        self._status_progress = status_progress
        self._progress_bar = status_progress

        percent_lbl = QLabel("0%")
        percent_lbl.setFixedWidth(36)
        percent_lbl.setStyleSheet("color: #bec7d4; font-size: 10px; background: transparent;")
        self._status_label = percent_lbl

        status_bar_layout.addWidget(status_progress)
        status_bar_layout.addWidget(percent_lbl)

        # 구분선
        sep1 = QFrame()
        sep1.setFrameShape(QFrame.VLine)
        sep1.setStyleSheet("color: #3f4852;")
        sep1.setFixedHeight(24)
        status_bar_layout.addWidget(sep1)

        # 중앙: 4단계 인디케이터
        _STAGE_DEFS = [
            ("Analyzing", "○"),
            ("Preprocessing", "○"),
            ("Meshing", "○"),
            ("Evaluating", "○"),
        ]
        self._status_stage_labels = []
        for i, (stage_name, stage_icon) in enumerate(_STAGE_DEFS):
            stage_lbl = QLabel(f"{stage_icon} {stage_name}")
            stage_lbl.setStyleSheet(
                "color: #4a5568; font-size: 10px; background: transparent;"
            )
            self._status_stage_labels.append(stage_lbl)
            status_bar_layout.addWidget(stage_lbl)
            if i < len(_STAGE_DEFS) - 1:
                dash = QLabel("—")
                dash.setStyleSheet("color: #3f4852; font-size: 10px; background: transparent;")
                status_bar_layout.addWidget(dash)

        status_bar_layout.addStretch()

        # 오른쪽: 상태 텍스트
        ready_lbl = QLabel("Ready")
        ready_lbl.setStyleSheet("color: #bec7d4; font-size: 10px; background: transparent;")
        self._active_tier_label = ready_lbl
        status_bar_layout.addWidget(ready_lbl)

        root_vbox.addWidget(status_bar)

        self._set_help_topic("tier")

    def show(self) -> None:  # pragma: no cover
        if not hasattr(self, "_qmain"):
            self._build()
        self._qmain.move(80, 80)
        self._qmain.showNormal()
        self._qmain.show()

    def _on_file_dropped(self, path: str) -> None:  # pragma: no cover
        """DropZone에서 파일이 드롭되었을 때 처리."""
        try:
            self.set_input_path(path)
            self._append_log(f"입력 설정(드롭): {path}")
            if self._mesh_viewer is not None:
                from PySide6.QtCore import QTimer
                self._append_log("[미리보기] 입력 파일을 3D 뷰어에 로드 중...")
                QTimer.singleShot(50, lambda: self._load_input_preview())
        except ValueError as exc:
            self._append_log(f"[오류] {exc}")

    def _on_pick_input(self) -> None:  # pragma: no cover
        if not hasattr(self, "_qt_file_dialog"):
            return
        filt = "Mesh/CAD Files (*.stl *.obj *.ply *.off *.3mf *.step *.stp *.iges *.igs *.brep *.msh *.vtu *.vtk)"
        path, _ = self._qt_file_dialog.getOpenFileName(self._qmain, "입력 파일 선택", "", filt)
        if path:
            try:
                self.set_input_path(path)
                self._append_log(f"입력 설정: {path}")
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
        """입력 파일 미리보기 로드."""
        if self._mesh_viewer is None or self._input_path is None:
            return
        try:
            self._append_log(f"[미리보기] 로드 시작: {self._input_path.name}")
            self._mesh_viewer.load_mesh(str(self._input_path))  # type: ignore[union-attr]
        except Exception as exc:  # noqa: BLE001
            self._append_log(f"[미리보기] 로드 실패: {exc}")

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

        if self._output_edit is not None:
            text = self._output_edit.text().strip()  # type: ignore[union-attr]
            if text:
                self.set_output_dir(text)
        if self._output_dir is None:
            self._output_dir = self._input_path.parent / f"{self._input_path.stem}_case"

        tier = self._tier_combo_text()
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

        for attr, key in (
            ("_cfmesh_surface_ref_edit", "cfmesh_surface_refinement"),
            ("_cfmesh_local_ref_edit", "cfmesh_local_refinement"),
        ):
            edit = getattr(self, attr, None)
            if edit is not None:
                raw = edit.text().strip()  # type: ignore[union-attr]
                if raw and self._is_param_active(key):
                    try:
                        tier_params[key] = json.loads(raw)
                    except Exception as exc:
                        self._append_log(f"[오류] {key} JSON 파싱 실패: {exc}")
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
                elif kind == "bool":
                    tier_params[key] = raw.lower() in ("true", "1", "yes", "on")
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
            self._run_btn.setText("⟳  Processing...")  # type: ignore[union-attr]
            self._run_btn.setStyleSheet(  # type: ignore[union-attr]
                "QPushButton { background: #2a2a2a; border: none; color: #4a5568; "
                "border-radius: 6px; font-size: 13px; font-weight: bold; }"
            )
        if self._open_output_btn is not None:
            self._open_output_btn.setEnabled(False)  # type: ignore[union-attr]
        if self._status_label is not None:
            self._status_label.setText("0%")  # type: ignore[union-attr]
        if self._progress_bar is not None:
            self._progress_bar.setRange(0, 100)  # type: ignore[union-attr]
            self._progress_bar.setValue(0)  # type: ignore[union-attr]
        if self._active_tier_label is not None:
            self._active_tier_label.setText("Running...")  # type: ignore[union-attr]

        # 스테이지 인디케이터 초기화
        self._update_stage_indicator(0)

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
                self._run_btn.setText("▶  Run Meshing")  # type: ignore[union-attr]
                self._run_btn.setStyleSheet(  # type: ignore[union-attr]
                    "QPushButton { background: #40e56c; border: none; color: #0a1a10; "
                    "border-radius: 6px; font-size: 13px; font-weight: bold; }"
                    "QPushButton:hover { background: #55f07f; }"
                    "QPushButton:pressed { background: #2bb54e; }"
                    "QPushButton:disabled { background: #2a2a2a; color: #4a5568; }"
                )
            if self._active_tier_label is not None:
                self._active_tier_label.setText("FAIL")  # type: ignore[union-attr]
            self._append_log(f"[오류] Worker 시작 실패: {exc.__class__.__name__}: {exc}")

    def _update_stage_indicator(self, active_stage: int) -> None:  # pragma: no cover
        """하단 상태바의 스테이지 인디케이터를 업데이트한다.

        active_stage: 0=Analyzing, 1=Preprocessing, 2=Meshing, 3=Evaluating
        -1 = 모두 완료
        """
        for i, lbl in enumerate(self._status_stage_labels):
            if i < active_stage:
                lbl.setStyleSheet(  # type: ignore[union-attr]
                    "color: #40e56c; font-size: 10px; background: transparent;"
                )
                text = lbl.text().split(" ", 1)[-1]  # type: ignore[union-attr]
                lbl.setText(f"✓ {text}")  # type: ignore[union-attr]
            elif i == active_stage:
                lbl.setStyleSheet(  # type: ignore[union-attr]
                    "color: #98cbff; font-size: 10px; background: transparent;"
                )
                text = lbl.text().split(" ", 1)[-1]  # type: ignore[union-attr]
                lbl.setText(f"⟳ {text}")  # type: ignore[union-attr]
            else:
                lbl.setStyleSheet(  # type: ignore[union-attr]
                    "color: #4a5568; font-size: 10px; background: transparent;"
                )
                text = lbl.text().split(" ", 1)[-1]  # type: ignore[union-attr]
                lbl.setText(f"○ {text}")  # type: ignore[union-attr]

    def _on_progress_percent(self, percent: int, message: str) -> None:  # pragma: no cover
        if self._progress_bar is not None:
            self._progress_bar.setRange(0, 100)  # type: ignore[union-attr]
            self._progress_bar.setValue(max(0, min(100, int(percent))))  # type: ignore[union-attr]
        if self._status_label is not None:
            self._status_label.setText(f"{int(percent)}%")  # type: ignore[union-attr]

        # 스테이지 매핑: percent → stage index
        pct = int(percent)
        if pct < 30:
            stage = 0
        elif pct < 45:
            stage = 1
        elif pct < 75:
            stage = 2
        else:
            stage = 3
        self._update_stage_indicator(stage)

    def _on_pipeline_finished(self, result: object) -> None:  # pragma: no cover
        if self._run_btn is not None:
            self._run_btn.setEnabled(True)  # type: ignore[union-attr]
            self._run_btn.setText("▶  Run Meshing")  # type: ignore[union-attr]
            self._run_btn.setStyleSheet(  # type: ignore[union-attr]
                "QPushButton { background: #40e56c; border: none; color: #0a1a10; "
                "border-radius: 6px; font-size: 13px; font-weight: bold; }"
                "QPushButton:hover { background: #55f07f; }"
                "QPushButton:pressed { background: #2bb54e; }"
                "QPushButton:disabled { background: #2a2a2a; color: #4a5568; }"
            )
        if self._progress_bar is not None:
            self._progress_bar.setRange(0, 100)  # type: ignore[union-attr]
            self._progress_bar.setValue(100)  # type: ignore[union-attr]
        if self._status_label is not None:
            self._status_label.setText("100%")  # type: ignore[union-attr]

        success = bool(getattr(result, "success", False))
        elapsed = float(getattr(result, "total_time_seconds", 0.0))
        err = getattr(result, "error", None)
        if result is None:
            success = False
            err = "Worker 내부 예외로 결과 객체를 만들지 못했습니다."

        status_text = "PASS" if success else "FAIL"
        if self._active_tier_label is not None:
            self._active_tier_label.setText(status_text)  # type: ignore[union-attr]

        if self._open_output_btn is not None and self._output_dir is not None:
            self._open_output_btn.setEnabled(self._output_dir.exists())  # type: ignore[union-attr]

        self._append_log(f"[완료] {'성공' if success else '실패'} ({elapsed:.1f}s)")

        # 메시 통계 오버레이 표시
        if success and self._mesh_stats_overlay is not None:
            self._mesh_stats_overlay.setVisible(True)  # type: ignore[union-attr]

        # 메시 뷰어에 메시 로드
        if success and self._output_dir is not None:
            self._load_mesh_to_viewer()

        # Report 탭 업데이트
        self._update_report_tab(result)

        if err:
            self._append_log(f"[오류] {err}")

    def _update_report_tab(self, result: object) -> None:  # pragma: no cover
        """Report 탭 내용을 파이프라인 결과로 업데이트한다."""
        from PySide6.QtWidgets import (
            QFrame, QHBoxLayout, QLabel, QScrollArea,
            QVBoxLayout, QWidget,
        )
        from PySide6.QtCore import Qt

        success = bool(getattr(result, "success", False))

        # placeholder 숨기고 content 보이기
        if self._report_placeholder is not None:
            self._report_placeholder.setVisible(False)  # type: ignore[union-attr]
        if self._report_content is not None:
            self._report_content.setVisible(True)  # type: ignore[union-attr]

        # 콘텐츠 위젯 빌드
        report_inner = QWidget()
        report_inner.setStyleSheet("background: #131313;")
        report_inner_layout = QVBoxLayout(report_inner)
        report_inner_layout.setContentsMargins(20, 20, 20, 20)
        report_inner_layout.setSpacing(16)

        # 헤더 카드
        header_card = QFrame()
        header_card.setStyleSheet(
            "QFrame { background: #1c1b1b; border: 1px solid #3f4852; border-radius: 8px; }"
        )
        header_layout = QVBoxLayout(header_card)
        header_layout.setContentsMargins(16, 12, 16, 12)

        tier_used = getattr(result, "tier_used", "auto") or "auto"
        checks_ok = "All Checks ✓" if success else "Checks Failed ✗"
        checks_color = "#40e56c" if success else "#e55a40"

        header_row = QFrame()
        header_row.setStyleSheet("background: transparent; border: none;")
        header_row_layout = QHBoxLayout(header_row)
        header_row_layout.setContentsMargins(0, 0, 0, 0)
        engine_lbl = QLabel(f"Generated with {tier_used} engine")
        engine_lbl.setStyleSheet("color: #bec7d4; font-size: 12px; background: transparent;")
        checks_lbl = QLabel(checks_ok)
        checks_lbl.setStyleSheet(f"color: {checks_color}; font-size: 12px; font-weight: bold; background: transparent;")
        header_row_layout.addWidget(engine_lbl)
        header_row_layout.addStretch()
        header_row_layout.addWidget(checks_lbl)
        header_layout.addWidget(header_row)

        # KPI 숫자 카드들
        kpi_row = QFrame()
        kpi_row.setStyleSheet("background: transparent; border: none;")
        kpi_row_layout = QHBoxLayout(kpi_row)
        kpi_row_layout.setContentsMargins(0, 8, 0, 0)
        kpi_row_layout.setSpacing(12)

        eval_report = getattr(result, "evaluation_report", None)
        n_vertices = "—"
        n_cells = "—"
        quality_score = "—"
        if eval_report:
            n_vertices = str(getattr(eval_report, "n_vertices", "—") or "—")
            n_cells = str(getattr(eval_report, "n_cells", "—") or "—")
            qs = getattr(eval_report, "quality_score", None)
            if qs is not None:
                quality_score = f"{float(qs) * 100:.1f}%"

        for val, title in [(n_vertices, "Vertices"), (n_cells, "Cells"), (quality_score, "Quality Score")]:
            kpi_card = QFrame()
            kpi_card.setStyleSheet(
                "QFrame { background: #201f1f; border: 1px solid #3f4852; border-radius: 6px; padding: 8px; }"
            )
            kpi_card_layout = QVBoxLayout(kpi_card)
            kpi_card_layout.setContentsMargins(12, 10, 12, 10)
            kpi_card_layout.setSpacing(4)
            val_lbl = QLabel(val)
            val_lbl.setAlignment(Qt.AlignCenter)
            val_lbl.setStyleSheet(
                "color: #98cbff; font-size: 22px; font-weight: bold; background: transparent; border: none;"
            )
            title_lbl = QLabel(title)
            title_lbl.setAlignment(Qt.AlignCenter)
            title_lbl.setStyleSheet(
                "color: #bec7d4; font-size: 10px; background: transparent; border: none;"
            )
            kpi_card_layout.addWidget(val_lbl)
            kpi_card_layout.addWidget(title_lbl)
            kpi_row_layout.addWidget(kpi_card)

        header_layout.addWidget(kpi_row)
        report_inner_layout.addWidget(header_card)

        # 품질 지표 카드들
        metrics_row = QFrame()
        metrics_row.setStyleSheet("background: transparent; border: none;")
        metrics_row_layout = QHBoxLayout(metrics_row)
        metrics_row_layout.setSpacing(12)

        non_ortho_val = None
        skewness_val = None
        hausdorff_val = None
        if eval_report:
            non_ortho_val = getattr(eval_report, "max_non_orthogonality", None)
            skewness_val = getattr(eval_report, "max_skewness", None)
            hausdorff_val = getattr(eval_report, "hausdorff_distance", None)

        for metric_title, metric_val, threshold, unit in [
            ("Non-Orthogonality", non_ortho_val, 70.0, "°"),
            ("Skewness", skewness_val, 0.85, ""),
            ("Hausdorff", hausdorff_val, 0.01, ""),
        ]:
            metric_card = QFrame()
            metric_card.setStyleSheet(
                "QFrame { background: #1c1b1b; border: 1px solid #3f4852; border-radius: 8px; }"
            )
            metric_card_layout = QVBoxLayout(metric_card)
            metric_card_layout.setContentsMargins(12, 10, 12, 10)
            metric_card_layout.setSpacing(4)

            m_title_lbl = QLabel(metric_title)
            m_title_lbl.setAlignment(Qt.AlignCenter)
            m_title_lbl.setStyleSheet(
                "color: #bec7d4; font-size: 10px; font-weight: bold; background: transparent; border: none;"
            )

            if metric_val is not None:
                pass_fail = "PASS" if float(metric_val) <= threshold else "FAIL"
                pf_color = "#40e56c" if pass_fail == "PASS" else "#e55a40"
                m_val_text = f"{pass_fail}  {float(metric_val):.3f}{unit}"
            else:
                pf_color = "#bec7d4"
                m_val_text = "—"

            m_val_lbl = QLabel(m_val_text)
            m_val_lbl.setAlignment(Qt.AlignCenter)
            m_val_lbl.setStyleSheet(
                f"color: {pf_color}; font-size: 12px; font-weight: bold; background: transparent; border: none;"
            )

            metric_card_layout.addWidget(m_title_lbl)
            metric_card_layout.addWidget(m_val_lbl)
            metrics_row_layout.addWidget(metric_card)

        report_inner_layout.addWidget(metrics_row)
        report_inner_layout.addStretch()

        if self._report_content is not None:
            self._report_content.setWidget(report_inner)  # type: ignore[union-attr]

    def _load_mesh_to_viewer(self) -> None:  # pragma: no cover
        """생성된 볼륨 메시를 뷰어에 로드."""
        if self._mesh_viewer is None or self._output_dir is None:
            return

        try:
            constant_dir = self._output_dir / "constant" / "polyMesh"
            if constant_dir.exists():
                if self._mesh_viewer.load_polymesh(str(self._output_dir)):  # type: ignore[union-attr]
                    self._append_log("[메시 뷰어] polyMesh 로드 성공")
                    return

            for pattern in ("**/*.vtu", "**/*.vtk"):
                files = list(self._output_dir.glob(pattern))
                if files:
                    mesh_file = max(files, key=lambda p: p.stat().st_mtime)
                    if self._mesh_viewer.load_mesh(str(mesh_file), show_edges=True):  # type: ignore[union-attr]
                        self._append_log(f"[메시 뷰어] 볼륨 메시 로드 성공: {mesh_file.name}")
                        return

            msh_files = list(self._output_dir.glob("**/*.msh"))
            if msh_files:
                mesh_file = max(msh_files, key=lambda p: p.stat().st_mtime)
                if self._mesh_viewer.load_mesh(str(mesh_file), show_edges=True):  # type: ignore[union-attr]
                    self._append_log(f"[메시 뷰어] MSH 메시 로드 성공: {mesh_file.name}")
                    return

            stl_files = [
                p for p in self._output_dir.glob("**/*.stl")
                if "preprocessed" not in p.name.lower()
            ]
            if stl_files:
                mesh_file = max(stl_files, key=lambda p: p.stat().st_mtime)
                if self._mesh_viewer.load_mesh(str(mesh_file), show_edges=True):  # type: ignore[union-attr]
                    self._append_log(f"[메시 뷰어] STL 로드 성공: {mesh_file.name}")
                    return

            self._append_log("[경고] 로드할 볼륨 메시 파일을 찾을 수 없습니다.")

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

    def _tier_combo_text(self) -> str:  # pragma: no cover
        """현재 선택된 엔진/tier 이름을 반환한다."""
        if self._engine_combo is None:
            return "auto"
        text = self._engine_combo.currentText().strip()  # type: ignore[union-attr]
        # separator나 group header가 선택되면 "auto" 반환
        text = text.strip()
        if text.startswith("──") or not text:
            return "auto"
        return text.strip() if text.strip() else "auto"

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
            else:
                text = f"{key}\n상세 설명이 아직 등록되지 않았습니다."

        if self._help_title_label is not None:
            self._help_title_label.setText(f"Parameter Help: {key}")  # type: ignore[union-attr]
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
        tier = self._tier_combo_text()
        remesh = self._remesh_engine_combo.currentText() if self._remesh_engine_combo is not None else "auto"  # type: ignore[union-attr]
        for key, widgets in self._param_widgets.items():
            visible = self._param_is_applicable(key, tier, remesh)
            for widget in widgets:
                if hasattr(widget, "setVisible"):
                    widget.setVisible(visible)  # type: ignore[union-attr]

    def _refresh_quality_seg_btns(self) -> None:
        """현재 _quality_level에 맞게 세그먼트 버튼 스타일을 갱신한다."""
        active = self._quality_level.value
        for key, btn in self._quality_seg_btns.items():
            if key == active:
                btn.setStyleSheet(  # type: ignore[union-attr]
                    "QPushButton { background: #0078d4; border: none; color: #ffffff; "
                    "border-radius: 3px; padding: 2px 8px; font-size: 11px; font-weight: bold; }"
                )
            else:
                btn.setStyleSheet(  # type: ignore[union-attr]
                    "QPushButton { background: transparent; border: none; color: #bec7d4; "
                    "border-radius: 3px; padding: 2px 8px; font-size: 11px; }"
                    "QPushButton:hover { background: #2a2a2a; color: #e5e2e1; }"
                )

    def update_pipeline_step(self, step_idx: int) -> None:  # pragma: no cover
        """파이프라인 스텝 인디케이터를 갱신한다.

        step_idx: 0=ANALYZE, 1=PREPROCESS, 2=GENERATE, 3=EVALUATE
        -1 = 모두 초기화
        """
        for i, lbl in enumerate(self._pipeline_step_labels):
            if i < step_idx:
                lbl.setStyleSheet(  # type: ignore[union-attr]
                    "color: #40e56c; font-size: 10px; letter-spacing: 1px; "
                    "padding: 4px 10px; border-radius: 2px; background: #201f1f;"
                )
            elif i == step_idx:
                lbl.setStyleSheet(  # type: ignore[union-attr]
                    "color: #ffffff; font-size: 10px; letter-spacing: 1px; "
                    "padding: 4px 10px; border-radius: 2px; background: #00629d;"
                )
            else:
                lbl.setStyleSheet(  # type: ignore[union-attr]
                    "color: #4a4a4a; font-size: 10px; letter-spacing: 1px; "
                    "padding: 4px 10px; border-radius: 2px;"
                )

        # 상태바 스테이지 인디케이터도 동기화
        self._update_stage_indicator(step_idx)

    def update_kpi(
        self,
        non_ortho: float | None = None,
        skewness: float | None = None,
        aspect_ratio: float | None = None,
    ) -> None:  # pragma: no cover
        """메시 품질 KPI 스코어카드 수치를 업데이트한다."""
        mapping = {
            "non_ortho": non_ortho,
            "skewness": skewness,
            "aspect_ratio": aspect_ratio,
        }
        for key, val in mapping.items():
            lbl = self._kpi_labels.get(key)
            if lbl is None:
                continue
            if val is None:
                lbl.setText("—")  # type: ignore[union-attr]
                lbl.setStyleSheet(  # type: ignore[union-attr]
                    "color: #98cbff; font-size: 9px; font-weight: bold; background: transparent; border: none;"
                )
            else:
                text = f"{val:.2f}"
                thresholds = {"non_ortho": 70.0, "skewness": 0.85, "aspect_ratio": 1000.0}
                threshold = thresholds.get(key, float("inf"))
                color = "#40e56c" if val <= threshold else "#e55a40"
                lbl.setText(text)  # type: ignore[union-attr]
                lbl.setStyleSheet(  # type: ignore[union-attr]
                    f"color: {color}; font-size: 9px; font-weight: bold; background: transparent; border: none;"
                )

    def _param_is_applicable(self, key: str, tier: str, remesh_engine: str) -> bool:
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
