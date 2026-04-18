"""AutoTessell 메인 윈도우 — 디자인 스펙 1:1 재구현 (v0.3.6+).

참조: AutoTessell GUI.html (Claude Design 핸드오프 번들)
CAD 다크 팔레트 (ParaView/Rhino 스타일), 3-column layout, 모든 데코 포함.
"""
from __future__ import annotations

import json
import os
import sys
from enum import StrEnum
from pathlib import Path

# ═════════════════════════════════════════════════════════════════════════════
# 데이터 상수 (기존 API 보존 — tests/test_qt_app.py 요구사항)
# ═════════════════════════════════════════════════════════════════════════════


class QualityLevel(StrEnum):
    DRAFT = "draft"
    STANDARD = "standard"
    FINE = "fine"


# 공통 팔레트 (Engineering CAD Dark — ParaView/Rhino inspired)
PALETTE = {
    "bg_0": "#0b0d10", "bg_1": "#101318", "bg_2": "#161a20",
    "bg_3": "#1c2129", "bg_4": "#242a33",
    "line_1": "#262c36", "line_2": "#323a46", "line_3": "#3e4757",
    "text_0": "#e8ecf2", "text_1": "#b6bdc9", "text_2": "#818a99", "text_3": "#5a6270",
    "accent": "#4ea3ff", "accent_hover": "#6ab4ff", "accent_dim": "#2c5f97",
    "accent_soft": "rgba(78,163,255,0.12)",
    "ok": "#4ade80", "warn": "#f5b454", "err": "#ff6b6b",
    "hex": "#9b87ff", "tet": "#5ee5d6",
}


# ═════════════════════════════════════════════════════════════════════════════
# 글로벌 QSS 스타일시트
# ═════════════════════════════════════════════════════════════════════════════

GLOBAL_STYLE = f"""
QMainWindow, QWidget {{
    background-color: {PALETTE['bg_1']};
    color: {PALETTE['text_0']};
    font-family: 'Pretendard', 'Inter', 'Segoe UI', -apple-system, sans-serif;
    font-size: 13px;
}}
QMenuBar {{
    background: {PALETTE['bg_1']}; border-bottom: 1px solid {PALETTE['line_1']};
    color: {PALETTE['text_1']}; font-size: 12.5px; padding: 2px 6px;
}}
QMenuBar::item {{ padding: 6px 10px; background: transparent; border-radius: 4px; }}
QMenuBar::item:selected {{ background: {PALETTE['bg_3']}; color: {PALETTE['text_0']}; }}
QMenu {{
    background: {PALETTE['bg_1']}; border: 1px solid {PALETTE['line_2']};
    border-radius: 6px; padding: 4px; color: {PALETTE['text_1']};
}}
QMenu::item {{ padding: 6px 18px 6px 12px; border-radius: 4px; font-size: 12px; }}
QMenu::item:selected {{ background: {PALETTE['accent']}; color: #05111e; }}
QMenu::separator {{ height: 1px; background: {PALETTE['line_1']}; margin: 4px 2px; }}

QComboBox {{
    background: {PALETTE['bg_2']}; border: 1px solid {PALETTE['line_2']};
    border-radius: 5px; padding: 8px 10px; color: {PALETTE['text_0']};
    font-size: 12.5px; min-height: 28px;
}}
QComboBox:hover {{ border-color: {PALETTE['line_3']}; }}
QComboBox:focus {{ border-color: {PALETTE['accent']}; }}
QComboBox::drop-down {{ border: none; width: 22px; }}
QComboBox::down-arrow {{ width: 8px; height: 8px; }}
QComboBox QAbstractItemView {{
    background: {PALETTE['bg_2']}; selection-background-color: {PALETTE['accent_dim']};
    border: 1px solid {PALETTE['line_2']}; color: {PALETTE['text_0']};
    font-size: 12.5px; padding: 2px; outline: none;
}}

QLineEdit {{
    background: {PALETTE['bg_2']}; border: 1px solid {PALETTE['line_2']};
    border-radius: 5px; padding: 6px 10px; color: {PALETTE['text_0']};
    font-size: 12.5px; min-height: 28px;
    selection-background-color: {PALETTE['accent_dim']};
}}
QLineEdit:hover {{ border-color: {PALETTE['line_3']}; }}
QLineEdit:focus {{ border-color: {PALETTE['accent']}; }}

QPushButton {{
    background: {PALETTE['bg_2']}; border: 1px solid {PALETTE['line_2']};
    border-radius: 5px; padding: 6px 14px; color: {PALETTE['text_1']};
    font-size: 12px; font-weight: 500; min-height: 28px;
}}
QPushButton:hover {{ background: {PALETTE['bg_3']}; border-color: {PALETTE['line_3']}; color: {PALETTE['text_0']}; }}
QPushButton:pressed {{ background: {PALETTE['bg_4']}; }}
QPushButton:disabled {{ background: {PALETTE['bg_0']}; color: {PALETTE['text_3']}; border-color: {PALETTE['line_1']}; }}
QPushButton[accent="primary"] {{
    background: {PALETTE['accent']}; border: 1px solid {PALETTE['accent']}; color: #05111e;
    font-weight: 600;
}}
QPushButton[accent="primary"]:hover {{ background: {PALETTE['accent_hover']}; border-color: {PALETTE['accent_hover']}; }}
QPushButton[accent="danger"] {{
    background: rgba(255,60,60,0.08); border: 1px solid #5f2d2d; color: #ff8888;
}}
QPushButton[accent="danger"]:hover {{ background: rgba(255,60,60,0.15); color: {PALETTE['err']}; }}

QLabel {{ color: {PALETTE['text_0']}; font-size: 13px; background: transparent; }}

QScrollBar:vertical {{ background: transparent; width: 8px; margin: 0; }}
QScrollBar::handle:vertical {{ background: {PALETTE['line_2']}; border-radius: 4px; min-height: 24px;
                               border: 2px solid transparent; background-clip: padding; }}
QScrollBar::handle:vertical:hover {{ background: {PALETTE['line_3']}; }}
QScrollBar:horizontal {{ background: transparent; height: 8px; }}
QScrollBar::handle:horizontal {{ background: {PALETTE['line_2']}; border-radius: 4px; min-width: 24px;
                                 border: 2px solid transparent; background-clip: padding; }}
QScrollBar::handle:horizontal:hover {{ background: {PALETTE['line_3']}; }}
QScrollBar::add-line, QScrollBar::sub-line {{ width: 0; height: 0; }}
QScrollBar::add-page, QScrollBar::sub-page {{ background: transparent; }}

QPlainTextEdit, QTextBrowser, QTextEdit {{
    background: #05070a; border: none; color: {PALETTE['text_1']};
    font-family: 'JetBrains Mono', 'SF Mono', 'Consolas', monospace;
    font-size: 11px;
    selection-background-color: {PALETTE['accent_dim']};
}}

QSpinBox, QDoubleSpinBox {{
    background: {PALETTE['bg_2']}; border: 1px solid {PALETTE['line_2']};
    border-radius: 5px; padding: 5px 8px; color: {PALETTE['text_0']};
    font-family: 'JetBrains Mono', monospace; font-size: 12px; min-height: 26px;
}}
QSpinBox:hover, QDoubleSpinBox:hover {{ border-color: {PALETTE['line_3']}; }}
QSpinBox:focus, QDoubleSpinBox:focus {{ border-color: {PALETTE['accent']}; }}

QCheckBox {{ color: {PALETTE['text_1']}; spacing: 8px; font-size: 12px; background: transparent; }}
QCheckBox::indicator {{ width: 14px; height: 14px; border: 1px solid {PALETTE['line_3']};
                        border-radius: 3px; background: {PALETTE['bg_2']}; }}
QCheckBox::indicator:hover {{ border-color: {PALETTE['accent']}; }}
QCheckBox::indicator:checked {{ background: {PALETTE['accent']}; border-color: {PALETTE['accent']}; }}
QRadioButton {{ color: {PALETTE['text_1']}; spacing: 8px; font-size: 12px; background: transparent; }}
QRadioButton::indicator {{ width: 14px; height: 14px; border: 1px solid {PALETTE['line_3']};
                           border-radius: 7px; background: {PALETTE['bg_2']}; }}
QRadioButton::indicator:checked {{ background: {PALETTE['accent']}; border-color: {PALETTE['accent']}; }}

QTabWidget::pane {{ border: none; background: {PALETTE['bg_1']}; }}
QTabBar::tab {{
    background: transparent; color: {PALETTE['text_2']};
    padding: 10px 16px; border: none;
    border-bottom: 2px solid transparent;
    font-size: 12px; font-weight: 500; min-width: 80px;
}}
QTabBar::tab:selected {{ color: {PALETTE['text_0']}; border-bottom-color: {PALETTE['accent']}; }}
QTabBar::tab:hover:!selected {{ color: {PALETTE['text_1']}; }}

QScrollArea {{ border: none; background: transparent; }}
QToolTip {{
    background: {PALETTE['bg_3']}; color: {PALETTE['text_0']};
    border: 1px solid {PALETTE['line_2']}; padding: 5px 9px; border-radius: 4px;
    font-size: 11.5px;
}}
QSlider::groove:horizontal {{
    height: 3px; background: {PALETTE['bg_3']}; border: 1px solid {PALETTE['line_1']}; border-radius: 2px;
}}
QSlider::handle:horizontal {{
    background: {PALETTE['accent']}; width: 12px; height: 12px;
    margin: -5px 0; border-radius: 6px; border: 2px solid {PALETTE['bg_1']};
}}
QSlider::handle:horizontal:hover {{ background: {PALETTE['accent_hover']}; }}
"""


# ═════════════════════════════════════════════════════════════════════════════
# AutoTessellWindow — 메인 윈도우 클래스
# ═════════════════════════════════════════════════════════════════════════════


class AutoTessellWindow:  # type: ignore[misc]
    """디자인 스펙 1:1 재현. HTML AutoTessell GUI.html 구조와 매핑."""

    SUPPORTED_EXTENSIONS: tuple[str, ...] = (
        ".stl", ".obj", ".ply", ".off", ".3mf",
        ".step", ".stp", ".iges", ".igs", ".brep",
        ".msh", ".vtu", ".vtk",
        ".las", ".laz",
    )

    # 파라미터 스펙 (기존 API 유지 — 테스트 요구)
    TIER_PARAM_SPECS: tuple[tuple[str, str, str, str], ...] = (
        ("core_quality", "Core Quality", "float", "2.0"),
        ("core_max_vertices", "Core Max Vertices", "int", "auto"),
        ("netgen_grading", "Netgen Grading", "float", "0.3"),
        ("netgen_curvaturesafety", "Netgen CurvatureSafety", "float", "2.0"),
        ("netgen_segmentsperedge", "Netgen Segments/Edge", "float", "1.0"),
        ("netgen_closeedgefac", "Netgen CloseEdgeFac", "float", "2.0"),
        ("ng_max_h", "Netgen maxh", "float", "auto"),
        ("ng_min_h", "Netgen minh", "float", "auto"),
        ("ng_fineness", "Netgen Fineness", "float", "0.5"),
        ("ng_second_order", "Netgen 2nd Order", "bool", "false"),
        ("meshpy_min_angle", "MeshPy Min Angle", "float", "25.0"),
        ("meshpy_max_volume", "MeshPy MaxVolume", "float", "auto"),
        ("meshpy_max_area_2d", "MeshPy MaxArea2D", "float", "auto"),
        ("jigsaw_hmax", "JIGSAW hmax", "float", "auto"),
        ("jigsaw_hmin", "JIGSAW hmin", "float", "auto"),
        ("jigsaw_optm_iter", "JIGSAW Opt Iter", "int", "32"),
        ("snappy_max_local_cells", "Snappy MaxLocalCells", "int", "1000000"),
        ("snappy_max_global_cells", "Snappy MaxGlobalCells", "int", "10000000"),
        ("snappy_min_refinement_cells", "Snappy MinRefCells", "int", "10"),
        ("snappy_n_cells_between_levels", "Snappy CellsBetweenLv", "int", "3"),
        ("snappy_snap_smooth_patch", "Snappy SmoothPatch", "int", "3"),
        ("snappy_snap_relax_iter", "Snappy RelaxIter", "int", "5"),
        ("snappy_feature_snap_iter", "Snappy FeatureSnapIter", "int", "10"),
        ("tetwild_epsilon", "TetWild Epsilon", "float", "auto"),
        ("tetwild_edge_length", "TetWild Edge Length (abs)", "float", "auto"),
        ("tetwild_edge_length_fac", "TetWild Edge Length Fac", "float", "auto"),
        ("tw_max_iterations", "TetWild Max Iter", "int", "auto"),
        ("mmg_hmin", "MMG hmin", "float", "auto"),
        ("mmg_hmax", "MMG hmax", "float", "auto"),
        ("mmg_hgrad", "MMG hgrad", "float", "1.3"),
        ("mmg_hausd", "MMG hausd", "float", "0.01"),
        ("cf_surface_feature_angle", "CF Surface Feature Angle", "float", "30.0"),
        ("feature_angle", "Polyhedral FeatureAngle", "float", "5.0"),
        ("concave_multi_cells", "Polyhedral ConcaveCells", "bool", "true"),
        ("voro_n_seeds", "Voro N Seeds", "int", "2000"),
        ("hohq_dx", "HOHQMesh Grid Spacing", "float", "auto"),
        ("hohq_n_cells", "HOHQMesh N Cells/Dir", "int", "0"),
        ("hohq_poly_order", "HOHQMesh Poly Order", "int", "1"),
        ("hohq_extrusion_dir", "HOHQMesh Extrusion Dir", "int", "3"),
        ("gmsh_hex_char_length_factor", "GMSH Char Length Factor", "float", "1.0"),
        ("gmsh_hex_algorithm", "GMSH Hex Algorithm", "int", "8"),
        ("gmsh_hex_recombine_all", "GMSH Recombine All", "bool", "true"),
        ("algohex_pipeline", "AlgoHex Pipeline", "str", "hexme"),
        ("algohex_tet_size", "AlgoHex Tet Size", "float", "0.05"),
        ("robust_hex_n_cells", "RobustHex N Cells", "int", "auto"),
        ("robust_hex_hausdorff", "RobustHex Hausdorff Ratio", "float", "auto"),
        ("robust_hex_slim_iter", "RobustHex SLIM Iter", "int", "auto"),
        ("robust_hex_timeout", "RobustHex Timeout (s)", "int", "auto"),
        ("mmg3d_hmax", "MMG3D hmax", "float", "auto"),
        ("mmg3d_hmin", "MMG3D hmin", "float", "auto"),
        ("mmg3d_hausd", "MMG3D hausd", "float", "0.01"),
        ("mmg3d_ar", "MMG3D Feature Angle", "float", "60.0"),
        ("mmg3d_optim", "MMG3D Optim", "bool", "false"),
        ("wildmesh_epsilon", "WildMesh Epsilon", "float", "auto"),
        ("wildmesh_edge_length_r", "WildMesh Edge Length Ratio", "float", "auto"),
        ("wildmesh_stop_quality", "WildMesh Stop Quality", "float", "auto"),
        ("wildmesh_max_its", "WildMesh Max Iter", "int", "auto"),
        ("classy_cell_size", "Classy Cell Size", "float", "auto"),
        ("hex_classy_use_snappy", "HexClassy Use Snappy", "bool", "true"),
        ("cinolib_hex_scale", "Cinolib Hex Scale", "float", "1.0"),
        ("voro_relax_iters", "Voro Relax Iters", "int", "10"),
        ("bl_num_layers", "BL Num Layers", "int", "3"),
        ("bl_first_thickness", "BL First Layer Thickness", "float", "0.001"),
        ("bl_growth_ratio", "BL Growth Ratio", "float", "1.2"),
        ("bl_feature_angle", "BL Feature Angle", "float", "130.0"),
        ("domain_min_x", "Domain Min X", "float", "-1.0"),
        ("domain_min_y", "Domain Min Y", "float", "-1.0"),
        ("domain_min_z", "Domain Min Z", "float", "-1.0"),
        ("domain_max_x", "Domain Max X", "float", "1.0"),
        ("domain_max_y", "Domain Max Y", "float", "1.0"),
        ("domain_max_z", "Domain Max Z", "float", "1.0"),
        ("domain_base_cell_size", "Domain Base Cell Size", "float", "0.1"),
    )

    _TIER_PARAM_SCOPE: dict[str, set[str]] = {
        "snappy_snap_tolerance": {"snappy"}, "snappy_snap_iterations": {"snappy"},
        "snappy_castellated_level": {"snappy"},
        "snappy_max_local_cells": {"snappy"}, "snappy_max_global_cells": {"snappy"},
        "snappy_min_refinement_cells": {"snappy"}, "snappy_n_cells_between_levels": {"snappy"},
        "snappy_snap_smooth_patch": {"snappy"}, "snappy_snap_relax_iter": {"snappy"},
        "snappy_feature_snap_iter": {"snappy"},
        "tetwild_epsilon": {"tetwild"}, "tetwild_stop_energy": {"tetwild"},
        "tetwild_edge_length": {"tetwild"}, "tetwild_edge_length_fac": {"tetwild"},
        "tw_max_iterations": {"tetwild"},
        "cfmesh_max_cell_size": {"cfmesh"}, "cfmesh_surface_refinement": {"cfmesh"},
        "cfmesh_local_refinement": {"cfmesh"}, "cf_surface_feature_angle": {"cfmesh"},
        "core_quality": {"core"}, "core_max_vertices": {"core"},
        "netgen_grading": {"netgen"}, "netgen_curvaturesafety": {"netgen"},
        "netgen_segmentsperedge": {"netgen"}, "netgen_closeedgefac": {"netgen"},
        "ng_max_h": {"netgen"}, "ng_min_h": {"netgen"},
        "ng_fineness": {"netgen"}, "ng_second_order": {"netgen"},
        "meshpy_min_angle": {"core", "jigsaw", "meshpy", "2d"},
        "meshpy_max_volume": {"core", "jigsaw", "meshpy", "2d"},
        "meshpy_max_area_2d": {"core", "jigsaw", "meshpy", "2d"},
        "jigsaw_hmax": {"jigsaw"}, "jigsaw_hmin": {"jigsaw"},
        "jigsaw_optm_iter": {"jigsaw"},
        "feature_angle": {"polyhedral"}, "concave_multi_cells": {"polyhedral"},
        "voro_n_seeds": {"voro_poly"},
        "hohq_dx": {"hohqmesh"}, "hohq_n_cells": {"hohqmesh"},
        "hohq_poly_order": {"hohqmesh"}, "hohq_extrusion_dir": {"hohqmesh"},
        "gmsh_hex_char_length_factor": {"gmsh_hex"}, "gmsh_hex_algorithm": {"gmsh_hex"},
        "gmsh_hex_recombine_all": {"gmsh_hex"},
        "robust_hex_n_cells": {"robust_hex"}, "robust_hex_hausdorff": {"robust_hex"},
        "robust_hex_slim_iter": {"robust_hex"}, "robust_hex_timeout": {"robust_hex"},
        "algohex_pipeline": {"algohex"}, "algohex_tet_size": {"algohex"},
        "mmg3d_hausd": {"mmg3d"}, "mmg3d_hmax": {"mmg3d"}, "mmg3d_hmin": {"mmg3d"},
        "mmg3d_ar": {"mmg3d"}, "mmg3d_optim": {"mmg3d"},
        "wildmesh_epsilon": {"wildmesh"}, "wildmesh_edge_length_r": {"wildmesh"},
        "wildmesh_stop_quality": {"wildmesh"}, "wildmesh_max_its": {"wildmesh"},
        "classy_cell_size": {"classy_blocks", "hex_classy"},
        "hex_classy_use_snappy": {"hex_classy"},
        "cinolib_hex_scale": {"cinolib_hex"}, "voro_relax_iters": {"voro_poly"},
    }
    _REMESH_PARAM_SCOPE: dict[str, set[str]] = {
        "mmg_hmin": {"mmg"}, "mmg_hmax": {"mmg"},
        "mmg_hgrad": {"mmg"}, "mmg_hausd": {"mmg"},
    }

    _QUALITY_DESC: dict[str, str] = {
        "draft": "~50k cells · TetWild / Netgen · fast tet · 약 30초",
        "standard": "~500k cells · snappyHexMesh 권장 · 약 3–5분",
        "fine": "~2M cells · snappy + BL · 약 30분+",
    }

    # 기본 엔진 리스트 (카테고리별)
    ENGINE_GROUPS: list[tuple[str, list[tuple[str, str, str]]]] = [
        # (group_label, [(value, display, status: ok/off/warn)])
        ("자동", [("auto", "Auto (best available tier)", "ok")]),
        ("Hex-dominant", [
            ("snappy", "SnappyHexMesh · CFD", "ok"),
            ("cfmesh", "cfMesh", "ok"),
            ("algohex", "AlgoHex (Frame Field)", "ok"),
            ("robust_hex", "Robust Pure Hex (Octree)", "ok"),
            ("hex_classy", "HexClassyBlocks", "ok"),
            ("cinolib_hex", "Cinolib Hex", "ok"),
            ("gmsh_hex", "GMSH Hex", "ok"),
            ("hohqmesh", "HOHQMesh", "ok"),
        ]),
        ("Tetrahedral", [
            ("netgen", "Netgen", "ok"),
            ("mmg3d", "MMG3D", "ok"),
            ("tetwild", "TetWild", "ok"),
            ("wildmesh", "WildMesh", "ok"),
            ("meshpy", "MeshPy (TetGen)", "ok"),
            ("jigsaw", "JIGSAW", "ok"),
            ("core", "Geogram CDT", "ok"),
        ]),
        ("Polyhedral", [
            ("voro_poly", "Voronoi Polyhedral", "ok"),
            ("polyhedral", "polyDualMesh (OpenFOAM)", "ok"),
        ]),
    ]

    def __init__(self) -> None:
        # ── 상태 ─────────────────────────────────────────
        self._input_path: Path | None = None
        self._output_dir: Path | None = None
        self._quality_level: QualityLevel = QualityLevel.DRAFT
        self._worker: object | None = None
        self._preview_loader: object | None = None
        self._stopping: bool = False
        self._pipeline_result: object | None = None  # None = 미완료, 완료 시 PipelineResult
        self._quality_last_updated: str | None = None  # Quality 탭 마지막 갱신 시각
        self._histogram_data: dict | None = None  # mesh_stats_computed에서 수신한 히스토그램 배열 캐시

        # ── 위젯 참조 (_build 전에는 None/empty) ───────────
        self._qmain: object | None = None
        self._titlebar_strip: object | None = None
        self._design_statusbar: object | None = None
        self._right_column: object | None = None
        self._tier_pipeline: object | None = None
        self._pipeline_legend: object | None = None
        self._viewport_overlays: object | None = None
        self._viewport_chrome: object | None = None
        self._mesh_viewer: object | None = None

        # ── 사이드바 위젯 ──────────────────────────────────
        self._drop_label: object | None = None  # DropZone
        self._engine_combo: object | None = None
        self._tier_combo: object | None = None
        self._quality_seg_btns: dict[str, object] = {}
        self._quality_desc_label: object | None = None
        self._output_path_edit: object | None = None
        self._output_path_label: object | None = None
        self._input_edit: object | None = None
        self._output_edit: object | None = None
        self._surface_element_size_edit: object | None = None
        self._surface_min_size_edit: object | None = None
        self._surface_feature_angle_edit: object | None = None

        # 공통 전처리 체크박스
        self._no_repair_check: object | None = None
        self._surface_remesh_check: object | None = None
        self._allow_ai_fallback_check: object | None = None
        self._remesh_engine_combo: object | None = None

        # 실행 버튼
        self._run_btn: object | None = None
        self._stop_btn: object | None = None

        # ── 호환용 (pipeline/log/kpi) ─────────────────────
        self._log_edit: object | None = None
        self._mesh_type_cards: dict[str, object] = {}
        self._pipeline_step_labels: list[object] = []
        self._kpi_labels: dict[str, object] = {}
        self._main_tab_widget: object | None = None
        self._progress_bar: object | None = None
        self._status_label: object | None = None
        self._status_progress: object | None = None
        self._status_stage_labels: list[object] = []
        self._report_widget: object | None = None
        self._report_placeholder: object | None = None
        self._report_content: object | None = None
        self._active_tier_label: object | None = None
        self._mesh_stats_overlay: object | None = None
        self._open_output_btn: object | None = None
        self._mesh_type_group: object | None = None
        self._iter_spin: object | None = None
        self._dry_run_check: object | None = None
        self._quality_combo: object | None = None
        self._help_title_label: object | None = None
        self._help_text_view: object | None = None
        self._adv_content: object | None = None
        self._adv_toggle_btn: object | None = None
        # tier param edits (placeholder)
        self._tier_param_edits: dict[str, object] = {}
        self._param_widgets: dict[str, list[object]] = {}
        # 개별 파라미터 필드 ref
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
        self._extra_params_edit: object | None = None

    # ═════════════════════════════════════════════════════════════════════
    # Public API
    # ═════════════════════════════════════════════════════════════════════

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
        # UI 업데이트 (안전하게 None 체크)
        self._sync_input_to_ui(resolved)

    def get_input_path(self) -> Path | None:
        return self._input_path

    def set_output_dir(self, path: str | Path) -> None:
        self._output_dir = Path(path).expanduser()
        if self._output_path_edit is not None:
            try:
                self._output_path_edit.setText(str(self._output_dir))  # type: ignore[union-attr]
            except Exception:
                pass
        if self._output_path_label is not None:
            try:
                self._output_path_label.setText(f"Output: {self._output_dir}")  # type: ignore[union-attr]
            except Exception:
                pass

    def get_output_dir(self) -> Path | None:
        return self._output_dir

    def set_quality_level(self, level: QualityLevel | str) -> None:
        self._quality_level = QualityLevel(level)
        self._refresh_quality_seg_btns()
        if self._quality_desc_label is not None:
            try:
                self._quality_desc_label.setText(  # type: ignore[union-attr]
                    self._QUALITY_DESC.get(self._quality_level.value, "")
                )
            except Exception:
                pass

    def get_quality_level(self) -> QualityLevel:
        return self._quality_level

    def update_kpi(self, **values: str) -> None:
        """KPI 셀 갱신. key=cells/points/faces/quality 등."""
        rc = self._right_column
        if rc is None:
            return
        try:
            job = rc.job_pane  # type: ignore[union-attr]
            mapping = {
                "elapsed": job.kpi_elapsed, "cells": job.kpi_cells,
                "hex": job.kpi_hex, "ram": job.kpi_ram,
            }
            for k, v in values.items():
                if k in mapping:
                    mapping[k].set_value(v)
        except Exception:
            pass

    def update_pipeline_step(self, index: int, status: str) -> None:
        """Tier pipeline 상태 갱신."""
        if self._tier_pipeline is not None:
            try:
                self._tier_pipeline.set_status(index, status)  # type: ignore[union-attr]
            except Exception:
                pass

    def show(self) -> None:  # pragma: no cover
        if not hasattr(self, "_qmain") or self._qmain is None:
            self._build()
        self._qmain.move(80, 80)  # type: ignore[union-attr]
        self._qmain.showNormal()  # type: ignore[union-attr]
        self._qmain.show()  # type: ignore[union-attr]

    # ═════════════════════════════════════════════════════════════════════
    # 비즈니스 헬퍼 (기존 API 보존 — 테스트 요구)
    # ═════════════════════════════════════════════════════════════════════

    def _tier_combo_text(self) -> str:
        if self._engine_combo is None:
            return "auto"
        try:
            data = self._engine_combo.currentData()  # type: ignore[union-attr]
            if data:
                return str(data)
            txt = self._engine_combo.currentText()  # type: ignore[union-attr]
            return txt.split(" ")[0].lower() if txt else "auto"
        except Exception:
            return "auto"

    def _remesh_engine_text(self) -> str:
        if self._remesh_engine_combo is None:
            return "auto"
        try:
            return self._remesh_engine_combo.currentText().lower()  # type: ignore[union-attr]
        except Exception:
            return "auto"

    def _param_is_applicable(
        self, param: str, tier: str, remesh_engine: str
    ) -> bool:
        """파라미터가 현재 선택된 엔진 조합에 적용 가능한지."""
        if param in self._TIER_PARAM_SCOPE:
            allowed = self._TIER_PARAM_SCOPE[param]
            if tier == "auto":
                return True
            return tier in allowed
        if param in self._REMESH_PARAM_SCOPE:
            allowed = self._REMESH_PARAM_SCOPE[param]
            if remesh_engine == "auto":
                return True
            return remesh_engine in allowed
        return True

    def _refresh_quality_seg_btns(self) -> None:
        """품질 레벨 세그먼트 버튼 활성 상태 갱신."""
        for lvl, btn in self._quality_seg_btns.items():
            active = (lvl == self._quality_level.value)
            try:
                btn.setProperty("active", active)  # type: ignore[union-attr]
                btn.style().unpolish(btn)  # type: ignore[union-attr]
                btn.style().polish(btn)  # type: ignore[union-attr]
            except Exception:
                pass

    # ═════════════════════════════════════════════════════════════════════
    # UI 빌더
    # ═════════════════════════════════════════════════════════════════════

    def _build(self) -> None:  # pragma: no cover
        from PySide6.QtCore import Qt
        from PySide6.QtGui import QAction
        from PySide6.QtWidgets import (
            QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QFrame, QLabel,
            QScrollArea, QStackedLayout,
        )
        try:
            from core.version import APP_VERSION
        except Exception:
            APP_VERSION = "0.3.5"

        # ── 최상위 윈도우 ───────────────────────────────────
        self._qmain = QMainWindow()
        self._qmain.setWindowTitle("AutoTessell")
        self._qmain.resize(1440, 920)
        self._qmain.setStyleSheet(GLOBAL_STYLE)

        # ── 메뉴바 ─────────────────────────────────────────
        self._build_menubar(QAction, APP_VERSION)

        # ── central widget + root vbox ──────────────────────
        central = QWidget()
        self._qmain.setCentralWidget(central)
        root = QVBoxLayout(central)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # ── Titlebar (데코레이션, 시스템 크롬 유지) ──────────
        from desktop.qt_app.widgets.titlebar_strip import TitlebarStrip
        self._titlebar_strip = TitlebarStrip()
        root.addWidget(self._titlebar_strip)

        # ── Body (3 column) ─────────────────────────────────
        body = QWidget()
        body.setStyleSheet(f"background: {PALETTE['bg_0']};")
        body_layout = QHBoxLayout(body)
        body_layout.setContentsMargins(0, 0, 0, 0)
        body_layout.setSpacing(0)
        root.addWidget(body, stretch=1)

        # [L] Sidebar 280px
        sidebar = self._build_sidebar()
        body_layout.addWidget(sidebar)

        # [M] Main area (viewport + pipeline)
        main_area = self._build_main_area()
        body_layout.addWidget(main_area, stretch=1)

        # [R] Right column 340px (Job/Quality/Export)
        from desktop.qt_app.widgets.right_column import RightColumn
        self._right_column = RightColumn()
        self._log_edit = self._right_column.job_pane.log_box  # 호환용
        # _output_path_edit 은 이제 Export 탭의 path_box 를 가리킨다
        self._output_path_edit = self._right_column.export_pane.path_box
        self._output_edit = self._output_path_edit
        # 브라우즈 버튼 연결
        try:
            self._right_column.export_pane.browse_btn.clicked.connect(self._on_pick_output_dir)
            self._right_column.export_pane.save_requested.connect(self._on_export_save)
        except Exception:
            pass
        # Export 탭은 파이프라인 완료 전까지 비활성화
        try:
            self._right_column.export_pane.setEnabled(False)
        except Exception:
            pass
        # 로그 필터/검색 연결
        try:
            self._wire_log_filters()
        except Exception:
            pass
        body_layout.addWidget(self._right_column)

        # ── Statusbar 26px ──────────────────────────────────
        from desktop.qt_app.widgets.status_bar import CustomStatusBar
        self._design_statusbar = CustomStatusBar()
        self._design_statusbar.set_phase("Ready", busy=False)
        self._design_statusbar.set_cpu("0%")
        self._design_statusbar.set_gpu("0%")
        self._design_statusbar.set_io("—")
        root.addWidget(self._design_statusbar)

        # 초기 상태 동기화
        self._refresh_quality_seg_btns()
        if self._quality_desc_label is not None:
            self._quality_desc_label.setText(
                self._QUALITY_DESC.get(self._quality_level.value, "")
            )

        # 뷰포트 chrome 액션 배선 (Solid/Wire/Hybrid + Screenshot)
        self._wire_viewport_chrome()

        # 시스템 모니터 시작 (2초 주기)
        self._start_sys_monitor()

        # 의존성 로그 요약 출력
        self._log_dep_summary()

    def _build_menubar(self, QAction, APP_VERSION: str) -> None:  # pragma: no cover
        mb = self._qmain.menuBar()  # type: ignore[union-attr]

        file_menu = mb.addMenu("파일")
        act_new = QAction("새 프로젝트", self._qmain); act_new.setShortcut("Ctrl+N")
        act_open = QAction("프로젝트 열기…", self._qmain); act_open.setShortcut("Ctrl+O")
        act_save = QAction("저장", self._qmain); act_save.setShortcut("Ctrl+S")
        act_save_as = QAction("다른 이름으로 저장…", self._qmain); act_save_as.setShortcut("Shift+Ctrl+S")
        act_export = QAction("내보내기…", self._qmain); act_export.setShortcut("Ctrl+E")
        act_quit = QAction("종료", self._qmain); act_quit.setShortcut("Ctrl+Q")
        act_new.triggered.connect(self._on_new_project)
        act_open.triggered.connect(self._on_open_project)
        act_save.triggered.connect(self._on_save_project)
        act_save_as.triggered.connect(self._on_save_project)
        act_export.triggered.connect(lambda: self._switch_right_tab("Export"))
        act_quit.triggered.connect(self._qmain.close)
        for a in (act_new, act_open, None, act_save, act_save_as, act_export, None, act_quit):
            if a is None:
                file_menu.addSeparator()
            else:
                file_menu.addAction(a)

        help_menu = mb.addMenu("도움말")
        act_docs = QAction("문서 보기", self._qmain); act_docs.setShortcut("F1")
        act_shortcuts = QAction("키보드 단축키", self._qmain)
        act_release = QAction("릴리즈 노트", self._qmain)
        act_report = QAction("문제 보고…", self._qmain)
        ver_action = QAction(f"AutoTessell {APP_VERSION}", self._qmain); ver_action.setEnabled(False)
        act_docs.triggered.connect(
            lambda: self._log("[INFO] 문서: https://github.com/younglin90/AutoTessell")
        )
        act_shortcuts.triggered.connect(
            lambda: self._log(
                "[INFO] 단축키: Ctrl+N (새), Ctrl+O (열기), Ctrl+S (저장), "
                "Ctrl+E (내보내기), Ctrl+Q (종료)"
            )
        )
        for a in (act_docs, act_shortcuts, act_release, None, act_report, None, ver_action):
            if a is None:
                help_menu.addSeparator()
            else:
                help_menu.addAction(a)

    def _build_sidebar(self) -> object:  # pragma: no cover
        from PySide6.QtCore import Qt
        from PySide6.QtWidgets import (
            QCheckBox, QComboBox, QFrame, QHBoxLayout, QLabel, QLineEdit,
            QPushButton, QScrollArea, QVBoxLayout, QWidget,
        )

        scroll = QScrollArea()
        scroll.setFixedWidth(280)
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        scroll.setStyleSheet(
            f"QScrollArea {{ background: {PALETTE['bg_1']}; "
            f"border: none; border-right: 1px solid {PALETTE['line_1']}; }}"
        )
        inner = QWidget()
        inner.setStyleSheet(f"background: {PALETTE['bg_1']};")
        v = QVBoxLayout(inner)
        v.setContentsMargins(0, 0, 0, 0)
        v.setSpacing(0)
        scroll.setWidget(inner)

        # ── [A] Brand ────────────────────────────────────
        brand = QFrame()
        brand.setStyleSheet(
            f"QFrame {{ background: transparent; border: none; "
            f"border-bottom: 1px solid {PALETTE['line_1']}; }}"
        )
        brand_layout = QHBoxLayout(brand)
        brand_layout.setContentsMargins(14, 14, 14, 12)
        brand_layout.setSpacing(10)

        badge = QLabel("⬡")
        badge.setFixedSize(30, 30)
        badge.setAlignment(Qt.AlignCenter)
        badge.setStyleSheet(
            "background: qlineargradient(x1:0, y1:0, x2:1, y2:1, "
            "  stop:0 #2d6bb5, stop:1 #4ea3ff); "
            "border-radius: 7px; color: #ffffff; "
            "font-size: 15px; font-weight: 700;"
        )
        brand_layout.addWidget(badge)

        brand_text = QWidget()
        brand_text.setStyleSheet("background: transparent;")
        bt = QVBoxLayout(brand_text)
        bt.setContentsMargins(0, 0, 0, 0)
        bt.setSpacing(1)
        name_lbl = QLabel("AutoTessell")
        name_lbl.setStyleSheet(
            f"color: {PALETTE['text_0']}; font-size: 14px; font-weight: 700; "
            f"letter-spacing: 0.2px; background: transparent;"
        )
        try:
            from core.version import APP_VERSION
        except Exception:
            APP_VERSION = "0.3.5"
        sub_lbl = QLabel(f"v{APP_VERSION} · Desktop")
        sub_lbl.setStyleSheet(
            f"color: {PALETTE['text_3']}; font-size: 10px; letter-spacing: 2px; "
            f"background: transparent; text-transform: uppercase;"
        )
        bt.addWidget(name_lbl)
        bt.addWidget(sub_lbl)
        brand_layout.addWidget(brand_text, stretch=1)
        v.addWidget(brand)

        # ── 섹션들 ────────────────────────────────────────
        v.addWidget(self._build_section_input_geometry())
        v.addWidget(self._build_section_engine())
        v.addWidget(self._build_section_quality())
        v.addWidget(self._build_section_preprocess())
        v.addWidget(self._build_section_surface_mesh())
        v.addWidget(self._build_run_buttons())
        v.addStretch()
        # 출력 디렉토리는 Export 탭에서 담당 — 사이드바에서 제거 (2026-04-18)
        # _output_path_edit 은 Export 탭의 path_box 로 리디렉션된다.
        return scroll

    def _make_section_label(self, text: str) -> object:  # pragma: no cover
        """스펙의 accent-bar prefix label."""
        from PySide6.QtCore import Qt
        from PySide6.QtWidgets import QFrame, QHBoxLayout, QLabel, QWidget
        w = QWidget()
        w.setStyleSheet("background: transparent;")
        row = QHBoxLayout(w)
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(7)
        bar = QFrame()
        bar.setFixedSize(3, 11)
        bar.setStyleSheet(f"background: {PALETTE['accent']}; border-radius: 1px;")
        row.addWidget(bar, 0, Qt.AlignVCenter)
        lbl = QLabel(text.upper())
        lbl.setStyleSheet(
            f"color: {PALETTE['text_1']}; font-size: 11px; font-weight: 700; "
            f"letter-spacing: 1.96px; background: transparent;"
        )
        row.addWidget(lbl)
        row.addStretch()
        return w

    def _section_frame(self, title: str) -> tuple[object, object]:  # pragma: no cover
        """섹션 프레임 생성 — (frame, content_layout)."""
        from PySide6.QtWidgets import QFrame, QVBoxLayout
        f = QFrame()
        f.setStyleSheet(
            f"QFrame {{ background: transparent; border: none; "
            f"border-bottom: 1px solid {PALETTE['line_1']}; }}"
        )
        v = QVBoxLayout(f)
        v.setContentsMargins(14, 14, 14, 12)
        v.setSpacing(10)
        v.addWidget(self._make_section_label(title))
        return f, v

    def _build_section_input_geometry(self) -> object:  # pragma: no cover
        f, v = self._section_frame("입력 지오메트리")
        from desktop.qt_app.drop_zone import DropZone
        dz = DropZone()
        dz.setMinimumHeight(88)
        dz.setText(
            "STL · OBJ · PLY · STEP · IGES\n"
            "OFF · 3MF · MSH · VTK · LAS/LAZ\n"
            "Drop file or click to browse"
        )
        dz.file_dropped.connect(self._on_file_dropped)
        dz.clicked.connect(self._on_pick_input)
        self._drop_label = dz
        # 숨김용 input edit (호환)
        from PySide6.QtWidgets import QLineEdit
        self._input_edit = QLineEdit()
        self._input_edit.setVisible(False)
        v.addWidget(dz)
        v.addWidget(self._input_edit)
        return f

    def _build_section_engine(self) -> object:  # pragma: no cover
        from PySide6.QtCore import Qt
        from PySide6.QtGui import QStandardItem, QStandardItemModel
        from PySide6.QtWidgets import QComboBox, QFrame, QHBoxLayout, QLabel, QWidget
        f, v = self._section_frame("메시 엔진")

        combo = QComboBox()
        model = QStandardItemModel(combo)
        for group, items in self.ENGINE_GROUPS:
            header = QStandardItem(f"── {group} ──")
            header.setFlags(Qt.NoItemFlags)
            header.setForeground(_qcolor(PALETTE["text_3"]))
            model.appendRow(header)
            for value, display, status in items:
                marker = {"ok": "● 설치됨", "off": "○ 미설치", "warn": "⚠ 설정 필요"}.get(status, "")
                item = QStandardItem(f"{display}  {marker}")
                item.setData(value)
                if status == "off":
                    item.setEnabled(False)
                model.appendRow(item)
        combo.setModel(model)
        combo.setCurrentIndex(1)  # 기본 auto
        self._engine_combo = combo
        self._tier_combo = combo  # 호환
        v.addWidget(combo)

        # engine-legend — 도트 설명
        legend = QWidget()
        legend.setStyleSheet("background: transparent;")
        lrow = QHBoxLayout(legend)
        lrow.setContentsMargins(0, 4, 0, 0)
        lrow.setSpacing(12)
        for css_dot, lbl in [
            (f"background: {PALETTE['ok']}; box-shadow: 0 0 4px rgba(74,222,128,0.5);", "설치됨"),
            (f"background: transparent; border: 1px solid {PALETTE['line_3']};", "미설치"),
            (f"background: {PALETTE['warn']};", "설정 필요"),
        ]:
            item = QWidget()
            item.setStyleSheet("background: transparent;")
            r = QHBoxLayout(item); r.setContentsMargins(0, 0, 0, 0); r.setSpacing(5)
            dot = QLabel(); dot.setFixedSize(6, 6)
            dot.setStyleSheet(css_dot + " border-radius: 3px;")
            txt = QLabel(lbl); txt.setStyleSheet(
                f"color: {PALETTE['text_3']}; font-size: 10.5px; background: transparent;"
            )
            r.addWidget(dot); r.addWidget(txt)
            lrow.addWidget(item)
        lrow.addStretch()
        v.addWidget(legend)
        return f

    def _build_section_quality(self) -> object:  # pragma: no cover
        from PySide6.QtWidgets import QFrame, QHBoxLayout, QLabel, QPushButton, QWidget
        f, v = self._section_frame("품질 레벨")

        seg = QFrame()
        seg.setStyleSheet(
            f"QFrame {{ background: {PALETTE['bg_2']}; "
            f"border: 1px solid {PALETTE['line_2']}; border-radius: 6px; }}"
        )
        row = QHBoxLayout(seg)
        row.setContentsMargins(3, 3, 3, 3); row.setSpacing(2)

        def _on_click(lvl: str):
            self.set_quality_level(lvl)

        for lvl, label in [("draft", "Draft"), ("standard", "Standard"), ("fine", "Fine")]:
            btn = QPushButton(label)
            btn.setFlat(True)
            btn.setCursor(_qt_cursor_pointing())
            btn.setProperty("active", lvl == self._quality_level.value)
            btn.setStyleSheet(
                f"QPushButton {{ background: transparent; color: {PALETTE['text_2']}; "
                f"border: none; border-radius: 4px; padding: 6px 10px; "
                f"font-size: 11.5px; font-weight: 500; }}"
                f"QPushButton[active=\"true\"] {{ background: {PALETTE['bg_4']}; "
                f"color: {PALETTE['text_0']}; }}"
                f"QPushButton:hover:!pressed {{ color: {PALETTE['text_1']}; }}"
            )
            btn.clicked.connect(lambda _, L=lvl: _on_click(L))
            row.addWidget(btn, stretch=1)
            self._quality_seg_btns[lvl] = btn
        v.addWidget(seg)

        desc = QLabel(self._QUALITY_DESC.get(self._quality_level.value, ""))
        desc.setWordWrap(True)
        desc.setStyleSheet(
            f"color: {PALETTE['text_2']}; font-size: 11px; font-style: italic; "
            f"background: transparent; padding-top: 4px;"
        )
        self._quality_desc_label = desc
        v.addWidget(desc)
        return f

    def _build_section_preprocess(self) -> object:  # pragma: no cover
        from PySide6.QtWidgets import QCheckBox
        f, v = self._section_frame("전처리 (공통)")

        self._no_repair_check = QCheckBox("표면 수리 스킵 (no-repair)")
        self._surface_remesh_check = QCheckBox("강제 L2 표면 리메쉬")
        self._surface_remesh_check.setChecked(True)
        self._allow_ai_fallback_check = QCheckBox("AI 표면 재생성 허용 (L3)")
        for chk in (
            self._no_repair_check, self._surface_remesh_check, self._allow_ai_fallback_check,
        ):
            v.addWidget(chk)

        from PySide6.QtWidgets import QComboBox, QHBoxLayout, QLabel, QWidget
        rem_row = QWidget()
        rem_row.setStyleSheet("background: transparent;")
        rl = QHBoxLayout(rem_row)
        rl.setContentsMargins(0, 6, 0, 0); rl.setSpacing(8)
        rl.addWidget(QLabel("L2 엔진:"))
        cb = QComboBox()
        cb.addItems(["auto", "mmg", "quadwild"])
        self._remesh_engine_combo = cb
        rl.addWidget(cb, stretch=1)
        v.addWidget(rem_row)
        return f

    def _build_section_output_path(self) -> object:  # pragma: no cover
        from PySide6.QtWidgets import QHBoxLayout, QLineEdit, QPushButton, QWidget
        f, v = self._section_frame("출력 디렉토리")
        row = QWidget()
        row.setStyleSheet("background: transparent;")
        rl = QHBoxLayout(row); rl.setContentsMargins(0, 0, 0, 0); rl.setSpacing(6)

        edit = QLineEdit()
        edit.setPlaceholderText("출력 폴더 경로…")
        edit.setStyleSheet(
            f"QLineEdit {{ background: {PALETTE['bg_2']}; border: 1px solid {PALETTE['line_2']}; "
            f"border-radius: 5px; padding: 6px 10px; color: {PALETTE['text_1']}; "
            f"font-family: 'JetBrains Mono', monospace; font-size: 11.5px; min-height: 28px; }}"
            f"QLineEdit:focus {{ border-color: {PALETTE['accent']}; }}"
        )
        self._output_path_edit = edit
        self._output_edit = edit
        rl.addWidget(edit, stretch=1)

        btn = QPushButton("⋯")
        btn.setFixedSize(32, 32)
        btn.setStyleSheet(
            f"QPushButton {{ background: {PALETTE['bg_2']}; color: {PALETTE['text_2']}; "
            f"border: 1px solid {PALETTE['line_2']}; border-radius: 5px; font-size: 14px; }}"
            f"QPushButton:hover {{ background: {PALETTE['bg_3']}; color: {PALETTE['text_0']}; "
            f"border-color: {PALETTE['line_3']}; }}"
        )
        btn.clicked.connect(self._on_pick_output_dir)
        rl.addWidget(btn)
        v.addWidget(row)

        # hidden output label for compat
        from PySide6.QtWidgets import QLabel
        self._output_path_label = QLabel("")
        self._output_path_label.setVisible(False)
        v.addWidget(self._output_path_label)
        return f

    def _build_section_surface_mesh(self) -> object:  # pragma: no cover
        from PySide6.QtWidgets import QGridLayout, QLabel, QLineEdit, QWidget
        f, v = self._section_frame("Surface Mesh")

        grid_w = QWidget()
        grid_w.setStyleSheet("background: transparent;")
        g = QGridLayout(grid_w)
        g.setContentsMargins(0, 0, 0, 0)
        g.setHorizontalSpacing(10); g.setVerticalSpacing(6)

        def _lbl(t):
            l = QLabel(t)
            l.setStyleSheet(
                f"color: {PALETTE['text_1']}; font-size: 11.5px; background: transparent;"
            )
            return l

        self._surface_element_size_edit = QLineEdit()
        self._surface_element_size_edit.setPlaceholderText("auto")
        self._surface_min_size_edit = QLineEdit()
        self._surface_min_size_edit.setPlaceholderText("auto")
        self._surface_feature_angle_edit = QLineEdit("150.0")

        g.addWidget(_lbl("Element Size"), 0, 0)
        g.addWidget(self._surface_element_size_edit, 0, 1)
        g.addWidget(_lbl("Min Size"), 1, 0)
        g.addWidget(self._surface_min_size_edit, 1, 1)
        g.addWidget(_lbl("Feature Angle"), 2, 0)
        g.addWidget(self._surface_feature_angle_edit, 2, 1)
        v.addWidget(grid_w)
        return f

    def _build_run_buttons(self) -> object:  # pragma: no cover
        from PySide6.QtWidgets import QFrame, QHBoxLayout, QPushButton, QWidget
        wrap = QWidget()
        wrap.setStyleSheet("background: transparent;")
        h = QHBoxLayout(wrap)
        h.setContentsMargins(14, 14, 14, 18)
        h.setSpacing(8)

        run_btn = QPushButton("▶  Run Meshing")
        run_btn.setProperty("accent", "primary")
        run_btn.setMinimumHeight(36)
        run_btn.clicked.connect(self._on_run_clicked)
        self._run_btn = run_btn
        h.addWidget(run_btn, stretch=3)

        stop_btn = QPushButton("■")
        stop_btn.setProperty("accent", "danger")
        stop_btn.setMinimumHeight(36)
        stop_btn.setFixedWidth(44)
        stop_btn.clicked.connect(self._on_stop_clicked)
        self._stop_btn = stop_btn
        h.addWidget(stop_btn)
        return wrap

    def _build_main_area(self) -> object:  # pragma: no cover
        from PySide6.QtWidgets import (
            QFrame, QLabel, QStackedLayout, QVBoxLayout, QWidget,
        )

        root = QWidget()
        root.setStyleSheet(f"background: {PALETTE['bg_0']};")
        v = QVBoxLayout(root)
        v.setContentsMargins(0, 0, 0, 0)
        v.setSpacing(0)

        # 뷰포트 stack (viewer + overlays + chrome)
        viewport_stack = QWidget()
        viewport_stack.setStyleSheet(
            "background: qradialgradient(cx:0.5, cy:0.45, radius:0.6, "
            "  stop:0 #171d27, stop:0.6 #0c1016, stop:1 #060809);"
        )
        stack_layout = QStackedLayout(viewport_stack)
        stack_layout.setStackingMode(QStackedLayout.StackAll)
        stack_layout.setContentsMargins(0, 0, 0, 0)

        try:
            from desktop.qt_app.mesh_viewer import MeshViewerWidget
            self._mesh_viewer = MeshViewerWidget()
            # 메시 품질 통계 Signal 연결
            try:
                self._mesh_viewer.mesh_stats_computed.connect(self._on_mesh_stats_computed)
            except Exception:
                pass
            stack_layout.addWidget(self._mesh_viewer)
        except Exception:
            fallback = QFrame()
            fallback.setStyleSheet("background: transparent;")
            fl = QVBoxLayout(fallback)
            lbl = QLabel("Drop a geometry file to preview")
            from PySide6.QtCore import Qt
            lbl.setAlignment(Qt.AlignCenter)
            lbl.setStyleSheet(
                f"color: {PALETTE['text_3']}; font-size: 14px; background: transparent;"
            )
            fl.addWidget(lbl)
            stack_layout.addWidget(fallback)

        from desktop.qt_app.widgets.viewport_overlays import ViewportOverlayContainer
        self._viewport_overlays = ViewportOverlayContainer()
        stack_layout.addWidget(self._viewport_overlays)

        from desktop.qt_app.widgets.viewport_chrome import ViewportChromeOverlay
        self._viewport_chrome = ViewportChromeOverlay()
        self._viewport_chrome.set_crumbs(["Viewport", "No file"])
        stack_layout.addWidget(self._viewport_chrome)

        v.addWidget(viewport_stack, stretch=1)

        # Pipeline strip + Legend
        from desktop.qt_app.widgets.tier_pipeline import TierPipelineStrip
        from desktop.qt_app.widgets.pipeline_legend import PipelineLegendStrip
        self._tier_pipeline = TierPipelineStrip()
        self._tier_pipeline.set_tiers([
            ("Tier 0 · Preprocess", "pymeshfix"),
            ("Tier 1 · Surface", "geogram CDT"),
            ("Tier 2 · Remesh", "MMG surface"),
            ("Tier 3 · Volume", "(selected)"),
            ("Tier 4 · Layers", "boundary layer"),
            ("Tier 5 · Validate", "checkMesh"),
        ])
        self._tier_pipeline.rerun_requested.connect(self._on_run_clicked)
        self._tier_pipeline.stop_requested.connect(self._on_stop_clicked)
        self._tier_pipeline.resume_requested.connect(self._on_resume_clicked)
        self._tier_pipeline.tier_clicked.connect(self._on_tier_node_clicked)
        v.addWidget(self._tier_pipeline)

        self._pipeline_legend = PipelineLegendStrip()
        v.addWidget(self._pipeline_legend)
        return root

    # ═════════════════════════════════════════════════════════════════════
    # 이벤트 핸들러
    # ═════════════════════════════════════════════════════════════════════

    def _sync_input_to_ui(self, resolved: Path) -> None:  # pragma: no cover
        if self._input_edit is not None:
            try:
                self._input_edit.setText(str(resolved))  # type: ignore[union-attr]
            except Exception:
                pass
        if self._titlebar_strip is not None:
            try:
                self._titlebar_strip.set_title(  # type: ignore[union-attr]
                    "AutoTessell", subtitle=resolved.name,
                    path=str(resolved.parent),
                )
            except Exception:
                pass
        if self._viewport_chrome is not None:
            try:
                parts = [resolved.parent.name or "Viewport", resolved.name]
                self._viewport_chrome.set_crumbs(parts)  # type: ignore[union-attr]
            except Exception:
                pass
        if self._right_column is not None:
            try:
                size_kb = resolved.stat().st_size // 1024
                size_txt = (
                    f"{size_kb / 1024:.1f} MB" if size_kb > 1024 else f"{size_kb} KB"
                )
                self._right_column.job_pane.status_card.set_state(  # type: ignore[union-attr]
                    badge="Ready", badge_level="info",
                    job_id=resolved.stem[:8], filename=resolved.name,
                    subtitle=f"{resolved.suffix.upper().lstrip('.')} · {size_txt}",
                )
            except Exception:
                pass
        if self._output_path_edit is not None and self._output_dir is not None:
            try:
                self._output_path_edit.setText(str(self._output_dir))  # type: ignore[union-attr]
            except Exception:
                pass
        if self._drop_label is not None:
            try:
                size_kb = resolved.stat().st_size // 1024
                size_txt = (
                    f"{size_kb / 1024:.1f} MB" if size_kb > 1024 else f"{size_kb} KB"
                )
                self._drop_label.setText(  # type: ignore[union-attr]
                    f"{resolved.name}\n{resolved.suffix.upper().lstrip('.')} · {size_txt}"
                )
            except Exception:
                pass

    def _on_file_dropped(self, path: str) -> None:  # pragma: no cover
        try:
            self.set_input_path(path)
        except Exception as e:
            try:
                self._log(f"[ERR] {e}")
            except Exception:
                pass

    def _on_pick_input(self) -> None:  # pragma: no cover
        if self._qmain is None:
            return
        from PySide6.QtWidgets import QFileDialog
        patterns = ["*" + e for e in self.SUPPORTED_EXTENSIONS]
        filter_str = f"Geometry files ({' '.join(patterns)});;All files (*)"
        path, _ = QFileDialog.getOpenFileName(
            self._qmain, "입력 파일 선택", "", filter_str
        )
        if path:
            try:
                self.set_input_path(path)
            except Exception as e:
                self._log(f"[ERR] {e}")

    def _on_pick_output_dir(self) -> None:  # pragma: no cover
        if self._qmain is None:
            return
        from PySide6.QtWidgets import QFileDialog
        cur = str(self._output_dir) if self._output_dir else str(Path.home())
        path = QFileDialog.getExistingDirectory(self._qmain, "출력 폴더 선택", cur)
        if path:
            self.set_output_dir(path)

    def _on_run_clicked(self) -> None:  # pragma: no cover
        if self._input_path is None:
            self._log("[WARN] 입력 파일이 없습니다 — 먼저 파일을 드롭하세요")
            return
        if self._output_dir is None:
            self._output_dir = self._input_path.parent / f"{self._input_path.stem}_case"

        # 사이드바 surface mesh 파라미터 → 워커 전달
        element_size = _parse_float(
            self._surface_element_size_edit.text()
            if self._surface_element_size_edit else ""
        )
        feature_angle = _parse_float(
            self._surface_feature_angle_edit.text()
            if self._surface_feature_angle_edit else ""
        )
        # tier_hint: engine_combo 의 itemData value
        tier_hint = self._tier_combo_text()

        # tier-specific params: feature_angle 이 있으면 BL 파라미터에 반영
        tier_params: dict[str, object] = {}
        if feature_angle is not None:
            tier_params["bl_feature_angle"] = feature_angle

        self._log(
            f"[INFO] Running pipeline — {self._input_path.name} "
            f"quality={self._quality_level.value} engine={tier_hint} "
            f"element_size={element_size or 'auto'}"
        )

        # 파이프라인 재시작 시 이전 결과/Export 비활성화
        self._pipeline_result = None
        self._quality_last_updated = None
        if self._right_column is not None:
            try:
                self._right_column.export_pane.setEnabled(False)
            except Exception:
                pass
            # Quality 탭 — "(갱신 중...)" 표시로 stale 방지
            try:
                q = self._right_column.quality_pane
                for key in ("aspect", "skew", "nonortho", "min_area", "min_vol", "neg_vols"):
                    q.set_metric(key, 0.0, "—")
                import time
                self._quality_last_updated = time.strftime("%H:%M:%S")
                if hasattr(q, "set_stale_label"):
                    q.set_stale_label("갱신 중...")
            except Exception:
                pass

        # 상태 UI 업데이트
        if self._design_statusbar is not None:
            self._design_statusbar.set_phase("Starting pipeline…", busy=True)
        if self._right_column is not None:
            try:
                import time
                job_id = f"{int(time.time()) % 100000:x}"
                self._right_column.job_pane.status_card.set_state(
                    badge="Processing", badge_level="running", job_id=job_id,
                    filename=self._input_path.name,
                    subtitle=(
                        f"{self._quality_level.value} · engine={tier_hint} · "
                        f"시작 {time.strftime('%H:%M:%S')}"
                    ),
                )
                self._pipeline_start_time = time.monotonic()
            except Exception:
                pass

        try:
            from desktop.qt_app.pipeline_worker import PipelineWorker
            self._stopping = False
            worker = PipelineWorker(
                self._input_path, self._quality_level,
                output_dir=self._output_dir,
                tier_hint=tier_hint,
                element_size=element_size,
                tier_specific_params=tier_params or None,
                no_repair=bool(self._no_repair_check.isChecked())
                    if self._no_repair_check else False,
                surface_remesh=bool(self._surface_remesh_check.isChecked())
                    if self._surface_remesh_check else True,
                allow_ai_fallback=bool(self._allow_ai_fallback_check.isChecked())
                    if self._allow_ai_fallback_check else False,
                remesh_engine=self._remesh_engine_text(),
            )
            worker.progress.connect(self._on_progress_line)
            if hasattr(worker, "progress_percent"):
                try:
                    worker.progress_percent.connect(self._on_progress_percent)
                except Exception:
                    pass
            if hasattr(worker, "quality_update"):
                try:
                    worker.quality_update.connect(self._on_quality_update)
                except Exception:
                    pass
            worker.finished.connect(self._on_pipeline_finished)
            worker.start()
            self._worker = worker
        except Exception as e:
            self._log(f"[ERR] 파이프라인 실행 실패: {e}")
            if self._design_statusbar is not None:
                self._design_statusbar.set_phase("Failed", busy=False)

    def _on_tier_node_clicked(self, index: int) -> None:  # pragma: no cover
        """Tier 노드 클릭 → 해당 Tier 파라미터 팝업 표시."""
        from PySide6.QtWidgets import QDialog, QVBoxLayout, QLabel, QTextBrowser, QPushButton

        # Tier 이름/엔진 정보 (TierPipelineStrip 공개 API 경유)
        info = None
        if self._tier_pipeline is not None:
            try:
                info = self._tier_pipeline.get_node_info(index)
            except Exception:
                info = None

        if info:
            tier_name = info.get("name", f"Tier {index}")
            tier_engine = info.get("engine", "—")
            tier_status = info.get("status", "pending")
        else:
            tier_name = f"Tier {index}"
            tier_engine = "—"
            tier_status = "pending"

        # 현재 티어 파라미터 수집 (tier_specific_params + 관련 설정)
        tier_hint = self._tier_combo_text()
        param_lines = [
            f"Tier: {index}  ({tier_name})",
            f"엔진: {tier_engine}",
            f"상태: {tier_status}",
            "",
            f"현재 선택 엔진: {tier_hint}",
            f"품질 레벨: {self._quality_level.value}",
        ]

        if self._output_dir is not None:
            param_lines.append(f"출력 디렉토리: {self._output_dir}")

        # Element size
        if self._surface_element_size_edit is not None:
            txt = self._surface_element_size_edit.text()
            param_lines.append(f"Element Size: {txt or 'auto'}")

        # tier-scope 파라미터 — tier_hint에 해당하는 것 나열
        relevant_params = [
            (k, v) for k, v in self.TIER_PARAM_SPECS
            if self._param_is_applicable(k, tier_hint, self._remesh_engine_text())
        ]
        if relevant_params:
            param_lines.append("")
            param_lines.append(f"── {tier_hint.upper()} 파라미터 (기본값) ──")
            for param_key, param_label, param_type, default in relevant_params[:12]:
                param_lines.append(f"  {param_label}: {default}")

        # 팝업 다이얼로그
        dlg = QDialog(self._qmain)
        dlg.setWindowTitle(f"Tier {index} 파라미터 (읽기 전용)")
        dlg.setMinimumSize(420, 340)
        dlg.setStyleSheet(
            f"QDialog {{ background: {PALETTE['bg_2']}; color: {PALETTE['text_0']}; }}"
        )
        v = QVBoxLayout(dlg)
        v.setContentsMargins(16, 16, 16, 16)
        v.setSpacing(10)

        title_lbl = QLabel(f"Tier {index} — {tier_name}")
        title_lbl.setStyleSheet(
            f"color: {PALETTE['text_0']}; font-size: 14px; font-weight: 700;"
        )
        v.addWidget(title_lbl)
        readonly_lbl = QLabel("읽기 전용 — 파라미터는 사이드바에서 변경하세요")
        readonly_lbl.setStyleSheet(
            f"color: {PALETTE['text_3']}; font-size: 11px; font-style: italic;"
        )
        v.addWidget(readonly_lbl)

        content = QTextBrowser()
        content.setStyleSheet(
            f"QTextBrowser {{ background: {PALETTE['bg_0']}; color: {PALETTE['text_1']}; "
            f"font-family: 'JetBrains Mono', monospace; font-size: 11px; border: none; "
            f"padding: 8px; }}"
        )
        content.setPlainText("\n".join(param_lines))
        v.addWidget(content, stretch=1)

        close_btn = QPushButton("닫기")
        close_btn.setStyleSheet(
            f"QPushButton {{ background: {PALETTE['accent']}; color: #05111e; "
            f"border: none; border-radius: 5px; padding: 8px 20px; font-weight: 600; }}"
        )
        close_btn.clicked.connect(dlg.accept)
        v.addWidget(close_btn)

        dlg.exec()

    def _on_resume_clicked(self) -> None:  # pragma: no cover
        """일시정지된 파이프라인 재개 (현재는 단순히 재실행)."""
        if self._worker is not None and getattr(self._worker, "isRunning", lambda: False)():
            self._log("[INFO] 파이프라인이 이미 실행 중입니다")
            return
        self._log("[INFO] 파이프라인 재개 — 처음부터 재실행")
        self._on_run_clicked()

    def _switch_right_tab(self, name: str) -> None:  # pragma: no cover
        if self._right_column is None:
            return
        tabs = self._right_column.tabs
        for i in range(tabs.count()):
            if tabs.tabText(i).lower() == name.lower():
                tabs.setCurrentIndex(i)
                return

    def _on_stop_clicked(self) -> None:  # pragma: no cover
        self._stopping = True
        if self._worker is not None:
            try:
                # requestInterruption()으로 cooperative shutdown — pipeline_worker가
                # InterruptedError를 raise하고 finished Signal을 emit한다.
                # terminate()는 서브프로세스/파일핸들 미정리 위험이 있어 사용하지 않는다.
                self._worker.requestInterruption()  # type: ignore[union-attr]
            except Exception:
                pass
        if self._design_statusbar is not None:
            self._design_statusbar.set_phase("Stopped", busy=False)
        self._log("[INFO] 파이프라인 중단")

    def _on_pipeline_finished(self, result: object) -> None:  # pragma: no cover
        if self._stopping:
            # 중단 후 UI를 대기 상태로 복원
            self._stopping = False
            if self._design_statusbar is not None:
                self._design_statusbar.set_phase("Stopped", busy=False)
            # 실행 중이던 tier 노드를 skipped로 전환 (남아 있는 active 상태 정리)
            if self._tier_pipeline is not None:
                try:
                    self._tier_pipeline.reset_active_to("skipped")
                except Exception:
                    pass
            # JobPane 상태 배지
            if self._right_column is not None:
                try:
                    self._right_column.job_pane.status_card.set_state(
                        badge="Cancelled", badge_level="warn",
                    )
                except Exception:
                    pass
            return
        self._pipeline_result = result
        success = bool(getattr(result, "success", False))
        if success:
            self._log("[OK] 파이프라인 완료")
            # Export 탭 활성화 — 메시가 생성된 이후에만 사용 가능
            if self._right_column is not None:
                try:
                    self._right_column.export_pane.setEnabled(True)
                except Exception:
                    pass
            # Tier pipeline 모든 노드 done 처리
            if self._tier_pipeline is not None:
                for i in range(6):
                    self._tier_pipeline.set_status(i, "done")
            if self._design_statusbar is not None:
                self._design_statusbar.set_phase("Done", busy=False)
            if self._right_column is not None:
                try:
                    self._right_column.job_pane.status_card.set_state(
                        badge="Completed", badge_level="ok",
                    )
                except Exception:
                    pass
            # Quality 탭 메트릭 갱신 시도
            self._update_quality_from_result(result)
            # Mesh viewer 에 결과 로드
            out_dir = getattr(result, "output_dir", None) or self._output_dir
            if out_dir is not None and self._mesh_viewer is not None:
                try:
                    poly = Path(out_dir) / "constant" / "polyMesh"
                    if poly.exists():
                        self._mesh_viewer.load_polymesh(out_dir)  # type: ignore[union-attr]
                except Exception:
                    pass
        else:
            err = getattr(result, "error", "unknown") if result else "interrupted"
            self._log(f"[ERR] 파이프라인 실패: {err}")
            if self._design_statusbar is not None:
                self._design_statusbar.set_phase("Failed", busy=False)
            if self._right_column is not None:
                try:
                    self._right_column.job_pane.status_card.set_state(
                        badge="Failed", badge_level="err",
                    )
                except Exception:
                    pass

    def _on_progress_line(self, line: str) -> None:  # pragma: no cover
        """워커의 progress 시그널 — 로그 + Tier pipeline 상태 추출."""
        self._log(line)
        # tier 진행 힌트: "[진행 NN%] Tier X ..." 또는 "tier_X" 키워드
        import re
        try:
            m = re.search(r"[Tt]ier\s*(\d+)", line)
            if m and self._tier_pipeline is not None:
                idx = int(m.group(1))
                if 0 <= idx < 6:
                    # 이전 단계들은 done, 현재는 active
                    for i in range(idx):
                        self._tier_pipeline.set_status(i, "done")
                    self._tier_pipeline.set_status(idx, "active")
        except Exception:
            pass

    def _on_progress_percent(self, pct: int, message: str) -> None:  # pragma: no cover
        """워커 progress_percent → 상태바 + ring progress."""
        if self._design_statusbar is not None:
            self._design_statusbar.set_phase(f"{message} ({pct}%)", busy=True)
        if self._viewport_overlays is not None:
            try:
                self._viewport_overlays.progress.set_progress(
                    pct / 100.0, label=message, eta=""
                )
            except Exception:
                pass
        # 경과 시간 KPI 갱신
        try:
            import time
            if hasattr(self, "_pipeline_start_time"):
                elapsed = time.monotonic() - self._pipeline_start_time
                mins, secs = divmod(int(elapsed), 60)
                self.update_kpi(elapsed=f"{mins:02d}:{secs:02d}")
        except Exception:
            pass

    def _on_mesh_stats_computed(self, stats: dict) -> None:  # pragma: no cover
        """MeshViewerWidget.mesh_stats_computed Signal 수신 → KPI + Quality 탭 갱신."""
        if not stats:
            return
        try:
            # KPI 셀 갱신
            n_cells = stats.get("n_cells", 0)
            if n_cells > 0:
                cells_str = f"{n_cells:,}" if n_cells < 1_000_000 else f"{n_cells / 1e6:.1f}M"
                self.update_kpi(cells=cells_str)

            hex_ratio = stats.get("hex_ratio", None)
            if hex_ratio is not None:
                self.update_kpi(hex=f"{hex_ratio * 100:.1f}%")

            # Quality 탭 — aspect/skewness
            if self._right_column is not None:
                q = self._right_column.quality_pane
                max_ar = stats.get("max_aspect_ratio")
                if max_ar is not None:
                    ratio = min(1.0, float(max_ar) / 20.0)
                    warn = float(max_ar) > 10.0
                    q.set_metric("aspect", ratio, f"{float(max_ar):.2f}", warn=warn)
                max_sk = stats.get("max_skewness")
                if max_sk is not None:
                    ratio = min(1.0, float(max_sk) / 5.0)
                    warn = float(max_sk) > 3.5
                    q.set_metric("skew", ratio, f"{float(max_sk):.2f}", warn=warn)

                # 셀 구성 바
                for cell_type, bar_name in [
                    ("hex_ratio", "Hexahedra"), ("tet_ratio", "Tetrahedra"),
                    ("prism_ratio", "Prisms"), ("poly_ratio", "Polyhedra"),
                ]:
                    ratio_val = stats.get(cell_type, 0.0)
                    n_key = cell_type.replace("_ratio", "").replace("hex", "n_hex").replace(
                        "tet", "n_tet").replace("prism", "n_prism").replace("poly", "n_poly")
                    n_val = stats.get("n_" + cell_type.replace("_ratio", ""), 0)
                    if bar_name in q.cell_comp_rows:
                        q.cell_comp_rows[bar_name].set_value(
                            float(ratio_val), f"{int(n_val):,}"
                        )
            # 히스토그램 배열 캐시 + Quality 탭 즉시 갱신 (3개 메트릭)
            hist = {}
            if "hist_aspect_ratio" in stats:
                hist["aspect_ratio"] = stats["hist_aspect_ratio"]
            if "hist_skewness" in stats:
                hist["skewness"] = stats["hist_skewness"]
            if "hist_non_orthogonality" in stats:
                hist["non_orthogonality"] = stats["hist_non_orthogonality"]
            if hist:
                self._histogram_data = hist
                # Quality 탭 인터랙티브 히스토그램 즉시 갱신
                if self._right_column is not None:
                    try:
                        self._right_column.quality_pane.histogram.update_histograms(
                            aspect_data=hist.get("aspect_ratio"),
                            skew_data=hist.get("skewness"),
                            non_ortho_data=hist.get("non_orthogonality"),
                        )
                    except Exception:
                        pass
        except Exception as e:
            self._log(f"[DBG] 메시 통계 KPI 갱신 실패: {e}")

    def _on_quality_update(self, metrics: dict) -> None:  # pragma: no cover
        """quality_update Signal 수신 → Quality 탭 실시간 갱신."""
        if self._right_column is None or not metrics:
            return
        import time
        self._quality_last_updated = time.strftime("%H:%M:%S")
        try:
            q = self._right_column.quality_pane
            if hasattr(q, "set_stale_label"):
                q.set_stale_label(f"갱신: {self._quality_last_updated}")
        except Exception:
            pass
        try:
            q = self._right_column.quality_pane

            def _set(key: str, value, max_value: float, warn_threshold=None):
                if value is None:
                    return
                try:
                    v = float(value)
                except (TypeError, ValueError):
                    return
                ratio = min(1.0, v / max_value) if max_value > 0 else 0.0
                warn = warn_threshold is not None and v > warn_threshold
                q.set_metric(key, ratio, f"{v:.2f}", warn=warn)

            _set("aspect", metrics.get("max_aspect_ratio"), 20.0, 10.0)
            _set("skew", metrics.get("max_skewness"), 5.0, 3.5)
            _set("nonortho", metrics.get("max_non_ortho"), 90.0, 65.0)
            _set("min_area", metrics.get("min_face_area"), 1.0)
            _set("min_vol", metrics.get("min_volume"), 1.0)
            neg = metrics.get("negative_volumes")
            if neg is not None:
                neg_i = int(neg)
                q.set_metric("neg_vols", 0.02 if neg_i == 0 else 1.0,
                             str(neg_i), warn=(neg_i > 0))

            # pass rows 업데이트
            pass_map = [
                ("nonortho", metrics.get("max_non_ortho")),
                ("skew", metrics.get("max_skewness")),
                ("aspect", metrics.get("max_aspect_ratio")),
            ]
            thresholds = {"nonortho": 65.0, "skew": 4.0, "aspect": 100.0}
            for key, val in pass_map:
                if val is not None and key in q.pass_rows:
                    ok = float(val) < thresholds.get(key, 1e9)
                    q.pass_rows[key].set_verdict("ok" if ok else "err",
                                                 "PASS" if ok else "FAIL")
            if neg is not None:
                neg_i = int(neg)
                if "negvol" in q.pass_rows:
                    q.pass_rows["negvol"].set_verdict(
                        "ok" if neg_i == 0 else "err",
                        "PASS" if neg_i == 0 else f"FAIL ({neg_i})"
                    )
        except Exception as e:
            self._log(f"[DBG] quality_update 처리 실패: {e}")

    def _update_quality_from_result(self, result: object) -> None:  # pragma: no cover
        """Pipeline 결과에서 checkMesh quality 메트릭 추출 → Quality 탭 반영."""
        if self._right_column is None or result is None:
            return
        try:
            q = self._right_column.quality_pane
            qr = getattr(result, "quality_report", None) or {}
            metrics = qr.get("metrics", {}) if isinstance(qr, dict) else {}

            def _set(key, value, max_value, warn_threshold=None):
                if value is None:
                    return
                ratio = min(1.0, value / max_value) if max_value > 0 else 0
                warn = warn_threshold is not None and value > warn_threshold
                q.set_metric(key, ratio, f"{value:.2f}", warn=warn)

            _set("aspect", metrics.get("max_aspect_ratio"), 20.0, 10.0)
            _set("skew", metrics.get("max_skewness"), 5.0, 3.5)
            _set("nonortho", metrics.get("max_non_ortho"), 90.0, 65.0)
            _set("min_area", metrics.get("min_face_area"), 1.0)
            _set("min_vol", metrics.get("min_volume"), 1.0)
            neg = metrics.get("negative_volumes", 0)
            q.set_metric("neg_vols", 0.02 if neg == 0 else 1.0,
                         str(neg), warn=(neg > 0))

            # pass rows
            pass_map = [
                ("nonortho", metrics.get("max_non_ortho", 0) < 65,
                    "< 65°" if metrics.get("max_non_ortho", 0) < 65 else "FAIL"),
                ("skew", metrics.get("max_skewness", 0) < 4.0,
                    "< 4.0" if metrics.get("max_skewness", 0) < 4.0 else "FAIL"),
                ("aspect", metrics.get("max_aspect_ratio", 0) < 100,
                    "< 100" if metrics.get("max_aspect_ratio", 0) < 100 else "FAIL"),
                ("negvol", neg == 0, "PASS" if neg == 0 else f"FAIL ({neg})"),
            ]
            for key, ok, label in pass_map:
                if key in q.pass_rows:
                    q.pass_rows[key].set_verdict("ok" if ok else "err",
                                                 "PASS" if ok else label)
        except Exception as e:
            self._log(f"[DBG] Quality 탭 갱신 실패: {e}")

    # ─── Export 저장 ─────────────────────────────────────────────
    def _on_export_save(self, fmt: str) -> None:  # pragma: no cover
        """Export 탭 설정을 읽어 실제 메시 저장 + 후처리 옵션 실행."""
        from PySide6.QtWidgets import QMessageBox

        # Export 탭 옵션 읽기
        opts: dict = {}
        if self._right_column is not None:
            try:
                opts = self._right_column.export_pane.get_export_options()
            except Exception:
                opts = {}

        # 출력 디렉토리 결정 (Export 탭 입력값 우선, fallback → self._output_dir)
        export_dir_str = opts.get("output_dir", "").strip()
        if export_dir_str:
            export_target_dir = Path(export_dir_str).expanduser().resolve()
        elif self._output_dir is not None:
            export_target_dir = self._output_dir.resolve()
        else:
            QMessageBox.warning(
                self._qmain, "저장 경로 없음",
                "출력 디렉토리를 먼저 지정하세요."
            )
            return

        if self._output_dir is None or not self._output_dir.exists():
            QMessageBox.warning(
                self._qmain, "결과 없음",
                "파이프라인을 먼저 실행하여 결과를 생성하세요."
            )
            return

        # 저장 버튼 비활성화
        if self._right_column is not None:
            try:
                self._right_column.export_pane.save_btn.setEnabled(False)
            except Exception:
                pass

        try:
            export_target_dir.mkdir(parents=True, exist_ok=True)
            actual_fmt = opts.get("format", fmt)
            self._log(f"[INFO] Export 시작: format={actual_fmt} → {export_target_dir}")

            # ── 포맷/엔진 호환성 사전 검증 ─────────────────────────
            if actual_fmt in ("openfoam", "OpenFOAM polyMesh"):
                poly_dir = self._output_dir / "constant" / "polyMesh"
                if not poly_dir.exists():
                    QMessageBox.warning(
                        self._qmain, "Export 불가",
                        "선택한 포맷은 OpenFOAM polyMesh이지만\n"
                        f"출력 디렉토리에 polyMesh가 없습니다:\n{poly_dir}\n\n"
                        "snappyHexMesh/cfMesh 엔진으로 실행했는지 확인하세요."
                    )
                    return

            self._export_mesh_format(actual_fmt, export_target_dir)

            # ── 후처리: checkMesh 리포트 JSON ─────────────────
            if opts.get("report_json", False):
                self._export_report_json(export_target_dir)

            # ── 후처리: 품질 히스토그램 PNG ───────────────────
            if opts.get("quality_hist", False):
                self._export_quality_histogram(export_target_dir)

            # ── 후처리: Paraview state 파일 ───────────────────
            if opts.get("paraview_state", False):
                self._export_paraview_state(export_target_dir)

            # ── 후처리: ZIP 압축 ──────────────────────────────
            if opts.get("zip_output", False):
                zip_path = self._export_zip(export_target_dir)
                self._log(f"[OK] ZIP 생성: {zip_path}")

            self._log(f"[OK] Export 완료: {export_target_dir}")
            QMessageBox.information(
                self._qmain, "Export 완료",
                f"메시가 성공적으로 저장되었습니다.\n\n경로: {export_target_dir}"
            )
        except Exception as e:
            self._log(f"[ERR] Export 실패: {e}")
            QMessageBox.critical(
                self._qmain, "Export 실패",
                f"저장 중 오류가 발생했습니다:\n{e}"
            )
        finally:
            if self._right_column is not None:
                try:
                    self._right_column.export_pane.save_btn.setEnabled(True)
                except Exception:
                    pass

    def _export_mesh_format(self, fmt: str, target_dir: Path) -> None:  # pragma: no cover
        """실제 메시 포맷 변환 + 복사."""
        import shutil

        src_polymesh = self._output_dir / "constant" / "polyMesh"

        if fmt == "openfoam":
            # polyMesh 폴더 복사
            dst = target_dir / "constant" / "polyMesh"
            if src_polymesh.exists():
                if dst.exists():
                    shutil.rmtree(dst)
                shutil.copytree(src_polymesh, dst)
                self._log(f"[OK] OpenFOAM polyMesh 복사: {dst}")
            else:
                # 결과 디렉토리 전체 복사 fallback
                for item in self._output_dir.iterdir():
                    dst_item = target_dir / item.name
                    if item.is_dir():
                        if dst_item.exists():
                            shutil.rmtree(dst_item)
                        shutil.copytree(item, dst_item)
                    else:
                        shutil.copy2(item, dst_item)
                self._log(f"[OK] 결과 디렉토리 복사 완료")
        else:
            # meshio 기반 변환
            self._export_via_meshio(fmt, target_dir)

    def _export_via_meshio(self, fmt: str, target_dir: Path) -> None:  # pragma: no cover
        """meshio를 통한 포맷 변환. 소스 파일 없으면 RuntimeError를 발생시킨다."""
        # 소스 파일 찾기 (VTU > VTK > MSH — surface-only STL은 volume mesh 대체 불가)
        src_file: Path | None = None
        for pattern in ("**/*.vtu", "**/*.vtk", "**/*.msh"):
            candidates = list(self._output_dir.glob(pattern))
            if candidates:
                src_file = max(candidates, key=lambda p: p.stat().st_mtime)
                break

        if src_file is None:
            raise RuntimeError(
                f"변환할 볼륨 메시 파일을 찾을 수 없습니다 (format={fmt}).\n"
                "파이프라인이 VTU/VTK/MSH를 생성했는지 확인하세요."
            )

        ext_map = {
            "vtu": ".vtu",
            "cgns": ".cgns",
            "nastran": ".nas",
            "fluent": ".msh",
            "gmsh": ".msh",
        }
        ext = ext_map.get(fmt, f".{fmt}")
        dst_file = target_dir / f"mesh{ext}"

        try:
            import meshio
        except ImportError:
            raise RuntimeError("meshio 미설치 — pip install meshio") from None

        mesh = meshio.read(str(src_file))
        meshio.write(str(dst_file), mesh)
        self._log(f"[OK] {fmt.upper()} 저장: {dst_file}")

    def _export_report_json(self, target_dir: Path) -> None:  # pragma: no cover
        """checkMesh 리포트를 JSON으로 복사/생성."""
        import shutil
        # 기존 JSON 리포트 찾기
        # 최상위 JSON만 검색 (재귀 glob 방지)
        for pattern in ("evaluation_report*.json", "quality_report*.json", "*.json"):
            candidates = list(self._output_dir.glob(pattern))
            if candidates:
                src = max(candidates, key=lambda p: p.stat().st_mtime)
                dst = target_dir / "quality_report.json"
                shutil.copy2(src, dst)
                self._log(f"[OK] 품질 리포트 복사: {dst}")
                return
        # 리포트 파일 없으면 기본 JSON 생성
        report = {
            "source": str(self._output_dir),
            "quality_level": self._quality_level.value,
            "note": "상세 리포트는 파이프라인 완료 후 생성됩니다.",
        }
        dst = target_dir / "quality_report.json"
        dst.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
        self._log(f"[OK] 기본 품질 리포트 생성: {dst}")

    def _export_quality_histogram(self, export_dir: Path) -> None:  # pragma: no cover
        """실제 셀 품질 분포 히스토그램 PNG 생성 (PyVista 배열 기반)."""
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt

        out_path = export_dir / "quality_histogram.png"
        hist_data = self._histogram_data or {}

        if not hist_data:
            self._log("[INFO] 히스토그램 데이터 없음 — 스칼라 게이지로 대체 출력")
            if self._right_column is None:
                return
            q = self._right_column.quality_pane
            metrics = {}
            try:
                for key, attr in [
                    ("max_aspect_ratio", "aspect"), ("max_skewness", "skew"),
                    ("max_non_ortho", "nonortho"),
                ]:
                    row = getattr(q, "_metric_rows", {}).get(attr)
                    if row:
                        label = getattr(row, "_value_label", None)
                        if label:
                            try:
                                metrics[key] = float(label.text())
                            except Exception:
                                pass
            except Exception:
                pass

            fig, ax = plt.subplots(figsize=(8, 3), facecolor="#0d1117")
            ax.set_facecolor("#0d1117")
            items = [
                ("Aspect Ratio (max)", metrics.get("max_aspect_ratio", 0), 20.0, "#4ea3ff"),
                ("Skewness (max)", metrics.get("max_skewness", 0), 5.0, "#f5b454"),
                ("Non-Ortho° (max)", metrics.get("max_non_ortho", 0), 90.0, "#9b87ff"),
            ]
            for i, (label, val, max_val, color) in enumerate(items):
                ratio = min(1.0, float(val) / max_val) if max_val > 0 else 0
                ax.barh(i, ratio, color=color, alpha=0.85, height=0.5)
                ax.text(min(ratio + 0.02, 0.95), i, f"{val:.2f}", va="center",
                        color="white", fontsize=9)
            ax.set_yticks(range(len(items)))
            ax.set_yticklabels([x[0] for x in items], color="#b6bdc9", fontsize=9)
            ax.set_xlim(0, 1.05)
            ax.set_xlabel("정규화 값 (0=최적, 1=최악)", color="#b6bdc9", fontsize=8)
            ax.tick_params(colors="#b6bdc9")
            for spine in ax.spines.values():
                spine.set_edgecolor("#323a46")
            ax.set_title("메시 품질 요약 (스칼라 게이지)", color="#e8ecf2", fontsize=11, pad=8)
            fig.tight_layout()
            fig.savefig(str(out_path), dpi=150, bbox_inches="tight",
                        facecolor="#0d1117", edgecolor="none")
            plt.close(fig)
            self._log(f"[OK] 품질 게이지 PNG 저장: {out_path}")
            return

        import numpy as np

        metrics_to_plot = []
        if "aspect_ratio" in hist_data:
            arr = np.array(hist_data["aspect_ratio"], dtype=float)
            arr = arr[np.isfinite(arr) & (arr > 0)]
            if len(arr) > 0:
                metrics_to_plot.append(("Aspect Ratio", arr, "#4ea3ff", (1.0, 20.0),
                                        "< 10 권장 (VTK 정의)"))
        if "skewness" in hist_data:
            arr = np.array(hist_data["skewness"], dtype=float)
            arr = arr[np.isfinite(arr) & (arr >= 0)]
            if len(arr) > 0:
                metrics_to_plot.append(("Skewness", arr, "#f5b454", (0.0, 1.0),
                                        "< 0.85 권장 (VTK 정의)"))
        if "non_orthogonality" in hist_data:
            arr = np.array(hist_data["non_orthogonality"], dtype=float)
            arr = arr[np.isfinite(arr) & (arr >= 0)]
            if len(arr) > 0:
                metrics_to_plot.append(("Non-orthogonality °", arr, "#ff7b54", (0.0, 90.0),
                                        "< 65° 권장 (OpenFOAM 기준)"))

        if not metrics_to_plot:
            self._log("[WARN] 히스토그램 배열이 비어 있음")
            return

        n = len(metrics_to_plot)
        fig, axes = plt.subplots(1, n, figsize=(5 * n, 4), facecolor="#0d1117")
        if n == 1:
            axes = [axes]

        for ax, (title, arr, color, xlim, note) in zip(axes, metrics_to_plot):
            ax.set_facecolor("#161a20")
            p99 = float(np.percentile(arr, 99))
            arr_clipped = arr[arr <= max(p99 * 1.1, xlim[1])]
            ax.hist(arr_clipped, bins=40, color=color, alpha=0.85, edgecolor="#0d1117",
                    linewidth=0.4)
            ax.axvline(float(np.median(arr)), color="white", linewidth=1.2,
                       linestyle="--", alpha=0.7, label=f"중앙값={np.median(arr):.2f}")
            ax.axvline(float(arr.max()), color="#ff6b6b", linewidth=1.0,
                       linestyle=":", alpha=0.8, label=f"최대={arr.max():.2f}")
            ax.set_title(title, color="#e8ecf2", fontsize=11, pad=6)
            ax.set_xlabel(f"{note}\nN={len(arr):,} 셀", color="#818a99", fontsize=8)
            ax.set_ylabel("셀 수", color="#818a99", fontsize=8)
            ax.tick_params(colors="#b6bdc9", labelsize=8)
            for spine in ax.spines.values():
                spine.set_edgecolor("#323a46")
            ax.legend(fontsize=7, facecolor="#161a20", edgecolor="#323a46",
                      labelcolor="#b6bdc9")

        fig.suptitle("메시 품질 분포 (PyVista/VTK 기준 — OpenFOAM checkMesh 정의와 다를 수 있음)",
                     color="#5a6270", fontsize=8, y=0.02)
        fig.tight_layout(rect=[0, 0.06, 1, 1])
        fig.savefig(str(out_path), dpi=150, bbox_inches="tight",
                    facecolor="#0d1117", edgecolor="none")
        plt.close(fig)
        self._log(f"[OK] 품질 히스토그램 PNG 저장: {out_path}")

    def _export_paraview_state(self, target_dir: Path) -> None:  # pragma: no cover
        """Paraview .pvsm 상태 파일 생성 (템플릿 기반)."""
        # 소스 파일 경로 탐색 + reader 타입 결정
        src_file = ""
        reader_type = "XMLUnstructuredGridReader"

        polymesh_candidate = self._output_dir / "constant" / "polyMesh"
        if polymesh_candidate.exists():
            # OpenFOAM case 디렉토리를 가리켜야 함 (polyMesh 상위)
            src_file = str(self._output_dir)
            reader_type = "OpenFOAMReader"
        else:
            for pattern in ("**/*.vtu", "**/*.vtk"):
                candidates = list(self._output_dir.glob(pattern))
                if candidates:
                    src_file = str(max(candidates, key=lambda p: p.stat().st_mtime))
                    reader_type = "XMLUnstructuredGridReader"
                    break

        pvsm_content = f"""<ParaViewState version="5.11.0">
  <ServerManagerState version="5.11.0">
    <ProxyCollection name="sources">
      <Item id="1" name="mesh" />
    </ProxyCollection>
    <Proxy group="sources" type="{reader_type}" id="1" servers="1">
      <Property name="FileName" id="1.FileName" number_of_elements="1">
        <Element index="0" value="{src_file}" />
      </Property>
    </Proxy>
    <ProxyCollection name="representations">
      <Item id="2" name="mesh_repr" />
    </ProxyCollection>
    <Proxy group="representations" type="GeometryRepresentation" id="2" servers="1">
      <Property name="Representation" id="2.Representation" number_of_elements="1">
        <Element index="0" value="Surface With Edges" />
      </Property>
    </Proxy>
  </ServerManagerState>
  <!-- AutoTessell generated ParaView state -->
  <!-- Source: {self._output_dir} -->
  <!-- Quality: {self._quality_level.value} -->
</ParaViewState>
"""
        pvsm_path = target_dir / "autotessell_view.pvsm"
        pvsm_path.write_text(pvsm_content, encoding="utf-8")
        self._log(f"[OK] ParaView state 파일: {pvsm_path}")

    def _export_zip(self, target_dir: Path) -> Path:  # pragma: no cover
        """target_dir을 zip으로 압축."""
        import zipfile
        zip_path = target_dir.parent / f"{target_dir.name}.zip"
        with zipfile.ZipFile(str(zip_path), "w", zipfile.ZIP_DEFLATED) as zf:
            for file in target_dir.rglob("*"):
                if file.is_file():
                    zf.write(file, file.relative_to(target_dir.parent))
        return zip_path

    # ─── 뷰포트 액션 ───────────────────────────────────────────────
    def _wire_viewport_chrome(self) -> None:  # pragma: no cover
        if self._viewport_chrome is None or self._mesh_viewer is None:
            return
        try:
            self._viewport_chrome.view_mode_changed.connect(self._on_view_mode_changed)
            self._viewport_chrome.screenshot_requested.connect(self._on_screenshot)
        except Exception:
            pass

    def _on_view_mode_changed(self, mode: str) -> None:  # pragma: no cover
        mv = self._mesh_viewer
        if mv is None:
            return
        try:
            if mode == "solid":
                mv.set_show_edges(False); mv.set_opacity(1.0)
            elif mode == "wire":
                mv.set_show_edges(True); mv.set_opacity(0.15)
            else:  # hybrid
                mv.set_show_edges(True); mv.set_opacity(1.0)
        except Exception:
            pass

    def _on_screenshot(self) -> None:  # pragma: no cover
        """뷰포트 스크린샷: Qt grab() (WYSIWYG) 우선, fallback → PyVista 오프스크린."""
        from PySide6.QtWidgets import QFileDialog, QMessageBox

        default_name = "autotessell_screenshot.png"
        if self._input_path is not None:
            default_name = f"{self._input_path.stem}_screenshot.png"

        path, _ = QFileDialog.getSaveFileName(
            self._qmain, "스크린샷 저장", default_name,
            "PNG (*.png);;JPEG (*.jpg *.jpeg)"
        )
        if not path:
            return

        saved = False

        # ── 1차 시도: Qt Widget grab (WYSIWYG — 화면에 보이는 그대로) ──────
        if self._mesh_viewer is not None:
            try:
                pix = self._mesh_viewer.grab()
                if pix.save(path):
                    self._log(f"[OK] 스크린샷 저장 (Qt grab): {path}")
                    saved = True
                else:
                    self._log("[DBG] Qt grab 저장 실패, PyVista 오프스크린으로 전환")
            except Exception as e:
                self._log(f"[DBG] Qt grab 실패, PyVista 오프스크린으로 전환: {e}")

        # ── 2차 시도: PyVista 오프스크린 렌더 (메시 뷰어 없을 때 fallback) ──
        if not saved and (self._output_dir is not None or self._input_path is not None):
            try:
                import pyvista as pv

                mesh_file: Path | None = None
                search_root = self._output_dir if self._output_dir and self._output_dir.exists() else None
                if search_root:
                    for pattern in ("*.vtu", "*.vtk", "*.stl"):
                        candidates = list(search_root.glob(pattern))
                        if candidates:
                            mesh_file = max(candidates, key=lambda p: p.stat().st_mtime)
                            break
                if mesh_file is None and self._input_path is not None:
                    mesh_file = self._input_path

                if mesh_file is not None and mesh_file.exists():
                    mesh = pv.read(str(mesh_file))
                    pl = pv.Plotter(off_screen=True, window_size=(1920, 1080))
                    pl.background_color = "#0d1117"
                    pl.add_mesh(
                        mesh, color="#00d9ff", show_edges=True,
                        edge_color="#ffffff", opacity=0.95, smooth_shading=True,
                    )
                    pl.add_axes(xlabel="X", ylabel="Y", zlabel="Z",
                                line_width=2, color="white")
                    pl.view_isometric()
                    pl.screenshot(path, transparent_background=False)
                    pl.close()
                    self._log(f"[OK] 스크린샷 저장 (PyVista 오프스크린): {path}")
                    saved = True
            except Exception as e:
                self._log(f"[ERR] PyVista 오프스크린 렌더 실패: {e}")

        if saved:
            QMessageBox.information(
                self._qmain, "스크린샷 저장",
                f"스크린샷이 저장되었습니다:\n{path}"
            )
        else:
            QMessageBox.warning(
                self._qmain, "스크린샷 실패",
                "스크린샷을 저장하지 못했습니다.\n메시를 먼저 로드하세요."
            )

    # ─── 로그 필터/검색 ───────────────────────────────────────────
    def _wire_log_filters(self) -> None:  # pragma: no cover
        job = self._right_column.job_pane
        self._active_log_levels: set[str] = {"ALL"}
        chips = {
            "ALL": job.chip_all, "INFO": job.chip_info,
            "WARN": job.chip_warn, "ERR": job.chip_err, "DBG": job.chip_dbg,
        }
        for level, chip in chips.items():
            chip.clicked.connect(lambda _, L=level: self._on_log_chip_toggled(L))
        job.log_search.textChanged.connect(self._on_log_search_changed)

    def _on_log_chip_toggled(self, level: str) -> None:  # pragma: no cover
        job = self._right_column.job_pane
        if level == "ALL":
            self._active_log_levels = {"ALL"}
            for lv, chip in (
                ("ALL", job.chip_all), ("INFO", job.chip_info),
                ("WARN", job.chip_warn), ("ERR", job.chip_err),
                ("DBG", job.chip_dbg),
            ):
                chip.set_active(lv == "ALL")
        else:
            self._active_log_levels.discard("ALL")
            job.chip_all.set_active(False)
            if level in self._active_log_levels:
                self._active_log_levels.discard(level)
            else:
                self._active_log_levels.add(level)
            if not self._active_log_levels:
                self._active_log_levels = {"ALL"}
                job.chip_all.set_active(True)
            for lv, chip in (
                ("INFO", job.chip_info), ("WARN", job.chip_warn),
                ("ERR", job.chip_err), ("DBG", job.chip_dbg),
            ):
                chip.set_active(lv in self._active_log_levels)
        self._refilter_log()

    def _on_log_search_changed(self, text: str) -> None:  # pragma: no cover
        self._refilter_log()

    def _refilter_log(self) -> None:  # pragma: no cover
        if self._log_edit is None or not hasattr(self, "_all_log_lines"):
            return
        job = self._right_column.job_pane
        search = (job.log_search.text() or "").strip().lower()
        levels = self._active_log_levels
        keep = []
        for raw in self._all_log_lines:
            if "ALL" not in levels:
                if not any(f"[{lv}]" in raw or f" {lv} " in raw for lv in levels):
                    continue
            if search and search not in raw.lower():
                continue
            keep.append(raw)
        self._log_edit.setPlainText("\n".join(keep))

    def _log(self, msg: str) -> None:  # pragma: no cover
        """필터링 가능한 로그 저장."""
        if not hasattr(self, "_all_log_lines"):
            self._all_log_lines: list[str] = []
        msg_str = str(msg)
        self._all_log_lines.append(msg_str)
        # 너무 길면 잘라내기
        if len(self._all_log_lines) > 5000:
            self._all_log_lines = self._all_log_lines[-3000:]
        self._refilter_log()

    # ─── 파일 메뉴 ───────────────────────────────────────────────
    def _on_new_project(self) -> None:  # pragma: no cover
        self._input_path = None
        self._output_dir = None
        self._set_quality_level(QualityLevel.DRAFT) if False else None
        if self._drop_label is not None:
            self._drop_label.setText(
                "STL · OBJ · PLY · STEP · IGES\n"
                "OFF · 3MF · MSH · VTK · LAS/LAZ\n"
                "Drop file or click to browse"
            )
        if self._tier_pipeline is not None:
            for i in range(6):
                self._tier_pipeline.set_status(i, "pending")
        if self._titlebar_strip is not None:
            self._titlebar_strip.set_title("AutoTessell", subtitle=None, path=None)
        if self._right_column is not None:
            self._right_column.job_pane.status_card.set_state(
                badge="Ready", badge_level="info", job_id="—",
                filename="No file loaded", subtitle="—",
            )
            self._right_column.job_pane.log_box.clear()
        if hasattr(self, "_all_log_lines"):
            self._all_log_lines.clear()
        self._log("[INFO] 새 프로젝트 초기화")

    def _on_save_project(self) -> None:  # pragma: no cover
        """현재 프로젝트 상태를 JSON으로 저장 (파일 다이얼로그)."""
        from PySide6.QtWidgets import QFileDialog, QMessageBox

        # 저장 경로 결정
        default_dir = str(self._output_dir) if self._output_dir else str(Path.home())
        path, _ = QFileDialog.getSaveFileName(
            self._qmain, "프로젝트 저장",
            str(Path(default_dir) / "autotessell_project.json"),
            "AutoTessell 프로젝트 (*.json);;모든 파일 (*)"
        )
        if not path:
            return

        # 전처리 옵션 수집
        no_repair = False
        surface_remesh = True
        allow_ai = False
        remesh_engine = "auto"
        element_size_text = ""
        try:
            if self._no_repair_check is not None:
                no_repair = bool(self._no_repair_check.isChecked())
            if self._surface_remesh_check is not None:
                surface_remesh = bool(self._surface_remesh_check.isChecked())
            if self._allow_ai_fallback_check is not None:
                allow_ai = bool(self._allow_ai_fallback_check.isChecked())
            remesh_engine = self._remesh_engine_text()
            if self._surface_element_size_edit is not None:
                element_size_text = self._surface_element_size_edit.text()
        except Exception:
            pass

        snapshot = {
            "version": "0.3.6",
            "input_path": str(self._input_path) if self._input_path else None,
            "output_dir": str(self._output_dir) if self._output_dir else None,
            "quality_level": self._quality_level.value,
            "engine": self._tier_combo_text(),
            "remesh_engine": remesh_engine,
            "preprocessing": {
                "no_repair": no_repair,
                "surface_remesh": surface_remesh,
                "allow_ai_fallback": allow_ai,
                "remesh_engine": remesh_engine,
                "element_size": element_size_text or None,
            },
        }

        try:
            Path(path).write_text(
                json.dumps(snapshot, indent=2, ensure_ascii=False), encoding="utf-8"
            )
            self._log(f"[OK] 프로젝트 저장: {path}")
            QMessageBox.information(
                self._qmain, "저장 완료",
                f"프로젝트가 저장되었습니다:\n{path}"
            )
        except Exception as e:
            self._log(f"[ERR] 프로젝트 저장 실패: {e}")
            QMessageBox.critical(self._qmain, "저장 실패", str(e))

    def _on_open_project(self) -> None:  # pragma: no cover
        """JSON 프로젝트 파일 열기 → UI 상태 복원."""
        from PySide6.QtWidgets import QFileDialog, QMessageBox

        path, _ = QFileDialog.getOpenFileName(
            self._qmain, "프로젝트 열기", str(Path.home()),
            "AutoTessell 프로젝트 (*.json);;모든 파일 (*)"
        )
        if not path:
            return

        try:
            data = json.loads(Path(path).read_text(encoding="utf-8"))
        except Exception as e:
            QMessageBox.critical(self._qmain, "열기 실패", f"JSON 파싱 오류:\n{e}")
            return

        try:
            # 입력 파일 경로 복원
            input_path = data.get("input_path")
            if input_path and Path(input_path).exists():
                try:
                    self.set_input_path(input_path)
                    self._log(f"[INFO] 입력 파일 복원: {input_path}")
                except Exception as e:
                    self._log(f"[WARN] 입력 파일 복원 실패: {e}")
            elif input_path:
                self._log(f"[WARN] 이전 입력 파일 없음: {input_path}")
                if self._drop_label is not None:
                    try:
                        self._drop_label.setText(
                            f"(이전 파일 없음)\n{Path(input_path).name}"
                        )
                    except Exception:
                        pass

            # 출력 디렉토리 복원
            output_dir = data.get("output_dir")
            if output_dir:
                output_dir_path = Path(output_dir)
                self._output_dir = output_dir_path
                if self._output_path_edit is not None:
                    try:
                        self._output_path_edit.setText(output_dir)
                    except Exception:
                        pass
                if not output_dir_path.exists():
                    QMessageBox.warning(
                        self._qmain, "경로 없음",
                        f"저장된 출력 경로가 현재 시스템에 없습니다:\n{output_dir}\n\n"
                        "파이프라인 실행 시 새로 생성됩니다."
                    )
                    self._log(f"[WARN] 출력 경로 없음 (복원됨): {output_dir}")
                else:
                    self._log(f"[INFO] 출력 경로 복원: {output_dir}")

            # 품질 레벨 복원
            quality = data.get("quality_level", "draft")
            try:
                self.set_quality_level(quality)
                self._log(f"[INFO] 품질 레벨 복원: {quality}")
            except Exception as e:
                self._log(f"[WARN] 품질 레벨 복원 실패: {e}")

            # 엔진 복원
            engine = data.get("engine", "auto")
            if self._engine_combo is not None:
                try:
                    for i in range(self._engine_combo.count()):
                        item_data = self._engine_combo.itemData(i)
                        if item_data == engine:
                            self._engine_combo.setCurrentIndex(i)
                            break
                    self._log(f"[INFO] 엔진 복원: {engine}")
                except Exception as e:
                    self._log(f"[WARN] 엔진 복원 실패: {e}")

            # 전처리 옵션 복원
            prep = data.get("preprocessing", {})
            if prep:
                try:
                    if self._no_repair_check is not None:
                        self._no_repair_check.setChecked(bool(prep.get("no_repair", False)))
                    if self._surface_remesh_check is not None:
                        self._surface_remesh_check.setChecked(
                            bool(prep.get("surface_remesh", True))
                        )
                    if self._allow_ai_fallback_check is not None:
                        self._allow_ai_fallback_check.setChecked(
                            bool(prep.get("allow_ai_fallback", False))
                        )
                    rem_eng = prep.get("remesh_engine", "auto")
                    if self._remesh_engine_combo is not None:
                        idx = self._remesh_engine_combo.findText(rem_eng)
                        if idx >= 0:
                            self._remesh_engine_combo.setCurrentIndex(idx)
                    elem_size = prep.get("element_size")
                    if elem_size and self._surface_element_size_edit is not None:
                        self._surface_element_size_edit.setText(str(elem_size))
                    self._log("[INFO] 전처리 옵션 복원 완료")
                except Exception as e:
                    self._log(f"[WARN] 전처리 옵션 복원 실패: {e}")

            self._log(f"[OK] 프로젝트 열기 완료: {path}")
        except Exception as e:
            QMessageBox.warning(self._qmain, "복원 오류", f"일부 설정 복원 실패:\n{e}")
            self._log(f"[ERR] 프로젝트 복원 중 오류: {e}")

    # ─── 시스템 모니터 타이머 ──────────────────────────────────────
    def _start_sys_monitor(self) -> None:  # pragma: no cover
        from PySide6.QtCore import QTimer
        self._sys_timer = QTimer(self._qmain)
        self._sys_timer.timeout.connect(self._update_sys_stats)
        self._sys_timer.start(2000)
        self._update_sys_stats()

    def _update_sys_stats(self) -> None:  # pragma: no cover
        if self._design_statusbar is None:
            return
        try:
            import psutil
            cpu = psutil.cpu_percent(interval=None)
            self._design_statusbar.set_cpu(f"{cpu:.0f}%")
            # I/O — disk read/write rate
            if not hasattr(self, "_last_io"):
                self._last_io = psutil.disk_io_counters()
                self._last_io_t = __import__("time").monotonic()
                self._design_statusbar.set_io("— MB/s")
            else:
                import time
                now = time.monotonic()
                dt = max(0.01, now - self._last_io_t)
                io = psutil.disk_io_counters()
                rb = (io.read_bytes - self._last_io.read_bytes) / dt
                wb = (io.write_bytes - self._last_io.write_bytes) / dt
                total = (rb + wb) / (1024 * 1024)
                self._design_statusbar.set_io(f"{total:.1f} MB/s")
                self._last_io = io; self._last_io_t = now
        except Exception:
            pass
        # GPU (선택적 pynvml)
        try:
            import pynvml  # type: ignore[import-not-found]
            pynvml.nvmlInit()
            h = pynvml.nvmlDeviceGetHandleByIndex(0)
            util = pynvml.nvmlDeviceGetUtilizationRates(h)
            self._design_statusbar.set_gpu(f"{util.gpu}%")
        except Exception:
            self._design_statusbar.set_gpu("—")

    def _log_dep_summary(self) -> None:  # pragma: no cover
        """시작 시 라이브러리 설치 현황 요약을 로그에 출력."""
        try:
            from core.runtime.dependency_status import get_dependency_summary
            summary = get_dependency_summary()
            self._log(f"─── 라이브러리 점검 ───")
            installed = [k for k, v in summary.items() if v]
            missing = [k for k, v in summary.items() if not v]
            self._log(f"✓ 설치됨 ({len(installed)}개): {', '.join(installed[:10])}"
                      + (f" 외 {len(installed) - 10}개" if len(installed) > 10 else ""))
            if missing:
                self._log(f"✗ 누락 ({len(missing)}개): {', '.join(missing)}")
            self._log(f"─────────────────────────────────────────")
        except Exception:
            pass


# ═════════════════════════════════════════════════════════════════════════════
# 유틸리티 함수
# ═════════════════════════════════════════════════════════════════════════════


def _qcolor(hex_str: str):  # pragma: no cover
    from PySide6.QtGui import QColor
    return QColor(hex_str)


def _qt_cursor_pointing():  # pragma: no cover
    from PySide6.QtCore import Qt
    return Qt.PointingHandCursor


def _parse_float(text: str) -> float | None:
    """빈 문자열/'auto'/비숫자는 None. 숫자는 float."""
    if not text:
        return None
    t = text.strip()
    if not t or t.lower() in ("auto", "-"):
        return None
    try:
        return float(t)
    except ValueError:
        return None
