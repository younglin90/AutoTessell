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
        act_open.triggered.connect(lambda: self._on_pick_input())
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
        v.addWidget(self._build_section_output_path())
        v.addWidget(self._build_section_surface_mesh())
        v.addWidget(self._build_run_buttons())
        v.addStretch()
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
        dz.mousePressEvent = lambda _e: self._on_pick_input()  # type: ignore[method-assign]
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
            self._log("[WARN] 입력 파일이 없습니다")
            return
        if self._output_dir is None:
            self._output_dir = self._input_path.parent / f"{self._input_path.stem}_case"
        self._log(
            f"[INFO] Running pipeline — {self._input_path.name} "
            f"(quality={self._quality_level.value})"
        )
        try:
            from desktop.qt_app.pipeline_worker import PipelineWorker
            self._stopping = False
            worker = PipelineWorker(
                self._input_path, self._quality_level,
                no_repair=bool(self._no_repair_check.isChecked())
                    if self._no_repair_check else False,
                surface_remesh=bool(self._surface_remesh_check.isChecked())
                    if self._surface_remesh_check else True,
                allow_ai_fallback=bool(self._allow_ai_fallback_check.isChecked())
                    if self._allow_ai_fallback_check else False,
                remesh_engine=self._remesh_engine_text(),
            )
            worker.progress.connect(lambda s: self._log(s))
            worker.finished.connect(lambda result: self._on_pipeline_finished(result))
            worker.start()
            self._worker = worker
            if self._design_statusbar is not None:
                self._design_statusbar.set_phase("Running…", busy=True)
        except Exception as e:
            self._log(f"[ERR] 파이프라인 실행 실패: {e}")

    def _on_stop_clicked(self) -> None:  # pragma: no cover
        self._stopping = True
        if self._worker is not None:
            try:
                self._worker.requestInterruption()  # type: ignore[union-attr]
                self._worker.terminate()  # type: ignore[union-attr]
            except Exception:
                pass
        if self._design_statusbar is not None:
            self._design_statusbar.set_phase("Stopped", busy=False)
        self._log("[INFO] 파이프라인 중단")

    def _on_pipeline_finished(self, result: object) -> None:  # pragma: no cover
        if self._stopping:
            return
        self._log(f"[INFO] 파이프라인 완료: {result}")
        if self._design_statusbar is not None:
            self._design_statusbar.set_phase("Done", busy=False)

    def _log(self, msg: str) -> None:  # pragma: no cover
        if self._log_edit is not None:
            try:
                self._log_edit.appendPlainText(str(msg))  # type: ignore[union-attr]
            except Exception:
                pass

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
