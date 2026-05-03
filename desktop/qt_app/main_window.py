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
    # GU2: 하드코딩됐던 값들을 의미있는 이름으로
    "accent_fg": "#05111e",     # accent 배경 위 텍스트 (어두운 남색)
    "err_fg": "#ff8888",        # 에러 버튼 텍스트 (밝은 붉은)
    "code_bg": "#05070a",       # 로그 박스 극흑 배경
    "dialog_bg": "#0f1318",     # 모달 다이얼로그 배경
}


# GU4: 다이얼로그 크기 표준 (width, height)
DIALOG_SMALL = (480, 360)
DIALOG_MEDIUM = (720, 520)
DIALOG_LARGE = (960, 640)


def get_dialog_qss() -> str:
    """모든 QDialog 공통 스타일시트 — PALETTE 기반."""
    return (
        f"QDialog {{ background: {PALETTE['dialog_bg']}; "
        f"color: {PALETTE['text_0']}; }}"
        f"QLabel {{ color: {PALETTE['text_1']}; background: transparent; }}"
        f"QLineEdit, QComboBox {{ background: {PALETTE['bg_2']}; "
        f"color: {PALETTE['text_0']}; border: 1px solid {PALETTE['line_2']}; "
        f"border-radius: 4px; padding: 5px 8px; }}"
        f"QPushButton {{ background: {PALETTE['bg_3']}; color: {PALETTE['text_0']}; "
        f"border: 1px solid {PALETTE['line_2']}; border-radius: 4px; "
        f"padding: 6px 12px; }}"
        f"QPushButton:hover {{ background: {PALETTE['bg_4']}; "
        f"border-color: {PALETTE['accent']}; }}"
        f"QPushButton:disabled {{ color: {PALETTE['text_3']}; "
        f"background: {PALETTE['bg_1']}; }}"
    )


def get_table_qss() -> str:
    """QTableWidget 공통 스타일시트."""
    return (
        f"QTableWidget {{ background: {PALETTE['dialog_bg']}; "
        f"color: {PALETTE['text_0']}; gridline-color: {PALETTE['line_1']}; "
        f"border: 1px solid {PALETTE['line_1']}; }}"
        f"QHeaderView::section {{ background: {PALETTE['bg_2']}; "
        f"color: {PALETTE['text_1']}; border: none; "
        f"border-right: 1px solid {PALETTE['line_1']}; "
        f"border-bottom: 1px solid {PALETTE['line_1']}; padding: 6px 8px; }}"
        f"QTableWidget::item {{ padding: 4px 6px; }}"
        f"QTableWidget::item:selected {{ background: {PALETTE['bg_3']}; "
        f"color: {PALETTE['text_0']}; }}"
    )


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
QMenu::item:selected {{ background: {PALETTE['accent']}; color: {PALETTE['accent_fg']}; }}
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
    background: {PALETTE['accent']}; border: 1px solid {PALETTE['accent']}; color: {PALETTE['accent_fg']};
    font-weight: 600;
}}
QPushButton[accent="primary"]:hover {{ background: {PALETTE['accent_hover']}; border-color: {PALETTE['accent_hover']}; }}
QPushButton[accent="danger"] {{
    background: rgba(255,60,60,0.08); border: 1px solid #5f2d2d; color: {PALETTE['err_fg']};
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
    background: {PALETTE['code_bg']}; border: none; color: {PALETTE['text_1']};
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
        # beta72 — native_bl Phase 2 config (BLConfig 신규 6 필드)
        ("bl_collision_safety", "BL Collision Safety (native)", "bool", "true"),
        ("bl_collision_safety_factor", "BL Collision Safety Factor", "float", "0.5"),
        ("bl_feature_lock", "BL Feature Lock (native)", "bool", "true"),
        ("bl_feature_angle_deg", "BL Feature Angle Deg (native)", "float", "45.0"),
        ("bl_feature_reduction_ratio", "BL Feature Reduction Ratio", "float", "0.5"),
        ("bl_quality_check_enabled", "BL Quality Check (native)", "bool", "true"),
        ("bl_aspect_ratio_threshold", "BL Aspect Ratio Threshold", "float", "50.0"),
        # beta93 — BL shrinkage iteration
        ("bl_shrink_iterations", "BL Shrink Iterations", "int", "1"),
        ("bl_shrink_factor", "BL Shrink Factor", "float", "0.7"),
        ("bl_shrink_aspect_threshold", "BL Shrink Aspect Threshold", "float", "30.0"),
        # beta83 — CFD 시뮬레이션 파라미터 (beta78 CLI 와 동기화)
        ("flow_velocity", "Flow Velocity (m/s)", "float", "1.0"),
        ("turbulence_model", "Turbulence Model", "str", "kEpsilon"),
        # beta96 — y⁺ 자동 BL 두께
        ("target_yplus", "Target y⁺", "float", "1.0"),
        ("fluid", "Fluid", "str", "air"),
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

    # v0.4 Native-First + beta104: 우리 엔진 최상단 + 외부 엔진은 "참고용"
    # 카테고리로 유지. native_tet 이 TetWild/WildMesh 수준에 도달할 때까지
    # 실제 CFD 수요가 있는 사용자가 돌아가는 엔진 선택할 수 있게 함.
    ENGINE_GROUPS: list[tuple[str, list[tuple[str, str, str]]]] = [
        # (group_label, [(value, display, status: ok/off/warn)])
        ("자동", [("auto", "Auto (strategist 가 mesh_type 기반 선택)", "ok")]),
        ("Native (v0.4)", [
            ("native_tet", "Native Tet · MVP (개선 중, TetWild-lite 포팅 예정)", "ok"),
            ("native_hex", "Native Hex · octree + snap + BL", "ok"),
            ("native_poly", "Native Poly · Voronoi + Lloyd CVT", "ok"),
        ]),
        ("Native AI (v0.5 skeleton)", [
            ("native_ai", "Native AI · mesh_type dispatch (현재 위임, AI-V1~V4 단계 통합)", "ok"),
        ]),
        # 참고용 (외부 의존). 우리 엔진 고도화 완료 시 단계적 제거 예정.
        ("참고용 · Tetrahedral", [
            ("wildmesh", "WildMesh (fTetWild, 참고용)", "ok"),
            ("tetwild", "TetWild (참고용)", "ok"),
            ("netgen", "Netgen (참고용)", "ok"),
            ("mmg3d", "MMG3D (참고용)", "ok"),
            ("meshpy", "MeshPy / TetGen (참고용)", "ok"),
            ("jigsaw", "JIGSAW (참고용)", "ok"),
            ("core", "Geogram CDT (참고용)", "ok"),
        ]),
        ("참고용 · Hex-dominant", [
            ("snappy", "snappyHexMesh (참고용)", "ok"),
            ("cfmesh", "cfMesh (참고용)", "ok"),
            ("algohex", "AlgoHex (참고용)", "ok"),
            ("robust_hex", "Robust Pure Hex octree (참고용)", "ok"),
            ("hex_classy", "HexClassyBlocks (참고용)", "ok"),
            ("cinolib_hex", "Cinolib Hex (참고용)", "ok"),
            ("gmsh_hex", "GMSH Hex (참고용)", "ok"),
            ("hohqmesh", "HOHQMesh (참고용)", "ok"),
        ]),
        ("참고용 · Polyhedral", [
            ("voro_poly", "Voronoi Polyhedral (참고용)", "ok"),
            ("polyhedral", "polyDualMesh · OpenFOAM (참고용)", "ok"),
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
        self._prefer_native_check: object | None = None
        self._prefer_native_tier_check: object | None = None  # beta29
        self._surface_remesh_check: object | None = None
        self._allow_ai_fallback_check: object | None = None
        self._remesh_engine_combo: object | None = None

        # 실행 버튼
        self._run_btn: object | None = None
        self._stop_btn: object | None = None

        # ── 호환용 (pipeline/log/kpi) ─────────────────────
        self._log_edit: object | None = None
        self._mesh_type_cards: dict[str, object] = {}
        # v0.4: 사용자가 선택한 메쉬 대분류 (auto/tet/hex_dominant/poly)
        # BETA2835 — default "auto" → "tet". auto path 의 legacy auto_select 가
        # tier2_tetwild (외부 PyPI) 우선 선택하던 문제 회피. tet 명시 시
        # _MESH_TYPE_TIER_MAP["tet"]["draft"] 의 tier_wildmesh primary 가
        # 적용되어 vendored fTetWild binding (BETA2834) 직접 사용.
        self._mesh_type: str = "tet"
        # v0.4: Evaluator FAIL 시 자동 재시도 모드 (off/once/continue)
        self._auto_retry: str = "off"
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

        # 최근 파일 / 프리셋 (v0.4)
        self._recent_menu: object | None = None
        self._preset_combo: object | None = None
        self._preset_desc_label: object | None = None

        # 엔진 정책 (wildmesh_only 모드 등)
        self._engine_policy: object | None = None

        # WildMesh 파라미터 슬라이더 패널 (tier=wildmesh 선택시 표시)
        self._wildmesh_param_panel: object | None = None
        self._wildmesh_param_frame: object | None = None
        self._param_revert_btn: object | None = None

        # polyDualMesh 파라미터 패널 (tier=polyhedral 선택 시 표시)
        self._polyhedral_param_panel: object | None = None
        self._polyhedral_param_frame: object | None = None

        # 일반 엔진 파라미터 패널 (wildmesh/polyhedral 외 나머지 엔진용 — spec-driven)
        self._generic_param_panel: object | None = None
        self._generic_param_frame: object | None = None

        # y⁺ 자동 BL 두께 패널 (beta100 배선)
        self._yplus_panel: object | None = None
        self._yplus_frame: object | None = None
        self._computed_bl_first_thickness: float | None = None

        # 품질 레벨 섹션 (WildMesh 선택 시 숨김 — 중복 UI 제거)
        self._quality_section_frame: object | None = None

        # Tier별 엔진 선택 콤보 (Tier 0/1/2/4/5 — Tier 3은 _engine_combo가 담당)
        self._tier0_engine_combo: object | None = None
        self._tier1_engine_combo: object | None = None
        self._tier2_engine_combo: object | None = None  # L2 remesh (기존 _remesh_engine_combo 미러)
        self._tier4_engine_combo: object | None = None
        self._tier5_engine_combo: object | None = None

        # Surface Mesh 섹션 중복 제거용 위젯 ref
        self._surface_size_lbl_el: object | None = None
        self._surface_size_lbl_min: object | None = None
        self._surface_size_dup_hint: object | None = None

        # 파이프라인 실행 시작 시각 (단조 시계)
        self._pipeline_start_time: float = 0.0

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
        # 최근 파일 기록 갱신
        try:
            from desktop.qt_app import recent_files

            recent_files.add(resolved)
            if hasattr(self, "_recent_menu") and self._recent_menu is not None:
                self._rebuild_recent_menu()
        except Exception:
            pass
        # 지오메트리 힌트 — 빠른 분석 + 추천 품질 + ETA
        try:
            self._show_geometry_hint(resolved)
        except Exception:
            pass

    def _show_geometry_hint(self, path: Path) -> None:  # pragma: no cover
        """드롭 즉시 지오메트리 요약을 로그/KPI/오버레이에 표시."""
        from desktop.qt_app.geometry_hint import analyze, format_hint

        hint = analyze(path)
        text = format_hint(hint)
        self._log("[INFO] 지오메트리 분석 — " + text.replace("\n", " / "))

        # y⁺ 패널의 특성 길이에 bbox 대각선 자동 주입 (beta100)
        if self._yplus_panel is not None and hint.bbox_diag > 0:
            try:
                self._yplus_panel.set_characteristic_length(float(hint.bbox_diag))  # type: ignore[union-attr]
            except Exception:
                pass

        # 뷰포트 KPI 오버레이 — 미실행 상태에서 프리뷰 정보 표시
        if self._viewport_overlays is not None and not hint.error:
            try:
                kpi = self._viewport_overlays.kpi
                kpi.set_value("Cells", f"~{hint.n_triangles:,} tri")
                kpi.set_value("Tier", f"추천: {hint.recommended_quality}", highlight=True)
                # ETA 표시
                eta = None
                if hint.recommended_quality == "draft":
                    eta = hint.eta_seconds_draft
                elif hint.recommended_quality == "standard":
                    eta = hint.eta_seconds_standard
                elif hint.recommended_quality == "fine":
                    eta = hint.eta_seconds_fine
                if eta is not None:
                    from desktop.qt_app.geometry_hint import _fmt_time
                    kpi.set_value("Time", f"ETA ~{_fmt_time(eta)}")
            except Exception:
                pass

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
        # Tier 4 Layers 라벨은 품질 레벨에 따라 변한다 — 재갱신.
        try:
            self._refresh_tier_strip_engine_labels()
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
        """품질 레벨 세그먼트 버튼 활성 상태 갱신.

        Qt style property 선택자 ``QPushButton[active="true"]`` 는 문자열 비교라
        bool 을 그대로 전달해도 인식되지 않는 케이스가 있다. 명시적으로 "true"/"false"
        문자열로 저장하고 update() 로 repaint 를 강제.
        """
        for lvl, btn in self._quality_seg_btns.items():
            active = (lvl == self._quality_level.value)
            try:
                btn.setProperty("active", "true" if active else "false")  # type: ignore[union-attr]
                style = btn.style()  # type: ignore[union-attr]
                style.unpolish(btn)
                style.polish(btn)
                btn.update()  # type: ignore[union-attr]
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

        # ── Body (3 column, QSplitter 로 사용자 조정 가능) ───
        from PySide6.QtWidgets import QSplitter
        body = QSplitter(Qt.Horizontal)
        body.setStyleSheet(
            f"QSplitter {{ background: {PALETTE['bg_0']}; }}"
            f"QSplitter::handle {{ "
            f"  background: {PALETTE['line_1']}; width: 3px; "
            f"}}"
            f"QSplitter::handle:hover {{ background: {PALETTE['accent']}; }}"
        )
        body.setChildrenCollapsible(False)
        body.setHandleWidth(3)
        root.addWidget(body, stretch=1)

        # [L] Sidebar
        sidebar = self._build_sidebar()
        body.addWidget(sidebar)

        # [M] Main area (viewport + pipeline)
        main_area = self._build_main_area()
        body.addWidget(main_area)

        # [R] Right column (Job/Quality/Export)
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
        body.addWidget(self._right_column)

        # QSplitter 초기 분할 비율 + 각 구역 stretch
        # [sidebar, main, right_column] 기본 크기 (사용자가 드래그로 조정 가능)
        # 사이드바 340 → 420 (글자 잘림 완화)
        body.setSizes([420, 820, 360])
        body.setStretchFactor(0, 0)  # sidebar: 고정 경향
        body.setStretchFactor(1, 1)  # main: 대부분 흡수
        body.setStretchFactor(2, 0)  # right: 고정 경향

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
        # Tier strip 엔진 라벨 초기화 (기본 엔진 = WildMesh 반영)
        try:
            self._refresh_tier_strip_engine_labels()
            self._refresh_wildmesh_panel_visibility()
            self._refresh_polyhedral_panel_visibility()
            self._refresh_generic_param_panel()
        except Exception:
            pass

        # 뷰포트 chrome 액션 배선 (Solid/Wire/Hybrid + Screenshot)
        self._wire_viewport_chrome()

        # 시스템 모니터 시작 (2초 주기)
        self._start_sys_monitor()

        # 의존성 로그 요약 출력
        self._log_dep_summary()

    def _on_open_batch_dialog(self) -> None:  # pragma: no cover
        """파일 → 배치 처리 메뉴 핸들러."""
        from desktop.qt_app.batch_dialog import BatchDialog

        dlg = BatchDialog(self._qmain)
        dlg.exec()
        self._rebuild_recent_menu()

    def _on_open_history_dialog(self) -> None:  # pragma: no cover
        """보기 → 실행 이력 메뉴 핸들러."""
        from desktop.qt_app.history_dialog import HistoryDialog

        dlg = HistoryDialog(self._qmain)
        dlg.exec()

    def _on_open_compare_dialog(self) -> None:  # pragma: no cover
        """도구 → 메시 비교 메뉴 핸들러."""
        from desktop.qt_app.compare_dialog import CompareDialog

        dlg = CompareDialog(self._qmain)
        dlg.exec()

    def _on_set_engine_policy(self, mode: str) -> None:  # pragma: no cover
        """엔진 정책 메뉴 → 모드 전환 + 영속 저장 + 배너 갱신."""
        from desktop.qt_app import engine_policy

        policy = engine_policy.set_mode(mode)
        self._engine_policy = policy
        self._log(f"[INFO] 엔진 정책: {mode}")
        self._rebuild_engine_combo_model()

        # 체크마크 갱신
        if hasattr(self, "_engine_policy_actions"):
            for k, act in self._engine_policy_actions.items():
                try:
                    act.setChecked(k == mode)
                except Exception:
                    pass

        # 알림
        from PySide6.QtWidgets import QMessageBox

        QMessageBox.information(
            self._qmain, "엔진 정책 변경",
            f"정책이 '{mode}'로 변경되었습니다.\n\n"
            f"새 정책은 다음 파이프라인 실행부터 적용됩니다.\n"
            f"GUI 엔진 드롭다운도 즉시 갱신되었습니다.",
        )

    def _show_shortcuts_dialog(self) -> None:  # pragma: no cover
        """키보드 단축키 전체 맵 표시."""
        from PySide6.QtWidgets import QDialog, QLabel, QVBoxLayout

        from desktop.qt_app.widgets.dialog_mixin import EscDismissMixin

        class _ShortcutDialog(EscDismissMixin, QDialog):
            pass

        d = _ShortcutDialog(self._qmain)
        d.setWindowTitle("키보드 단축키")
        d.setMinimumSize(*DIALOG_SMALL)
        d.setStyleSheet(get_dialog_qss())
        layout = QVBoxLayout(d)
        layout.setContentsMargins(20, 16, 20, 16)
        layout.setSpacing(8)

        title = QLabel("⌨  키보드 단축키")
        title.setStyleSheet("font-size: 15px; font-weight: 600; padding-bottom: 8px;")
        layout.addWidget(title)

        shortcuts = [
            ("파일", [
                ("Ctrl+N", "새 프로젝트"),
                ("Ctrl+O", "프로젝트 열기"),
                ("Ctrl+S", "저장"),
                ("Ctrl+Shift+S", "다른 이름으로 저장"),
                ("Ctrl+E", "내보내기"),
                ("Ctrl+B", "배치 처리"),
                ("Ctrl+Q", "종료"),
            ]),
            ("보기", [
                ("Ctrl+H", "실행 이력"),
                ("F1", "문서 보기"),
            ]),
            ("팁", [
                ("드래그앤드롭", "파일을 DropZone에 끌어다 놓기"),
                ("DropZone 클릭", "파일 다이얼로그 열기"),
                ("우클릭 (로그)", "로그 복사/저장/지우기"),
                ("Tier 노드 클릭", "해당 Tier 파라미터 팝업"),
            ]),
        ]

        for group, items in shortcuts:
            sec = QLabel(group)
            sec.setStyleSheet(
                "color: #4ea3ff; font-size: 12px; font-weight: 600; "
                "padding-top: 8px; padding-bottom: 2px;"
            )
            layout.addWidget(sec)
            for key, desc in items:
                row = QLabel(
                    f"<span style='font-family: JetBrains Mono; "
                    f"color: #b6bdc9;'>{key}</span> "
                    f"<span style='color: #818a99;'>&nbsp;&nbsp;{desc}</span>"
                )
                row.setStyleSheet("font-size: 12px; padding: 2px 8px;")
                layout.addWidget(row)

        layout.addStretch()
        from PySide6.QtCore import Qt as _Qt
        from PySide6.QtWidgets import QPushButton

        close_btn = QPushButton("닫기")
        close_btn.setStyleSheet(
            f"QPushButton {{ background: {PALETTE['accent']}; color: {PALETTE['accent_fg']}; "
            f"border: none; border-radius: 4px; padding: 8px 20px; "
            f"font-size: 12px; font-weight: 600; }}"
            f"QPushButton:hover {{ background: {PALETTE['accent_hover']}; }}"
        )
        close_btn.clicked.connect(d.accept)
        layout.addWidget(close_btn, alignment=_Qt.AlignRight)
        d.exec()

    def _rebuild_recent_menu(self) -> None:  # pragma: no cover
        """최근 파일 서브메뉴를 현재 저장된 경로로 재구성."""
        from PySide6.QtGui import QAction
        from desktop.qt_app import recent_files

        if not hasattr(self, "_recent_menu") or self._recent_menu is None:
            return
        self._recent_menu.clear()
        entries = recent_files.load()
        if not entries:
            act_empty = QAction("(비어 있음)", self._qmain)
            act_empty.setEnabled(False)
            self._recent_menu.addAction(act_empty)
            return
        for i, path in enumerate(entries):
            from pathlib import Path
            p = Path(path)
            label = f"&{i + 1}  {p.name}  ({p.parent})"
            act = QAction(label, self._qmain)
            act.setStatusTip(path)
            act.triggered.connect(lambda _checked=False, _p=path: self._open_recent_file(_p))
            self._recent_menu.addAction(act)
        self._recent_menu.addSeparator()
        act_clear = QAction("기록 지우기", self._qmain)
        act_clear.triggered.connect(self._clear_recent_files)
        self._recent_menu.addAction(act_clear)

    def _open_recent_file(self, path: str) -> None:  # pragma: no cover
        from pathlib import Path
        p = Path(path)
        if not p.exists():
            self._log(f"[WARN] 파일을 찾을 수 없음: {path}")
            self._rebuild_recent_menu()  # 누락 제거
            return
        self._input_path = p
        if self._drop_label is not None:
            self._drop_label.setText(f"입력 파일:\n{p.name}")
        if self._mesh_viewer is not None:
            try:
                self._mesh_viewer.load_mesh(str(p))  # type: ignore[union-attr]
            except Exception:
                pass
        self._log(f"[INFO] 최근 파일 로드: {path}")

    def _clear_recent_files(self) -> None:  # pragma: no cover
        from desktop.qt_app import recent_files
        recent_files.clear()
        self._rebuild_recent_menu()
        self._log("[INFO] 최근 파일 기록 삭제")

    def _build_menubar(self, QAction, APP_VERSION: str) -> None:  # pragma: no cover
        mb = self._qmain.menuBar()  # type: ignore[union-attr]

        file_menu = mb.addMenu("파일")
        act_new = QAction("새 프로젝트", self._qmain); act_new.setShortcut("Ctrl+N")
        act_open = QAction("프로젝트 열기…", self._qmain); act_open.setShortcut("Ctrl+O")
        act_save = QAction("저장", self._qmain); act_save.setShortcut("Ctrl+S")
        act_save_as = QAction("다른 이름으로 저장…", self._qmain); act_save_as.setShortcut("Shift+Ctrl+S")
        act_export = QAction("내보내기…", self._qmain); act_export.setShortcut("Ctrl+E")
        act_batch = QAction("배치 처리…", self._qmain); act_batch.setShortcut("Ctrl+B")
        act_quit = QAction("종료", self._qmain); act_quit.setShortcut("Ctrl+Q")
        act_new.triggered.connect(self._on_new_project)
        act_open.triggered.connect(self._on_open_project)
        act_save.triggered.connect(self._on_save_project)
        act_save_as.triggered.connect(self._on_save_project)
        act_export.triggered.connect(lambda: self._switch_right_tab("Export"))
        act_batch.triggered.connect(self._on_open_batch_dialog)
        act_quit.triggered.connect(self._qmain.close)

        # 최근 파일 서브메뉴 (동적으로 채움)
        self._recent_menu = file_menu.addMenu("최근 파일")
        self._rebuild_recent_menu()

        for a in (act_new, act_open, None, act_save, act_save_as, act_export,
                  None, act_batch, None, act_quit):
            if a is None:
                file_menu.addSeparator()
            else:
                file_menu.addAction(a)

        # ── 보기 메뉴 ────────────────────────────────────
        view_menu = mb.addMenu("보기")
        act_history = QAction("실행 이력…", self._qmain)
        act_history.setShortcut("Ctrl+H")
        act_history.triggered.connect(self._on_open_history_dialog)
        view_menu.addAction(act_history)

        # ── 도구 메뉴 ────────────────────────────────────
        tools_menu = mb.addMenu("도구")
        act_compare = QAction("메시 비교…", self._qmain)
        act_compare.setShortcut("Ctrl+D")
        act_compare.triggered.connect(self._on_open_compare_dialog)
        tools_menu.addAction(act_compare)

        # ── 엔진 정책 메뉴 ────────────────────────────────
        engine_menu = mb.addMenu("엔진 정책")
        from desktop.qt_app import engine_policy as _pol

        _current_mode = _pol.load().mode

        def _make_policy_action(mode: str, label: str) -> object:
            act = QAction(label, self._qmain)
            act.setCheckable(True)
            act.setChecked(mode == _current_mode)
            act.triggered.connect(lambda _checked=False, _m=mode: self._on_set_engine_policy(_m))
            return act

        act_all = _make_policy_action("all", "전체 엔진 허용 (기본)")
        act_wild = _make_policy_action("wildmesh_only", "WildMesh 전용")
        self._engine_policy_actions = {"all": act_all, "wildmesh_only": act_wild}
        engine_menu.addAction(act_all)
        engine_menu.addAction(act_wild)

        help_menu = mb.addMenu("도움말")
        act_docs = QAction("문서 보기", self._qmain); act_docs.setShortcut("F1")
        act_shortcuts = QAction("키보드 단축키", self._qmain)
        act_release = QAction("릴리즈 노트", self._qmain)
        act_report = QAction("문제 보고…", self._qmain)
        ver_action = QAction(f"AutoTessell {APP_VERSION}", self._qmain); ver_action.setEnabled(False)
        act_docs.triggered.connect(
            lambda: self._log("[INFO] 문서: https://github.com/younglin90/AutoTessell")
        )
        act_shortcuts.triggered.connect(self._show_shortcuts_dialog)
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
        # 사용자가 QSplitter로 드래그하여 조정 가능하도록 min/max 범위만 지정.
        # 기본값은 main_window._build() 의 body.setSizes([420, ...]) 에서 결정.
        # 글자 잘림 방지를 위해 min 너비 확대.
        scroll.setMinimumWidth(360)
        scroll.setMaximumWidth(720)
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

        # ── 섹션들 (사용자 요청 순서 — v0.4 Native-First 레이아웃) ─────────
        # 1. 입력 지오메트리
        # 2. 메쉬 타입
        # 3. 프리셋
        # 4. Tier 엔진 (Tier 3 "볼륨 메쉬" 포함 — 별도 "메시 엔진" 섹션 삭제)
        # 5. 품질 레벨
        # 6. 엔진 파라미터 (wildmesh + polyhedral + generic + surface mesh)
        # 7. 전처리
        # 8. y⁺ 자동 BL 두께
        v.addWidget(self._build_section_input_geometry())
        v.addWidget(self._build_section_mesh_type())
        v.addWidget(self._build_section_preset())
        v.addWidget(self._build_section_tier_engines())
        v.addWidget(self._build_section_quality())
        v.addWidget(self._build_section_wildmesh_params())
        v.addWidget(self._build_section_polyhedral_params())
        v.addWidget(self._build_section_generic_engine_params())
        v.addWidget(self._build_section_surface_mesh())
        v.addWidget(self._build_section_preprocess())
        v.addWidget(self._build_section_yplus())
        # 파이프라인 실행 버튼은 하단 Tier 스트립의 Run/Stop 버튼으로 통합됨.
        # (중복 UI 제거 — 2026-04-19)
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

    def _build_section_preset(self) -> object:  # pragma: no cover
        """프리셋 섹션 — 드롭다운에서 프리셋 선택 → 품질/엔진/파라미터 자동 세팅."""
        from PySide6.QtWidgets import QComboBox, QLabel

        from desktop.qt_app import presets as _presets

        f, v = self._section_frame("프리셋")
        self._preset_combo = QComboBox()
        self._preset_combo.setStyleSheet(
            "QComboBox { background: #161a20; color: #e8ecf2; "
            "border: 1px solid #323a46; border-radius: 4px; padding: 4px 8px; "
            "font-size: 12px; }"
            "QComboBox:hover { border-color: #4ea3ff; }"
            "QComboBox QAbstractItemView { background: #161a20; color: #e8ecf2; "
            "selection-background-color: #2c5f97; selection-color: #e8ecf2; "
            "border: 1px solid #323a46; outline: none; padding: 2px; }"
        )
        self._preset_combo.addItem("(프리셋 선택…)", None)
        for p in _presets.all_presets():
            self._preset_combo.addItem(p.name, p.name)
        self._preset_combo.currentIndexChanged.connect(self._on_preset_selected)
        v.addWidget(self._preset_combo)

        # 설명 레이블
        self._preset_desc_label = QLabel("")
        self._preset_desc_label.setStyleSheet(
            "color: #818a99; font-size: 10.5px; background: transparent; padding: 2px;"
        )
        self._preset_desc_label.setWordWrap(True)
        v.addWidget(self._preset_desc_label)

        # 현재 설정을 프리셋으로 저장 버튼
        from PySide6.QtWidgets import QPushButton

        save_preset_btn = QPushButton("현재 설정 → 프리셋 저장")
        save_preset_btn.setStyleSheet(
            "QPushButton { background: #161a20; color: #b6bdc9; "
            "border: 1px solid #323a46; border-radius: 4px; "
            "padding: 4px 8px; font-size: 11px; }"
            "QPushButton:hover { background: #1c2129; border-color: #4ea3ff; color: #e8ecf2; }"
        )
        save_preset_btn.clicked.connect(self._on_save_current_as_preset)
        v.addWidget(save_preset_btn)
        return f

    def _on_save_current_as_preset(self) -> None:  # pragma: no cover
        """현재 사이드바 설정을 사용자 정의 프리셋으로 저장."""
        from PySide6.QtWidgets import QInputDialog, QMessageBox

        from desktop.qt_app import presets as _presets

        name, ok = QInputDialog.getText(
            self._qmain, "프리셋 이름",
            "저장할 프리셋 이름 입력:",
            text="My Preset",
        )
        if not ok or not name.strip():
            return
        name = name.strip()

        # 이름 중복 확인 (내장과 같으면 거부)
        builtin_names = {p.name for p in _presets.BUILTIN_PRESETS}
        if name in builtin_names:
            QMessageBox.warning(
                self._qmain, "이름 충돌",
                f"'{name}'은(는) 내장 프리셋입니다. 다른 이름을 선택하세요.",
            )
            return

        description, ok = QInputDialog.getText(
            self._qmain, "프리셋 설명",
            "설명 (선택):",
            text="사용자 정의 프리셋",
        )
        if not ok:
            return

        # 현재 상태 수집
        tier_hint = self._tier_combo_text() if hasattr(self, "_tier_combo_text") else "auto"
        remesh_engine = (
            self._remesh_engine_text()
            if hasattr(self, "_remesh_engine_text") else "auto"
        )
        surface_remesh = False
        allow_ai_fallback = False
        try:
            if self._surface_remesh_check is not None:
                surface_remesh = bool(self._surface_remesh_check.isChecked())  # type: ignore[union-attr]
        except Exception:
            pass
        try:
            if self._allow_ai_fallback_check is not None:
                allow_ai_fallback = bool(
                    self._allow_ai_fallback_check.isChecked()  # type: ignore[union-attr]
                )
        except Exception:
            pass

        new_preset = _presets.Preset(
            name=name,
            description=description or "사용자 정의 프리셋",
            quality_level=self._quality_level.value,
            tier_hint=tier_hint,
            remesh_engine=remesh_engine,
            surface_remesh=surface_remesh,
            allow_ai_fallback=allow_ai_fallback,
        )
        _presets.save_user_preset(new_preset)
        self._log(f"[OK] 프리셋 저장: {name}")

        # 콤보박스 갱신
        if self._preset_combo is not None:
            try:
                # 현재 선택 저장
                cur = self._preset_combo.currentText()  # type: ignore[union-attr]
                self._preset_combo.clear()  # type: ignore[union-attr]
                self._preset_combo.addItem("(프리셋 선택…)", None)  # type: ignore[union-attr]
                for p in _presets.all_presets():
                    self._preset_combo.addItem(p.name, p.name)  # type: ignore[union-attr]
                # 새로 저장한 것 선택
                idx = self._preset_combo.findText(name)  # type: ignore[union-attr]
                if idx >= 0:
                    self._preset_combo.setCurrentIndex(idx)  # type: ignore[union-attr]
                else:
                    prev_idx = self._preset_combo.findText(cur)  # type: ignore[union-attr]
                    if prev_idx >= 0:
                        self._preset_combo.setCurrentIndex(prev_idx)  # type: ignore[union-attr]
            except Exception:
                pass

    def _on_preset_selected(self, index: int) -> None:  # pragma: no cover
        """프리셋 선택 → 품질/엔진/리메쉬 설정 자동 적용."""
        if self._preset_combo is None:
            return
        name = self._preset_combo.currentData()
        if not name:
            self._preset_desc_label.setText("")
            return
        from desktop.qt_app import presets as _presets

        preset = _presets.get(name)
        if preset is None:
            return

        # 품질 레벨
        try:
            level = QualityLevel(preset.quality_level)
            self._set_quality_level(level)
        except Exception:
            pass

        # 엔진 (tier_hint)
        if self._engine_combo is not None and preset.tier_hint:
            try:
                for i in range(self._engine_combo.count()):  # type: ignore[union-attr]
                    if self._engine_combo.itemData(i) == preset.tier_hint:  # type: ignore[union-attr]
                        self._engine_combo.setCurrentIndex(i)  # type: ignore[union-attr]
                        break
            except Exception:
                pass

        # 리메쉬 엔진
        if self._remesh_engine_combo is not None and preset.remesh_engine:
            try:
                idx = self._remesh_engine_combo.findText(preset.remesh_engine, 0)  # type: ignore[union-attr]
                if idx >= 0:
                    self._remesh_engine_combo.setCurrentIndex(idx)  # type: ignore[union-attr]
            except Exception:
                pass

        # 표면 리메쉬 체크박스
        if self._surface_remesh_check is not None:
            try:
                self._surface_remesh_check.setChecked(preset.surface_remesh)  # type: ignore[union-attr]
            except Exception:
                pass
        if self._allow_ai_fallback_check is not None:
            try:
                self._allow_ai_fallback_check.setChecked(preset.allow_ai_fallback)  # type: ignore[union-attr]
            except Exception:
                pass

        if (
            preset.tier_hint == "wildmesh"
            and self._wildmesh_param_panel is not None
            and preset.params
        ):
            try:
                wm_params = {
                    k: v for k, v in preset.params.items()
                    if k.startswith("wildmesh_")
                }
                if wm_params:
                    self._wildmesh_param_panel.set_params(wm_params)  # type: ignore[union-attr]
            except Exception:
                pass

        self._preset_desc_label.setText(preset.description)
        self._log(f"[INFO] 프리셋 적용: {preset.name}")

    def _make_engine_combo_model(self, parent=None) -> tuple[object, int]:  # pragma: no cover
        from PySide6.QtCore import Qt
        from PySide6.QtGui import QStandardItem, QStandardItemModel

        from desktop.qt_app import engine_policy

        policy = engine_policy.load()
        self._engine_policy = policy

        model = QStandardItemModel(parent)
        # beta104: 기본 엔진 = auto (strategist 가 mesh_type × quality 로 결정).
        # native_tet 이 MVP 수준이라 기본 강제하면 품질 실망 가능.
        desired_default = policy.default_tier if policy.default_tier != "auto" else "tier_auto"
        default_idx = 1  # fallback: 첫 실제 아이템 (auto)
        native_tet_idx = -1
        wildmesh_idx = -1
        for group, items in self.ENGINE_GROUPS:
            header = QStandardItem(f"── {group} ──")
            header.setFlags(Qt.NoItemFlags)
            header.setForeground(_qcolor(PALETTE["text_3"]))
            model.appendRow(header)
            for value, display, status in items:
                marker = {"ok": "● 설치됨", "off": "○ 미설치", "warn": "⚠ 설정 필요"}.get(status, "")
                canonical = _resolve_engine_canonical(value)
                blocked = not policy.is_allowed(canonical)
                if blocked:
                    marker = "🔒 정책 차단"
                item = QStandardItem(f"{display}  {marker}")
                item.setData(value, Qt.UserRole)
                if status == "off" or blocked:
                    item.setEnabled(False)
                row_idx = model.rowCount()
                if canonical == desired_default and item.isEnabled():
                    default_idx = row_idx
                if value == "native_tet" and item.isEnabled():
                    native_tet_idx = row_idx
                if value == "wildmesh" and item.isEnabled():
                    wildmesh_idx = row_idx
                model.appendRow(item)
        # 정책 default 를 못 찾았으면 native_tet, 그것도 없으면 WildMesh 로 fallback.
        if default_idx == 1:
            if native_tet_idx >= 0:
                default_idx = native_tet_idx
            elif wildmesh_idx >= 0:
                default_idx = wildmesh_idx
        return model, default_idx

    def _rebuild_engine_combo_model(self) -> None:  # pragma: no cover
        """현재 엔진 정책 기준으로 엔진 콤보 모델을 다시 만든다."""
        from PySide6.QtCore import Qt

        if self._engine_combo is None:
            return
        try:
            current = self._engine_combo.currentData()  # type: ignore[union-attr]
        except Exception:
            current = None

        model, default_idx = self._make_engine_combo_model(self._engine_combo)
        self._engine_combo.setModel(model)  # type: ignore[union-attr]

        restored_idx = -1
        if current is not None:
            try:
                for i in range(model.rowCount()):  # type: ignore[attr-defined]
                    item = model.item(i)  # type: ignore[attr-defined]
                    if item and item.data(Qt.UserRole) == current and item.isEnabled():
                        restored_idx = i
                        break
            except Exception:
                restored_idx = -1

        self._engine_combo.setCurrentIndex(  # type: ignore[union-attr]
            restored_idx if restored_idx >= 0 else default_idx
        )
        self._refresh_wildmesh_panel_visibility()

    def _build_section_engine(self) -> object:  # pragma: no cover
        from PySide6.QtWidgets import QComboBox, QHBoxLayout, QLabel, QWidget

        from desktop.qt_app import engine_policy

        f, v = self._section_frame("메시 엔진")

        # 현재 정책 로드
        policy = engine_policy.load()
        self._engine_policy = policy

        # 정책이 wildmesh_only 면 배너 표시
        if policy.mode != "all":
            banner = QLabel(f"⚙ 정책: {policy.mode}")
            banner.setStyleSheet(
                f"color: {PALETTE['accent']}; font-size: 10.5px; "
                f"background: transparent; padding: 2px 4px; "
                f"border: 1px dashed {PALETTE['accent']}; border-radius: 3px;"
            )
            v.addWidget(banner)

        combo = QComboBox()
        combo.setStyleSheet(self._dark_combo_qss())
        model, default_idx = self._make_engine_combo_model(combo)
        combo.setModel(model)
        combo.setCurrentIndex(default_idx)
        self._engine_combo = combo
        self._tier_combo = combo  # 호환
        # 엔진 변경시 WildMesh 파라미터 패널 표시/숨김 + Tier 3 라벨 갱신
        combo.currentIndexChanged.connect(
            lambda _idx: self._on_engine_changed()
        )
        v.addWidget(combo)

        # engine-legend — 도트 설명
        legend = QWidget()
        legend.setStyleSheet("background: transparent;")
        lrow = QHBoxLayout(legend)
        lrow.setContentsMargins(0, 4, 0, 0)
        lrow.setSpacing(12)
        for css_dot, lbl in [
            (f"background: {PALETTE['ok']};", "설치됨"),
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

    def _build_section_wildmesh_params(self) -> object:  # pragma: no cover
        """WildMesh 슬라이더 패널 + '⟲ 이전 값' 버튼. tier=wildmesh 선택시만 표시."""
        from PySide6.QtWidgets import QHBoxLayout, QPushButton

        from desktop.qt_app.widgets.wildmesh_param_panel import WildMeshParamPanel

        f, v = self._section_frame("WildMesh 튜닝")
        panel = WildMeshParamPanel()
        panel.params_changed.connect(self._on_wildmesh_params_changed)
        self._wildmesh_param_panel = panel
        v.addWidget(panel)

        # ⟲ 이전 값 버튼
        revert_row = QHBoxLayout()
        revert_row.addStretch()
        revert_btn = QPushButton("⟲ 이전 값")
        revert_btn.setToolTip("최근 변경 전 파라미터로 되돌리기")
        revert_btn.setStyleSheet(
            f"QPushButton {{ background: {PALETTE['bg_2']}; color: {PALETTE['text_1']}; "
            f"border: 1px solid {PALETTE['line_2']}; border-radius: 3px; "
            f"padding: 3px 10px; font-size: 11px; }} "
            f"QPushButton:hover {{ border-color: {PALETTE['accent']}; color: {PALETTE['text_0']}; }} "
            f"QPushButton:disabled {{ color: {PALETTE['text_3']}; }}"
        )
        revert_btn.setEnabled(False)
        revert_btn.clicked.connect(self._on_revert_wildmesh_params)
        self._param_revert_btn = revert_btn
        revert_row.addWidget(revert_btn)
        v.addLayout(revert_row)

        self._wildmesh_param_frame = f
        # 기본적으로는 tier=wildmesh 가 아닐 수 있으므로 show/hide는 엔진 선택 핸들러에서 제어
        self._refresh_wildmesh_panel_visibility()
        return f

    def _build_section_polyhedral_params(self) -> object:  # pragma: no cover
        """polyDualMesh 파라미터 패널. tier=polyhedral 선택 시만 표시."""
        from desktop.qt_app.widgets.polyhedral_param_panel import PolyhedralParamPanel

        f, v = self._section_frame("polyDualMesh 튜닝")
        panel = PolyhedralParamPanel()
        panel.params_changed.connect(self._on_polyhedral_params_changed)
        self._polyhedral_param_panel = panel
        v.addWidget(panel)

        self._polyhedral_param_frame = f
        # 초기에는 숨김 (polyhedral 엔진 선택 시 표시)
        f.setVisible(False)
        return f

    def _on_polyhedral_params_changed(self, _params: dict) -> None:  # pragma: no cover
        """polyDualMesh 패널 값 변경 — 현재는 파이프라인 실행 시 즉시 적용."""
        # 별도 로깅 없이 단순 pass. 값은 _on_run_clicked 에서 current_params() 로 읽는다.
        pass

    def _build_section_generic_engine_params(self) -> object:  # pragma: no cover
        """wildmesh / polyhedral 을 제외한 모든 엔진의 파라미터 패널.

        엔진 콤보 변경 시 spec 레지스트리에서 해당 엔진 파라미터를 읽어
        슬라이더/체크박스/콤보/ⓘ 팝업을 자동 생성한다.
        """
        from desktop.qt_app.widgets.generic_engine_param_panel import (
            GenericEngineParamPanel,
        )

        f, v = self._section_frame("엔진 파라미터")
        panel = GenericEngineParamPanel()
        panel.params_changed.connect(self._on_generic_engine_params_changed)
        self._generic_param_panel = panel
        v.addWidget(panel)
        self._generic_param_frame = f
        f.setVisible(False)
        return f

    def _on_generic_engine_params_changed(self, _params: dict) -> None:  # pragma: no cover
        """generic 엔진 파라미터 변경 — 값은 _on_run_clicked 에서 읽는다."""
        pass

    def _build_section_yplus(self) -> object:  # pragma: no cover
        """y⁺ 기반 첫 BL 층 두께 자동 계산 패널 (beta100).

        사용자가 유체·유입 속도·특성 길이·목표 y⁺ 입력 후 Calculate 를 누르면
        `bl_thickness_computed` 시그널이 발행되고, `_on_run_clicked` 시 해당 값이
        `tier_params["bl_first_thickness"]` 에 주입된다. 파일 drop 시 bbox 대각선을
        `set_characteristic_length` 로 자동 주입.
        """
        from desktop.qt_app.widgets.yplus_panel import YPlusPanel

        f, v = self._section_frame("y⁺ 자동 BL 두께")
        panel = YPlusPanel()
        panel.bl_thickness_computed.connect(self._on_yplus_thickness_computed)
        self._yplus_panel = panel
        v.addWidget(panel)
        self._yplus_frame = f
        return f

    def _on_yplus_thickness_computed(self, thickness: float) -> None:  # pragma: no cover
        """y⁺ 패널 Calculate → 계산된 첫 층 두께 [m] 수신 후 저장 + 로그."""
        self._computed_bl_first_thickness = float(thickness)
        try:
            self._log(
                f"[INFO] y⁺ → bl_first_thickness = {thickness:.3e} m "
                "(다음 Run 부터 자동 적용)"
            )
        except Exception:
            pass

    def _refresh_generic_param_panel(self) -> None:  # pragma: no cover
        """엔진 변경 시 generic 패널을 현재 엔진 spec 으로 갱신.

        wildmesh / polyhedral 은 전용 패널이 따로 있으므로 generic 은 숨긴다.
        해당 엔진의 spec 이 비어 있어도 숨긴다.
        """
        if self._generic_param_frame is None or self._generic_param_panel is None:
            return
        try:
            tier = self._tier_combo_text().lower()
        except Exception:
            tier = "auto"

        if tier in ("wildmesh", "polyhedral", "auto", ""):
            self._generic_param_frame.setVisible(False)  # type: ignore[union-attr]
            return

        try:
            from desktop.qt_app.widgets.engine_params_spec import get_specs_for_engine
            specs = get_specs_for_engine(tier)
            if not specs:
                self._generic_param_frame.setVisible(False)  # type: ignore[union-attr]
                return
            self._generic_param_panel.set_engine(tier)  # type: ignore[union-attr]
            self._generic_param_frame.setVisible(True)  # type: ignore[union-attr]
        except Exception:
            self._generic_param_frame.setVisible(False)  # type: ignore[union-attr]

    # Tier별 엔진 후보 — (combo value, display label).
    # v0.4 Native-First: 외부 라이브러리는 전부 제거. native_* + disabled + auto 만.
    _TIER0_ENGINES: tuple[tuple[str, str], ...] = (
        ("native_repair", "Native Repair"),
        ("disabled", "비활성화"),
    )
    _TIER1_ENGINES: tuple[tuple[str, str], ...] = (
        ("native_surface", "Native Surface"),
        ("disabled", "비활성화"),
    )
    _TIER2_ENGINES: tuple[tuple[str, str], ...] = (
        ("native_isotropic", "Native Isotropic (Botsch)"),
        ("native_cvt", "Native CVT (Lloyd)"),
        ("disabled", "비활성화"),
    )
    # Tier 3 (볼륨 메쉬) — 기존 _build_section_engine 의 ENGINE_GROUPS 로부터 평면화.
    # GUI-CLEAN / beta2809 — 실제 구현 + tested 엔진만 노출.
    # 검증 (5 STL × 3 engine = 6/6 grade A) 통과한 엔진만 default.
    _TIER3_ENGINES: tuple[tuple[str, str], ...] = (
        ("auto", "Auto (strategist)"),
        ("native_tet", "Native Tet · scipy Delaunay + Klingner full sweep"),
        ("native_hex", "Native Hex · octree+snap+BL"),
        ("native_poly", "Native Poly · Voronoi+CVT (clipping)"),
    )
    _TIER4_ENGINES: tuple[tuple[str, str], ...] = (
        ("native_bl", "Native BL (Phase 2)"),
        ("native_bl_tet", "Native BL — tet 3 분할"),
        ("poly_bl_transition", "Native BL — poly dual 전환"),
        ("auto", "Auto (품질 레벨 기반)"),
        ("disabled", "비활성화"),
    )
    _TIER5_ENGINES: tuple[tuple[str, str], ...] = (
        ("native", "Native Checker · parity 검증"),
        ("disabled", "비활성화"),
    )

    def _build_section_tier_engines(self) -> object:  # pragma: no cover
        """Tier 0/1/2/4/5 각 단계의 엔진을 개별 드롭다운으로 선택.

        Tier 3 (볼륨 메쉬)는 상위 '메시 엔진' 섹션에서 이미 선택하므로 제외.
        기본적으로 Tier 0/1/2/4는 비활성화 — WildMesh 단독으로 돌릴 수 있게.
        """
        # GUI-SIMPLIFY / beta2814 — Option C: mesh_type 1콤보 + BL 체크박스만 노출.
        # Tier 3 (볼륨) → Mesh Type combo (tet / hex / poly).
        # Tier 4 (BL) → 체크박스 1개 (체크 시 auto, 미체크 시 disabled).
        # Tier 5 (검증) → 항상 native (UI 숨김).
        from PySide6.QtWidgets import (
            QCheckBox, QComboBox, QHBoxLayout, QLabel, QWidget,
        )

        f, v = self._section_frame("메쉬 설정")

        # --- Mesh Type combo (Tier 3) ---
        row1 = QWidget()
        row1.setStyleSheet("background: transparent;")
        rl1 = QHBoxLayout(row1)
        rl1.setContentsMargins(0, 0, 0, 0); rl1.setSpacing(8)
        lbl1 = QLabel("Mesh Type")
        lbl1.setStyleSheet(
            f"color: {PALETTE['text_2']}; font-size: 11px; "
            f"background: transparent; min-width: 120px;"
        )
        rl1.addWidget(lbl1)

        cb_mesh = QComboBox()
        cb_mesh.setStyleSheet(self._dark_combo_qss())
        # 핵심 3 mesh type 만 노출 (CLAUDE.md mesh_type 정책).
        # BETA2836 — Tet 옵션을 vendored fTetWild (wildmesh) 로 매핑.
        # 이전 "native_tet" 은 우리 Python self-impl tet engine (tier_native_tet)
        # 으로 wildmesh 와 알고리즘 자체가 다른 결과 생성. BETA2834 vendored
        # binding 이 있으므로 default 는 fTetWild 로 변경 — 결과 동일성 보장.
        # BETA2845 — 3 mesh_type 모두 vendored backend 로 default.
        for value, display in [
            ("wildmesh",    "Tet · fTetWild (vendored, wildmesh-identical)"),
            ("cfmesh",      "Hex_dominant · cfMesh cartesianMesh (vendored, BL 통합)"),
            ("cfmesh_poly", "Poly · cfMesh pMesh (vendored, BL 통합)"),
        ]:
            cb_mesh.addItem(display, value)
        cb_mesh.setCurrentIndex(0)  # default: wildmesh (vendored fTetWild).
        cb_mesh.currentIndexChanged.connect(
            lambda _idx: self._on_engine_changed()
        )
        # alias 로 기존 핸들러 호환.
        self._engine_combo = cb_mesh
        self._tier_combo = cb_mesh
        self._tier3_engine_combo = cb_mesh
        rl1.addWidget(cb_mesh, stretch=1)
        v.addWidget(row1)

        # --- BL checkbox (Tier 4) ---
        row2 = QWidget()
        row2.setStyleSheet("background: transparent;")
        rl2 = QHBoxLayout(row2)
        rl2.setContentsMargins(0, 0, 0, 0); rl2.setSpacing(8)
        self._bl_check = QCheckBox("Boundary Layer 적용 (auto)")
        self._bl_check.setStyleSheet(
            f"color: {PALETTE['text_2']}; font-size: 11px; "
            f"background: transparent;"
        )
        self._bl_check.setChecked(True)   # default ON.
        self._bl_check.setToolTip(
            "체크 시: quality_level 기반 자동 BL.\n"
            "미체크 시: BL 비활성화 (Euler/inviscid simulation 용)."
        )
        # 가짜 combobox alias — 기존 _tier4_engine_text() 호환.
        class _BLComboShim:
            def __init__(self, check):
                self._check = check
            def currentData(self):
                return "auto" if self._check.isChecked() else "disabled"
        self._tier4_engine_combo = _BLComboShim(self._bl_check)
        rl2.addWidget(self._bl_check)
        rl2.addStretch(1)
        v.addWidget(row2)

        # --- BETA2847 — cfMesh cell size 조절 (hex_dominant + poly 에 적용) ---
        from PySide6.QtWidgets import QDoubleSpinBox, QSpinBox, QLabel as _QL
        row3 = QWidget()
        row3.setStyleSheet("background: transparent;")
        rl3 = QHBoxLayout(row3)
        rl3.setContentsMargins(0, 0, 0, 0); rl3.setSpacing(8)
        rl3.addWidget(_QL("max cell:"))
        self._cfm_max_cell_spin = QDoubleSpinBox()
        self._cfm_max_cell_spin.setRange(0.0, 10.0)
        self._cfm_max_cell_spin.setSingleStep(0.01)
        self._cfm_max_cell_spin.setDecimals(4)
        self._cfm_max_cell_spin.setValue(0.0)  # 0 = auto from strategist.
        self._cfm_max_cell_spin.setToolTip(
            "cfMesh maxCellSize (volume cell size). 0 = strategist 자동값."
        )
        rl3.addWidget(self._cfm_max_cell_spin)
        rl3.addWidget(_QL("boundary cell:"))
        self._cfm_bnd_cell_spin = QDoubleSpinBox()
        self._cfm_bnd_cell_spin.setRange(0.0, 10.0)
        self._cfm_bnd_cell_spin.setSingleStep(0.005)
        self._cfm_bnd_cell_spin.setDecimals(4)
        self._cfm_bnd_cell_spin.setValue(0.0)  # 0 = auto.
        self._cfm_bnd_cell_spin.setToolTip(
            "cfMesh boundaryCellSize (surface 셀 크기, 작을수록 STL 정확).\n"
            "0 = strategist 자동값. 보통 max cell 의 1/4~1/10."
        )
        rl3.addWidget(self._cfm_bnd_cell_spin)
        rl3.addStretch(1)
        v.addWidget(row3)

        # --- BETA2847 — BL 세부 조절 (BL checkbox 가 켜진 경우에만 사용) ---
        row4 = QWidget()
        row4.setStyleSheet("background: transparent;")
        rl4 = QHBoxLayout(row4)
        rl4.setContentsMargins(0, 0, 0, 0); rl4.setSpacing(8)
        rl4.addWidget(_QL("BL layers:"))
        self._cfm_bl_layers_spin = QSpinBox()
        self._cfm_bl_layers_spin.setRange(0, 30)
        self._cfm_bl_layers_spin.setValue(0)  # 0 = auto from strategist.
        self._cfm_bl_layers_spin.setToolTip(
            "BL 레이어 수. 0 = quality_level 자동 결정 (BL 체크박스 ON 시).\n"
            ">0 = 명시적으로 강제 (overrides BL checkbox)."
        )
        rl4.addWidget(self._cfm_bl_layers_spin)
        rl4.addWidget(_QL("BL ratio:"))
        self._cfm_bl_ratio_spin = QDoubleSpinBox()
        self._cfm_bl_ratio_spin.setRange(1.0, 3.0)
        self._cfm_bl_ratio_spin.setSingleStep(0.05)
        self._cfm_bl_ratio_spin.setDecimals(3)
        self._cfm_bl_ratio_spin.setValue(1.2)
        self._cfm_bl_ratio_spin.setToolTip("BL expansion ratio (각 레이어 두께 증가율).")
        rl4.addWidget(self._cfm_bl_ratio_spin)
        rl4.addWidget(_QL("first thick:"))
        self._cfm_bl_first_spin = QDoubleSpinBox()
        self._cfm_bl_first_spin.setRange(0.0, 1.0)
        self._cfm_bl_first_spin.setSingleStep(0.001)
        self._cfm_bl_first_spin.setDecimals(5)
        self._cfm_bl_first_spin.setValue(0.0)  # 0 = auto.
        self._cfm_bl_first_spin.setToolTip(
            "최외곽 레이어 두께 (maxFirstLayerThickness). 0 = cfMesh 자동."
        )
        rl4.addWidget(self._cfm_bl_first_spin)
        rl4.addStretch(1)
        v.addWidget(row4)

        # Tier 5 (검증) — 항상 native, UI 노출 안 함.
        # _tier5_engine_combo 미생성 → _tier5_engine_text() fallback "native".
        self._tier5_engine_combo = None

        return f

    def _tier0_engine_text(self) -> str:
        try:
            if self._tier0_engine_combo is not None:
                return str(self._tier0_engine_combo.currentData() or "pymeshfix")  # type: ignore[union-attr]
        except Exception:
            pass
        return "pymeshfix"

    def _tier1_engine_text(self) -> str:
        try:
            if self._tier1_engine_combo is not None:
                return str(self._tier1_engine_combo.currentData() or "geogram_cdt")  # type: ignore[union-attr]
        except Exception:
            pass
        return "geogram_cdt"

    def _tier2_engine_text(self) -> str:
        try:
            if self._tier2_engine_combo is not None:
                return str(self._tier2_engine_combo.currentData() or "auto")  # type: ignore[union-attr]
        except Exception:
            pass
        return "auto"

    def _tier4_engine_text(self) -> str:
        try:
            if self._tier4_engine_combo is not None:
                return str(self._tier4_engine_combo.currentData() or "auto")  # type: ignore[union-attr]
        except Exception:
            pass
        return "auto"

    def _tier5_engine_text(self) -> str:
        try:
            if self._tier5_engine_combo is not None:
                return str(self._tier5_engine_combo.currentData() or "native")  # type: ignore[union-attr]
        except Exception:
            pass
        return "native"

    def _refresh_wildmesh_panel_visibility(self) -> None:  # pragma: no cover
        """tier 선택에 따라 wildmesh 패널 표시/숨김.

        WildMesh 선택 시 Surface Mesh 섹션의 중복 필드(Element Size / Min Size)도 숨긴다.
        WildMesh Tuning 패널의 edge_length_r 슬라이더와 역할이 동일하여 중복을 방지한다.
        """
        if self._wildmesh_param_frame is None:
            return
        try:
            tier = self._tier_combo_text().lower()
        except Exception:
            tier = "auto"
        show = (tier == "wildmesh")
        self._wildmesh_param_frame.setVisible(show)  # type: ignore[union-attr]
        # WildMesh 선택 시 품질 레벨 섹션 숨김 (WildMesh 튜닝 패널의 draft/standard/fine 버튼과 중복)
        if self._quality_section_frame is not None:
            try:
                self._quality_section_frame.setVisible(not show)  # type: ignore[union-attr]
            except Exception:
                pass
        # Surface Mesh 섹션 중복 필드 동기화
        try:
            self._refresh_surface_mesh_section_for_tier(tier)
        except Exception:
            pass

    @staticmethod
    def _dark_combo_qss() -> str:
        """모든 QComboBox에 공통으로 적용할 어두운 배경 스타일시트 (팝업 포함)."""
        return (
            f"QComboBox {{ background: {PALETTE['bg_2']}; color: {PALETTE['text_0']}; "
            f"border: 1px solid {PALETTE['line_2']}; border-radius: 5px; "
            f"padding: 6px 10px; font-size: 12px; min-height: 28px; }}"
            f"QComboBox:hover {{ border-color: {PALETTE['accent']}; }}"
            f"QComboBox::drop-down {{ border: none; width: 22px; }}"
            f"QComboBox QAbstractItemView {{ background: {PALETTE['bg_2']}; "
            f"color: {PALETTE['text_0']}; "
            f"selection-background-color: {PALETTE['accent_dim']}; "
            f"selection-color: {PALETTE['text_0']}; "
            f"border: 1px solid {PALETTE['line_2']}; outline: none; padding: 2px; }}"
        )

    def _on_engine_changed(self) -> None:  # pragma: no cover
        """엔진 콤보 변경 핸들러 — 파라미터 패널 표시/숨김 + Tier 3 라벨 동기화."""
        self._refresh_wildmesh_panel_visibility()
        self._refresh_polyhedral_panel_visibility()
        self._refresh_generic_param_panel()
        self._refresh_tier_strip_engine_labels()

    def _refresh_polyhedral_panel_visibility(self) -> None:  # pragma: no cover
        """엔진=polyhedral 일 때만 polyDualMesh 튜닝 패널 노출."""
        if self._polyhedral_param_frame is None:
            return
        try:
            tier = self._tier_combo_text().lower()
        except Exception:
            tier = "auto"
        try:
            self._polyhedral_param_frame.setVisible(tier == "polyhedral")  # type: ignore[union-attr]
        except Exception:
            pass

    def _refresh_tier_strip_engine_labels(self) -> None:  # pragma: no cover
        """현재 선택된 엔진 설정으로 모든 Tier 노드의 엔진명을 갱신한다."""
        if self._tier_pipeline is None:
            return
        try:
            tier = self._tier_combo_text()
        except Exception:
            tier = "auto"
        # 엔진 값 → 표시 이름 매핑 (Tier 3 Volume)
        display_map = {
            "auto": "auto (strategist)",
            "wildmesh": "WildMesh",
            "tetwild": "TetWild",
            "netgen": "Netgen",
            "mmg3d": "MMG3D",
            "meshpy": "MeshPy (TetGen)",
            "jigsaw": "JIGSAW",
            "core": "Geogram CDT",
            "snappy": "snappyHexMesh",
            "cfmesh": "cfMesh",
            "algohex": "AlgoHex",
            "robust_hex": "RobustHex",
            "hex_classy": "HexClassyBlocks",
            "cinolib_hex": "Cinolib Hex",
            "gmsh_hex": "GMSH Hex",
            "hohqmesh": "HOHQMesh",
            "voro_poly": "Voronoi Polyhedral",
            "polyhedral": "polyDualMesh",
            # v0.4 Native-First
            "native_tet": "Native Tet",
            "native_hex": "Native Hex",
            "native_poly": "Native Poly",
            "native_ai": "Native AI",
        }
        volume_engine = display_map.get(tier, tier)

        # Tier 콤보에서 선택된 값을 display label로 변환하는 helper
        def _combo_display(combo, specs, fallback: str) -> str:
            try:
                value = combo.currentData() if combo is not None else None
            except Exception:
                value = None
            if value is None:
                return fallback
            for v_val, display in specs:
                if v_val == value:
                    return display
            return str(value)

        # Tier 0 Preprocess — 사용자 선택 콤보 우선, 폴백은 no_repair 체크박스
        preprocess_engine = _combo_display(
            self._tier0_engine_combo, self._TIER0_ENGINES, "pymeshfix",
        )
        try:
            if self._no_repair_check is not None and self._no_repair_check.isChecked():  # type: ignore[union-attr]
                preprocess_engine = "(skip)"
        except Exception:
            pass

        # Tier 1 Surface
        surface_engine = _combo_display(
            self._tier1_engine_combo, self._TIER1_ENGINES, "Geogram CDT",
        )

        # Tier 2 Remesh — 전용 콤보 사용 (surface_remesh 체크해제 시 skip)
        remesh_engine = _combo_display(
            self._tier2_engine_combo, self._TIER2_ENGINES, "auto",
        )
        try:
            if self._surface_remesh_check is not None and not self._surface_remesh_check.isChecked():  # type: ignore[union-attr]
                remesh_engine = "(skip)"
        except Exception:
            pass

        # Tier 4 Layers — 사용자 선택 우선, "auto"면 품질 레벨별 자동 결정
        layers_engine = _combo_display(
            self._tier4_engine_combo, self._TIER4_ENGINES, "auto",
        )
        if layers_engine.startswith("auto"):
            try:
                ql = self._quality_level.value
                if ql == "fine":
                    layers_engine = "snappy addLayers (fine)"
                elif ql == "standard":
                    layers_engine = "optional (standard)"
                else:
                    layers_engine = "disabled (draft)"
            except Exception:
                pass

        # Tier 5 Validate
        validate_engine = _combo_display(
            self._tier5_engine_combo, self._TIER5_ENGINES, "OpenFOAM checkMesh",
        )

        tier_engines = [
            preprocess_engine, surface_engine, remesh_engine,
            volume_engine, layers_engine, validate_engine,
        ]

        try:
            nodes = getattr(self._tier_pipeline, "_nodes", None)
            if not nodes:
                return
            for idx, eng in enumerate(tier_engines):
                if idx < len(nodes):
                    nodes[idx]._engine = eng
                    nodes[idx].update()
        except Exception:
            pass

    def _on_wildmesh_params_changed(self, params: dict) -> None:  # pragma: no cover
        """슬라이더 변경시 revert 버튼 활성화 + param_history 적재."""
        if self._param_revert_btn is not None:
            try:
                from desktop.qt_app import param_history

                entries = param_history.load()
                self._param_revert_btn.setEnabled(len(entries) >= 1)  # type: ignore[union-attr]
            except Exception:
                pass

    def _on_revert_wildmesh_params(self) -> None:  # pragma: no cover
        """이전 파라미터 스냅샷 복원."""
        from desktop.qt_app import param_history

        prev = param_history.pop_previous()
        if prev is None:
            self._log("[INFO] 이전 파라미터 스냅샷 없음")
            if self._param_revert_btn is not None:
                self._param_revert_btn.setEnabled(False)  # type: ignore[union-attr]
            return
        if self._wildmesh_param_panel is not None:
            try:
                self._wildmesh_param_panel.set_params(prev)  # type: ignore[union-attr]
                self._log(f"[INFO] 이전 파라미터 복원: {prev}")
            except Exception:
                pass

    _MESH_TYPE_DESC = {
        "auto":         "Strategist 자동 선택 (geometry/quality 기반).",
        "tet":          "Tet — 복잡 형상 강건, isotropic.",
        "hex_dominant": "Hex-dominant — CFD BL 품질 우수, 셀 수 효율적.",
        "poly":         "Poly — 셀 수 최소, large-gradient 해소 우수.",
    }

    def _build_section_mesh_type(self) -> object:  # pragma: no cover
        """메쉬 타입 세그먼트 (Auto/Tet/Hex-Dom/Poly) — v0.4 신규."""
        from PySide6.QtWidgets import QFrame, QHBoxLayout, QLabel, QPushButton

        f, v = self._section_frame("메쉬 타입")

        seg = QFrame()
        seg.setStyleSheet(
            f"QFrame {{ background: {PALETTE['bg_2']}; "
            f"border: 1px solid {PALETTE['line_2']}; border-radius: 6px; }}"
        )
        row = QHBoxLayout(seg)
        row.setContentsMargins(3, 3, 3, 3)
        row.setSpacing(2)

        def _on_click(mt: str) -> None:
            self.set_mesh_type(mt)

        self._mesh_type_seg_btns: dict[str, object] = {}
        for mt, label in [
            ("auto", "Auto"),
            ("tet", "Tet"),
            ("hex_dominant", "Hex-Dom"),
            ("poly", "Poly"),
        ]:
            btn = QPushButton(label)
            btn.setFlat(True)
            btn.setCursor(_qt_cursor_pointing())
            btn.setProperty("active", mt == self._mesh_type)
            btn.setStyleSheet(
                f"QPushButton {{ background: transparent; "
                f"color: {PALETTE['text_2']}; "
                f"border: none; border-radius: 4px; padding: 6px 8px; "
                f"font-size: 11px; font-weight: 500; }}"
                f"QPushButton[active=\"true\"] {{ background: {PALETTE['bg_4']}; "
                f"color: {PALETTE['text_0']}; }}"
                f"QPushButton:hover:!pressed {{ color: {PALETTE['text_1']}; }}"
            )
            btn.clicked.connect(lambda _, M=mt: _on_click(M))
            row.addWidget(btn, stretch=1)
            self._mesh_type_seg_btns[mt] = btn
        v.addWidget(seg)

        desc = QLabel(self._MESH_TYPE_DESC.get(self._mesh_type, ""))
        desc.setWordWrap(True)
        desc.setStyleSheet(
            f"color: {PALETTE['text_2']}; font-size: 11px; font-style: italic; "
            f"background: transparent; padding-top: 4px;"
        )
        self._mesh_type_desc_label = desc
        v.addWidget(desc)
        return f

    def set_mesh_type(self, mesh_type: str) -> None:  # pragma: no cover
        """메쉬 타입 변경 — 세그먼트 버튼 상태 + desc label 동기화."""
        mt = str(mesh_type or "auto").lower()
        if mt not in ("auto", "tet", "hex_dominant", "poly"):
            return
        prev = self._mesh_type
        self._mesh_type = mt
        for key, btn in getattr(self, "_mesh_type_seg_btns", {}).items():
            try:
                btn.setProperty("active", key == mt)  # type: ignore[attr-defined]
                btn.style().unpolish(btn)             # type: ignore[attr-defined]
                btn.style().polish(btn)               # type: ignore[attr-defined]
            except Exception:
                pass
        lbl = getattr(self, "_mesh_type_desc_label", None)
        if lbl is not None:
            try:
                lbl.setText(self._MESH_TYPE_DESC.get(mt, ""))  # type: ignore[attr-defined]
            except Exception:
                pass
        if prev != mt:
            try:
                self._log(f"[INFO] 메쉬 타입 변경: {prev} → {mt}")
            except Exception:
                pass

    def _build_section_quality(self) -> object:  # pragma: no cover
        from PySide6.QtWidgets import QFrame, QHBoxLayout, QLabel, QPushButton, QWidget
        f, v = self._section_frame("품질 레벨")
        self._quality_section_frame = f

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
            btn.setProperty("active", "true" if lvl == self._quality_level.value else "false")
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
        self._allow_ai_fallback_check = QCheckBox("AI 표면 재생성 허용 (L3)")
        # v0.4: 자체 native L1 repair (pymeshfix 없이) — beta26 기본 On
        self._prefer_native_check = QCheckBox("Native L1 수리 (자체 repair, v0.4)")
        # v0.4.0-beta29: Strategist 가 native_* tier 를 primary 로 선택
        self._prefer_native_tier_check = QCheckBox(
            "Native Tier 우선 (native_tet/hex/poly)"
        )
        self._prefer_native_tier_check.setToolTip(
            "체크 시 Strategist 가 tet/hex_dominant/poly 각각에 대해 native_*\n"
            "엔진을 primary 로 선택. mesh_type 명시 필요.\n"
            "legacy tier (wildmesh/snappy/cfmesh 등) 는 fallback 으로 유지."
        )
        # beta2299 — CLI --cross-engine-fallback 대응 GUI 체크박스.
        self._cross_engine_fallback_check = QCheckBox(
            "Cross-engine fallback (poly→hex 자동 재시도)"
        )
        self._cross_engine_fallback_check.setToolTip(
            "체크 시 poly mesh_type 이 완전 실패하면 hex_dominant 로 1 회\n"
            "자동 재시도 (beta68 도입, CLI --cross-engine-fallback 동등).\n"
            "extreme tier 의 self-intersect 형상에서 회복률 향상."
        )
        # beta2345 — CLI --enable-vvv9h-apply / --enable-offplane-steiner 동등.
        self._enable_vvv9h_apply_check = QCheckBox(
            "VVV9H Klingner edge-contract real apply (실험적)"
        )
        self._enable_vvv9h_apply_check.setToolTip(
            "체크 시 Klingner 2008 §3.5 edge-contract 가 sliver 격감 위해 실 apply.\n"
            "AUTO_TESSELL_VVV9H_APPLY=1 동등. monotone guard 로 안전성 보장."
        )
        self._enable_offplane_steiner_check = QCheckBox(
            "Off-plane Steiner exudation (실험적)"
        )
        self._enable_offplane_steiner_check.setToolTip(
            "체크 시 Klingner-Shewchuk 2008 §4.1 off-plane Steiner 가 실 apply.\n"
            "AUTO_TESSELL_OFFPLANE_STEINER=1 동등. flat sliver tet 격감용."
        )
        # beta2351 — CLI VVV9J/K/P 동등 GUI 체크박스 (V-series 5 완전).
        self._enable_vvv9j_apply_check = QCheckBox(
            "VVV9J SLIM global-pass (실험적)"
        )
        self._enable_vvv9j_apply_check.setToolTip(
            "AUTO_TESSELL_VVV9J_APPLY=1 — SLIM smoothing 강화 (sliver-gated)."
        )
        self._enable_vvv9k_apply_check = QCheckBox(
            "VVV9K priority-queue main-loop (실험적)"
        )
        self._enable_vvv9k_apply_check.setToolTip(
            "AUTO_TESSELL_VVV9K_APPLY=1 — worst-first priority queue + monotone guard."
        )
        self._enable_vvv9p_apply_check = QCheckBox(
            "VVV9P multi-face removal (실험적)"
        )
        self._enable_vvv9p_apply_check.setToolTip(
            "AUTO_TESSELL_VVV9P_APPLY=1 — multi-face removal + monotone guard."
        )
        # C-GUI-8 / beta2419 — 최근 backend env flags 의 GUI 체크박스 노출.
        self._seed_gwn_check = QCheckBox(
            "Seed GWN (Jacobson 2013 SI-robust)"
        )
        self._seed_gwn_check.setToolTip(
            "체크 시 시드 inside test 에 generalized winding number 사용.\n"
            "SI/non-manifold 입력 robust. AUTO_TESSELL_SEED_GWN=1 동등.\n"
            "기본값은 자동 fallback (SI 검출 시 자동 ON, beta2394)."
        )
        self._stellar_split_check = QCheckBox(
            "Stellar 4-op split-pass (실험적)"
        )
        self._stellar_split_check.setToolTip(
            "체크 시 Stellar queue 의 split-pass 가 강제 활성.\n"
            "fine quality 는 자동 ON (beta2378).\n"
            "AUTO_TESSELL_STELLAR_SPLIT=1 동등."
        )
        self._parallel_delaunay_check = QCheckBox(
            "Parallel chunked Delaunay (V > 30k)"
        )
        self._parallel_delaunay_check.setToolTip(
            "체크 시 ProcessPoolExecutor 기반 chunked Delaunay 강제 활성.\n"
            "기본은 cpu_count() ≥ 2 시 자동 (beta2375).\n"
            "AUTO_TESSELL_PARALLEL_DELAUNAY=1 동등."
        )
        # C-GUI-D3 / beta2594 — beta2581-2593 신규 env flags 노출.
        self._cvt3d_qweight_check = QCheckBox(
            "CVT3D quality-weighted Lloyd (beta2586)"
        )
        self._cvt3d_qweight_check.setToolTip(
            "체크 시 Volumetric Lloyd 가 quality-weighted target.\n"
            "poor tet (q<0.3) → centroid weight 1/(q+0.05) — sliver pull 가속.\n"
            "AUTO_TESSELL_CVT3D_QUALITY_WEIGHT=1 동등."
        )
        self._lcr_auto_reduce_check = QCheckBox(
            "BL LCR global num_layers auto-reduce (beta2587)"
        )
        self._lcr_auto_reduce_check.setToolTip(
            "50%+ wall verts 가 좁은 gap 인 경우 cfg.num_layers 를\n"
            "median 으로 globally 감소 (Pointwise T-Rex 동등).\n"
            "AUTO_TESSELL_LCR_AUTO_REDUCE=1 동등."
        )
        self._bl_aniso_split_check = QCheckBox(
            "BL anisotropic prism split (beta2591)"
        )
        self._bl_aniso_split_check.setToolTip(
            "체크 시 mean wall-normal aspect > 4.0 인 BL 의 layer 를 mid-vertex\n"
            "삽입으로 균일 subdivide (cfMesh splitInternalLayers 동등).\n"
            "cfg.num_layers 2배. AUTO_TESSELL_BL_ANISO_SPLIT=1 동등."
        )
        self._ml_smooth_model_path = QLineEdit() if False else None  # lazy init below
        # C-GUI-D3: ML model path inputs.
        from PySide6.QtWidgets import QLineEdit as _QLE
        self._ml_smooth_model_path = _QLE()
        self._ml_smooth_model_path.setPlaceholderText("(optional) /path/to/ml_smooth_model.pt")
        self._ml_smooth_model_path.setToolTip(
            "tet quality predictor model 경로. 비워두면 ML smoothing 비활성.\n"
            "models/ml_smooth_model.pt 추천. AUTO_TESSELL_ML_SMOOTH_MODEL 동등."
        )
        self._bl_predict_model_path = _QLE()
        self._bl_predict_model_path.setPlaceholderText("(optional) /path/to/bl_predictor.pt")
        self._bl_predict_model_path.setToolTip(
            "BL collision predictor model 경로. 비워두면 ML predict 비활성.\n"
            "models/bl_predictor.pt 추천. AUTO_TESSELL_BL_PREDICT_MODEL 동등."
        )
        # C-GUI-14 / beta2449 — BL floor ratio (curvature_adaptive 강도).
        from PySide6.QtWidgets import QDoubleSpinBox, QLabel, QHBoxLayout, QWidget, QSpinBox
        self._bl_floor_ratio_spin = QDoubleSpinBox()
        self._bl_floor_ratio_spin.setRange(0.0, 1.0)
        self._bl_floor_ratio_spin.setSingleStep(0.05)
        self._bl_floor_ratio_spin.setDecimals(2)
        self._bl_floor_ratio_spin.setValue(1.0)
        self._bl_floor_ratio_spin.setToolTip(
            "BL curvature_adaptive_thickness floor ratio.\n"
            "1.0 = uniform thickness (안정성 ↑, hard mesh 권장).\n"
            "0.7 = cfMesh maxFirstLayerThickness parity.\n"
            "0.5 = balanced.\n"
            "0.3 = aggressive curvature adaptation (sharp feature 자동 thinning).\n"
            "AUTO_TESSELL_BL_FLOOR_RATIO 환경변수 동등."
        )
        # C-GUI-15 / beta2460 — patch count cap (polyMesh boundary).
        self._patch_cap_spin = QSpinBox()
        self._patch_cap_spin.setRange(8, 1024)
        self._patch_cap_spin.setSingleStep(8)
        self._patch_cap_spin.setValue(64)
        self._patch_cap_spin.setToolTip(
            "polyMesh patch count cap. 이 값을 초과하는 patch 는 wall_misc 로 병합.\n"
            "기본 64. 늘리면 BC 별 세분화 가능 (boundary 파일 증가).\n"
            "AUTO_TESSELL_PATCH_CAP 환경변수 동등."
        )
        # C-GUI-16 / beta2461 — hex feature snap budget (s).
        self._hex_snap_budget_spin = QDoubleSpinBox()
        self._hex_snap_budget_spin.setRange(0.0, 600.0)
        self._hex_snap_budget_spin.setSingleStep(5.0)
        self._hex_snap_budget_spin.setDecimals(1)
        self._hex_snap_budget_spin.setValue(0.0)  # 0 = off
        self._hex_snap_budget_spin.setToolTip(
            "Hex feature snap pass 의 wall-clock budget (초).\n"
            "0 = off (기본). 설정 시 강제 cap (hard hex 메쉬에서 hang 방지).\n"
            "AUTO_TESSELL_HEX_WWW7_BUDGET_S 환경변수 동등."
        )
        # C-GUI-17 / beta2462 — Lloyd plateau threshold (poly CVT 수렴).
        self._lloyd_plateau_spin = QDoubleSpinBox()
        self._lloyd_plateau_spin.setRange(1e-7, 1e-1)
        self._lloyd_plateau_spin.setSingleStep(5e-5)
        self._lloyd_plateau_spin.setDecimals(7)
        self._lloyd_plateau_spin.setValue(1e-4)  # default
        self._lloyd_plateau_spin.setToolTip(
            "Poly Lloyd CVT plateau early-exit threshold (rel-disp/bbox).\n"
            "기본 1e-4. 작을수록 더 수렴 (느림), 클수록 일찍 종료.\n"
            "AUTO_TESSELL_LLOYD_PLATEAU_THRESH 환경변수 동등."
        )
        # 기본값: native L1 은 기본 On (beta26 철학), native tier 는 opt-in
        self._no_repair_check.setChecked(False)
        self._surface_remesh_check.setChecked(False)
        self._allow_ai_fallback_check.setChecked(False)
        self._prefer_native_check.setChecked(True)  # beta26 default
        self._prefer_native_tier_check.setChecked(False)
        self._cross_engine_fallback_check.setChecked(False)
        self._enable_vvv9h_apply_check.setChecked(False)
        self._enable_offplane_steiner_check.setChecked(False)
        self._enable_vvv9j_apply_check.setChecked(False)
        self._enable_vvv9k_apply_check.setChecked(False)
        self._enable_vvv9p_apply_check.setChecked(False)
        # C-GUI-8 / beta2420 — 신규 env 체크박스 default OFF + layout 추가.
        self._seed_gwn_check.setChecked(False)
        self._stellar_split_check.setChecked(False)
        self._parallel_delaunay_check.setChecked(False)
        # C-GUI-D3 / beta2594 — 신규 env-flag default OFF.
        self._cvt3d_qweight_check.setChecked(False)
        self._lcr_auto_reduce_check.setChecked(False)
        self._bl_aniso_split_check.setChecked(False)
        for chk in (
            self._no_repair_check, self._surface_remesh_check,
            self._allow_ai_fallback_check, self._prefer_native_check,
            self._prefer_native_tier_check, self._cross_engine_fallback_check,
            self._enable_vvv9h_apply_check, self._enable_offplane_steiner_check,
            self._enable_vvv9j_apply_check, self._enable_vvv9k_apply_check,
            self._enable_vvv9p_apply_check,
            self._seed_gwn_check, self._stellar_split_check,
            self._parallel_delaunay_check,
            self._cvt3d_qweight_check, self._lcr_auto_reduce_check,
            self._bl_aniso_split_check,
        ):
            v.addWidget(chk)
        # C-GUI-D3: ML model path rows.
        try:
            from PySide6.QtWidgets import QHBoxLayout, QLabel, QWidget
            for label_txt, line_edit in (
                ("ML smooth model:", self._ml_smooth_model_path),
                ("BL predict model:", self._bl_predict_model_path),
            ):
                _row = QWidget()
                _row.setStyleSheet("background: transparent;")
                _h = QHBoxLayout(_row)
                _h.setContentsMargins(0, 0, 0, 0); _h.setSpacing(8)
                _h.addWidget(QLabel(label_txt))
                _h.addWidget(line_edit, 1)
                v.addWidget(_row)
        except Exception:
            pass
        # C-GUI-14 / beta2449 — BL floor ratio spin row.
        try:
            from PySide6.QtWidgets import QHBoxLayout, QLabel, QWidget
            _bl_row = QWidget()
            _bl_row.setStyleSheet("background: transparent;")
            _bl_layout = QHBoxLayout(_bl_row)
            _bl_layout.setContentsMargins(0, 0, 0, 0); _bl_layout.setSpacing(8)
            _bl_layout.addWidget(QLabel("BL floor ratio:"))
            _bl_layout.addWidget(self._bl_floor_ratio_spin)
            _bl_layout.addStretch(1)
            v.addWidget(_bl_row)
        except Exception:
            pass
        # C-GUI-15 / beta2460 — patch cap spin row.
        try:
            from PySide6.QtWidgets import QHBoxLayout, QLabel, QWidget
            _pc_row = QWidget()
            _pc_row.setStyleSheet("background: transparent;")
            _pc_layout = QHBoxLayout(_pc_row)
            _pc_layout.setContentsMargins(0, 0, 0, 0); _pc_layout.setSpacing(8)
            _pc_layout.addWidget(QLabel("Patch cap:"))
            _pc_layout.addWidget(self._patch_cap_spin)
            _pc_layout.addStretch(1)
            v.addWidget(_pc_row)
        except Exception:
            pass
        # C-GUI-16 / beta2461 — hex snap budget spin row.
        try:
            from PySide6.QtWidgets import QHBoxLayout, QLabel, QWidget
            _hs_row = QWidget()
            _hs_row.setStyleSheet("background: transparent;")
            _hs_layout = QHBoxLayout(_hs_row)
            _hs_layout.setContentsMargins(0, 0, 0, 0); _hs_layout.setSpacing(8)
            _hs_layout.addWidget(QLabel("Hex snap budget (s):"))
            _hs_layout.addWidget(self._hex_snap_budget_spin)
            _hs_layout.addStretch(1)
            v.addWidget(_hs_row)
        except Exception:
            pass
        # C-GUI-17 / beta2462 — Lloyd plateau threshold spin row.
        try:
            from PySide6.QtWidgets import QHBoxLayout, QLabel, QWidget
            _lp_row = QWidget()
            _lp_row.setStyleSheet("background: transparent;")
            _lp_layout = QHBoxLayout(_lp_row)
            _lp_layout.setContentsMargins(0, 0, 0, 0); _lp_layout.setSpacing(8)
            _lp_layout.addWidget(QLabel("Lloyd plateau thresh:"))
            _lp_layout.addWidget(self._lloyd_plateau_spin)
            _lp_layout.addStretch(1)
            v.addWidget(_lp_row)
        except Exception:
            pass
            try:
                chk.toggled.connect(lambda _v: self._refresh_tier_strip_engine_labels())
            except Exception:
                pass

        from PySide6.QtWidgets import QComboBox, QHBoxLayout, QLabel, QWidget
        rem_row = QWidget()
        rem_row.setStyleSheet("background: transparent;")
        rl = QHBoxLayout(rem_row)
        rl.setContentsMargins(0, 6, 0, 0); rl.setSpacing(8)
        rl.addWidget(QLabel("L2 엔진:"))
        cb = QComboBox()
        cb.setStyleSheet(self._dark_combo_qss())
        # v0.4 Native-First: 외부 엔진 전부 제거.
        cb.addItems([
            "native_isotropic",   # Botsch 2004
            "native_cvt",         # Lloyd CVT
            "disabled",
        ])
        cb.setCurrentIndex(0)  # 기본값 native_isotropic
        cb.currentIndexChanged.connect(
            lambda _idx: self._refresh_tier_strip_engine_labels()
        )
        self._remesh_engine_combo = cb
        rl.addWidget(cb, stretch=1)
        v.addWidget(rem_row)

        # beta2301 — CLI --auto-retry 대응 GUI 콤보 (off / once / continue).
        ar_row = QWidget()
        ar_row.setStyleSheet("background: transparent;")
        ar_l = QHBoxLayout(ar_row)
        ar_l.setContentsMargins(0, 6, 0, 0); ar_l.setSpacing(8)
        ar_l.addWidget(QLabel("Auto-retry:"))
        ar_cb = QComboBox()
        ar_cb.setStyleSheet(self._dark_combo_qss())
        ar_cb.addItems(["off", "once", "continue"])
        ar_cb.setCurrentIndex(0)  # off — v0.4 기본값.
        ar_cb.setToolTip(
            "Generator ↔ Evaluator 자동 재시도 모드.\n"
            "  off       : FAIL 시 사용자 확인 (기본).\n"
            "  once      : Evaluator 결과 기반 1 회 자동 재시도.\n"
            "  continue  : 성공 시까지 반복 (max_iterations 까지)."
        )
        ar_cb.currentIndexChanged.connect(
            lambda _idx, c=ar_cb: setattr(self, "_auto_retry", c.currentText())
        )
        self._auto_retry_combo = ar_cb
        ar_l.addWidget(ar_cb, stretch=1)
        v.addWidget(ar_row)
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
        # beta2300 — CLI --max-cells 대응 GUI 입력 필드 (이전엔 attribute 만
        # 선언되어 있고 widget 미생성 → 사용자가 cell 수 cap 설정 불가).
        self._max_cells_edit = QLineEdit()
        self._max_cells_edit.setPlaceholderText("(no cap)")
        self._max_cells_edit.setToolTip(
            "최대 셀 수 cap. 초과 시 셀 크기 자동 확대 후 재생성.\n"
            "비워두면 무제한. CLI --max-cells 동등."
        )

        # Element Size / Min Size 행 — WildMesh 선택 시 WildMesh Tuning 패널의
        # edge_length_r 슬라이더와 중복이므로 숨김. _refresh_wildmesh_panel_visibility에서 제어.
        el_size_lbl = _lbl("Element Size")
        min_size_lbl = _lbl("Min Size")
        self._surface_size_lbl_el = el_size_lbl
        self._surface_size_lbl_min = min_size_lbl

        g.addWidget(el_size_lbl, 0, 0)
        g.addWidget(self._surface_element_size_edit, 0, 1)
        g.addWidget(min_size_lbl, 1, 0)
        g.addWidget(self._surface_min_size_edit, 1, 1)
        g.addWidget(_lbl("Feature Angle (BL)"), 2, 0)
        g.addWidget(self._surface_feature_angle_edit, 2, 1)
        g.addWidget(_lbl("Max Cells"), 3, 0)
        g.addWidget(self._max_cells_edit, 3, 1)
        v.addWidget(grid_w)

        # 중복 방지 힌트 라벨 — WildMesh 선택 시에만 표시
        from PySide6.QtWidgets import QLabel as _QL
        dup_hint = _QL(
            "Element Size는 WildMesh Tuning의\nedge_length_r 슬라이더로 제어하세요."
        )
        dup_hint.setStyleSheet(
            f"color: {PALETTE['text_3']}; font-size: 10px; "
            f"background: transparent; padding: 2px;"
        )
        dup_hint.setWordWrap(True)
        dup_hint.setVisible(False)
        self._surface_size_dup_hint = dup_hint
        v.addWidget(dup_hint)

        return f

    def _refresh_surface_mesh_section_for_tier(self, tier: str) -> None:  # pragma: no cover
        """WildMesh 선택 여부에 따라 Surface Mesh 섹션 중복 필드를 숨김/표시한다."""
        is_wildmesh = (tier.lower() == "wildmesh")
        for w in (
            getattr(self, "_surface_size_lbl_el", None),
            getattr(self, "_surface_size_lbl_min", None),
            self._surface_element_size_edit,
            self._surface_min_size_edit,
        ):
            if w is not None:
                try:
                    w.setVisible(not is_wildmesh)  # type: ignore[union-attr]
                except Exception:
                    pass
        hint = getattr(self, "_surface_size_dup_hint", None)
        if hint is not None:
            try:
                hint.setVisible(is_wildmesh)  # type: ignore[union-attr]
            except Exception:
                pass

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

        # J5 / beta2630 — 키보드 shortcut.
        # F5 = Run, Esc = Stop, Ctrl+L = clear log, Ctrl+R = re-run.
        try:
            from PySide6.QtGui import QShortcut, QKeySequence
            _sc_run = QShortcut(QKeySequence("F5"), self._qmain)
            _sc_run.activated.connect(self._on_run_clicked)
            _sc_stop = QShortcut(QKeySequence("Esc"), self._qmain)
            _sc_stop.activated.connect(self._on_stop_clicked)
            _sc_rerun = QShortcut(QKeySequence("Ctrl+R"), self._qmain)
            _sc_rerun.activated.connect(self._on_run_clicked)
        except Exception:
            pass
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
        # beta2290: TierPipelineStrip 실 API 동기화. 이전 코드는
        # run_requested / reset_requested 라는 미존재 시그널에 connect 시도하여
        # 윈도우 생성 시 AttributeError 로 GUI 가 부분 깨졌다.
        self._tier_pipeline.resume_requested.connect(self._on_run_clicked)
        self._tier_pipeline.rerun_requested.connect(self._on_run_clicked)
        self._tier_pipeline.stop_requested.connect(self._on_stop_clicked)
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

    def _run_wildmesh_preflight_if_applicable(self) -> bool:  # pragma: no cover
        """wildmesh_only 정책 활성시 입력 파일 preflight. 사용자 취소시 False."""
        from desktop.qt_app import engine_policy as _pol

        policy = _pol.load()
        if policy.mode != "wildmesh_only":
            return True  # 정책 off면 생략
        if self._input_path is None:
            return True

        from desktop.qt_app.wildmesh_preflight import analyze, format_summary

        report = analyze(self._input_path)
        if not report.warnings:
            return True  # 감지된 이슈 없음

        # 경고 로그
        for w in report.warnings:
            level_tag = {"info": "INFO", "warn": "WARN", "danger": "ERR"}.get(w.level.value, "INFO")
            self._log(f"[{level_tag}] preflight: {w.title} — {w.description}")

        # DANGER 있으면 모달로 확인받음
        if report.is_safe:
            return True
        from PySide6.QtWidgets import QMessageBox

        summary = format_summary(report)
        resp = QMessageBox.warning(
            self._qmain,
            "WildMesh-only 위험 경고",
            f"WildMesh-only 모드에서 실행 전 위험 패턴이 감지됐습니다:\n\n{summary}\n\n"
            "계속 진행하시겠습니까? (WildMesh가 실패하면 fallback 없음)",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        )
        return resp == QMessageBox.Yes

    def _on_run_clicked(self) -> None:  # pragma: no cover
        if self._input_path is None:
            self._log("[WARN] 입력 파일이 없습니다 — 먼저 파일을 드롭하세요")
            return
        if self._output_dir is None:
            self._output_dir = self._input_path.parent / f"{self._input_path.stem}_case"

        # wildmesh_only 모드 preflight — 위험 케이스 발견시 사용자 경고
        if not self._run_wildmesh_preflight_if_applicable():
            return  # 사용자가 cancel

        # 사이드바 surface mesh 파라미터 → 워커 전달
        element_size = _parse_float(
            self._surface_element_size_edit.text()
            if self._surface_element_size_edit else ""
        )
        feature_angle = _parse_float(
            self._surface_feature_angle_edit.text()
            if self._surface_feature_angle_edit else ""
        )
        # beta2300 — Max Cells cap (CLI --max-cells 동등). 빈 값/0 = 무제한.
        _max_cells_text = (
            self._max_cells_edit.text().strip()
            if getattr(self, "_max_cells_edit", None) else ""
        )
        max_cells: int | None = None
        if _max_cells_text:
            try:
                _v = int(_max_cells_text)
                if _v > 0:
                    max_cells = _v
            except (ValueError, TypeError):
                self._log(
                    f"[WARN] Max Cells 입력 무시 (정수 아님): {_max_cells_text!r}"
                )
        # tier_hint: engine_combo 의 itemData value
        tier_hint = self._tier_combo_text()

        # tier-specific params: feature_angle 이 있으면 BL 파라미터에 반영
        tier_params: dict[str, object] = {}
        if feature_angle is not None:
            tier_params["bl_feature_angle"] = feature_angle

        # BETA2847 — cfMesh GUI widget 값 propagate (hex_dominant + poly).
        # 0 값은 strategist 자동값을 그대로 쓰겠다는 뜻이므로 키 추가 안 함.
        try:
            if getattr(self, "_cfm_max_cell_spin", None) is not None:
                _v = float(self._cfm_max_cell_spin.value())
                if _v > 0.0:
                    tier_params["cfmesh_max_cell_size"] = _v
            if getattr(self, "_cfm_bnd_cell_spin", None) is not None:
                _v = float(self._cfm_bnd_cell_spin.value())
                if _v > 0.0:
                    tier_params["cfmesh_boundary_cell_size"] = _v
            if getattr(self, "_cfm_bl_layers_spin", None) is not None:
                _v = int(self._cfm_bl_layers_spin.value())
                if _v > 0:
                    tier_params["cfmesh_bl_n_layers"] = _v
            if getattr(self, "_cfm_bl_ratio_spin", None) is not None:
                _v = float(self._cfm_bl_ratio_spin.value())
                if abs(_v - 1.2) > 1e-9:
                    tier_params["cfmesh_bl_thickness_ratio"] = _v
            if getattr(self, "_cfm_bl_first_spin", None) is not None:
                _v = float(self._cfm_bl_first_spin.value())
                if _v > 0.0:
                    tier_params["cfmesh_bl_max_first_layer"] = _v
        except Exception:
            pass

        # y⁺ 패널에서 계산된 첫 층 두께 자동 주입 (beta100)
        if self._computed_bl_first_thickness is not None:
            tier_params["bl_first_thickness"] = float(self._computed_bl_first_thickness)

        # Tier 4 (경계층) 엔진 콤보 → 내부 BL (snappy/cfmesh) on/off + 독립 후처리 설정
        try:
            tier4_choice = self._tier4_engine_text()
            # 내부 BL — 주 엔진이 자체적으로 BL 생성 (snappy addLayers / cfMesh boundaryLayers)
            internal_bl = tier4_choice in ("snappy_layers", "cfmesh_layers")
            # beta2290 — native_bl/native_bl_tet/poly_bl 도 독립 post engine.
            #            기존 코드는 native_bl 을 elif 에서 누락해 default
            #            "disabled" 로 떨어졌고, "auto" 도 항상 "disabled" 로
            #            덮어써서 strategist 결정 무력화. 둘 다 수정.
            _native_post_engines = (
                "native_bl", "native_bl_tet", "poly_bl_transition",
            )
            _foreign_post_engines = (
                "generate_boundary_layers",
                "refine_wall_layer",
                "snappy_addlayers",
                "extrude_mesh",
                "netgen_bl",
                "gmsh_bl",
                "pyhyp",
                "meshkit_bl",
                "su2_hexpress",
                "salome_bl",
            )
            post_engine: str | None = None
            if tier4_choice == "disabled":
                tier_params["boundary_layers_enabled"] = False
                tier_params["skip_addLayers"] = True
                post_engine = "disabled"
            elif internal_bl:
                tier_params["boundary_layers_enabled"] = True
                tier_params["skip_addLayers"] = False
            elif tier4_choice in _native_post_engines + _foreign_post_engines:
                # 독립 후처리 — 주 엔진 내부 BL 은 끔 (중복 방지)
                tier_params["boundary_layers_enabled"] = False
                tier_params["skip_addLayers"] = True
                post_engine = tier4_choice
            # else: auto → strategist 가 결정하도록 override 안 함.
            if post_engine is not None:
                tier_params["post_layers_engine"] = post_engine
        except Exception:
            pass

        # WildMesh 슬라이더 패널이 있고 tier=wildmesh면 현재 슬라이더값 병합
        if (
            tier_hint.lower() == "wildmesh"
            and self._wildmesh_param_panel is not None
        ):
            try:
                tier_params.update(self._wildmesh_param_panel.current_params())  # type: ignore[union-attr]
                # 실행 직전 스냅샷 저장 (revert 용)
                from desktop.qt_app import param_history

                param_history.push(self._wildmesh_param_panel.current_params())  # type: ignore[union-attr]
            except Exception:
                pass

        # polyDualMesh 파라미터 패널 — tier=polyhedral 일 때 병합
        if (
            tier_hint.lower() == "polyhedral"
            and self._polyhedral_param_panel is not None
        ):
            try:
                tier_params.update(self._polyhedral_param_panel.current_params())  # type: ignore[union-attr]
            except Exception:
                pass

        # Generic 엔진 파라미터 패널 — wildmesh/polyhedral 외 모든 엔진의 값 병합.
        # 패널이 보여지는 조건은 엔진 spec 이 있을 때만 이므로 해당 엔진에 맞는 키만 들어감.
        if (
            tier_hint.lower() not in ("wildmesh", "polyhedral", "auto", "")
            and self._generic_param_panel is not None
        ):
            try:
                tier_params.update(self._generic_param_panel.current_params())  # type: ignore[union-attr]
            except Exception:
                pass

        self._log(
            f"[INFO] Running pipeline — {self._input_path.name} "
            f"quality={self._quality_level.value} engine={tier_hint} "
            f"element_size={element_size or 'auto'}"
        )

        # 파이프라인 재시작 시 이전 결과/Export 비활성화
        self._pipeline_result = None
        self._quality_last_updated = None
        self._histogram_data = None
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
                # 히스토그램 초기화
                if hasattr(q, "histogram"):
                    q.histogram.update_histograms()
                # 셀 구성 바도 초기화 (이전 결과 잔존 방지)
                if hasattr(q, "cell_comp_rows"):
                    for _name, _row in q.cell_comp_rows.items():
                        try:
                            _row.set_value(0.0, "—")
                        except Exception:
                            pass
                # Job 탭 KPI 라벨 초기화
                if hasattr(self._right_column, "job_pane"):
                    try:
                        jp = self._right_column.job_pane
                        for _lbl_name in ("kpi_cells", "kpi_hex", "kpi_ram", "kpi_elapsed"):
                            _lbl = getattr(jp, _lbl_name, None)
                            if _lbl is not None and hasattr(_lbl, "set_value"):
                                _lbl.set_value("—")
                    except Exception:
                        pass
                import time
                self._quality_last_updated = time.strftime("%H:%M:%S")
                if hasattr(q, "set_stale_label"):
                    q.set_stale_label("갱신 중...")
            except Exception:
                pass

        # 뷰포트 KPI 오버레이 초기화
        if self._viewport_overlays is not None:
            try:
                self._viewport_overlays.kpi.reset()
            except Exception:
                pass

        # 상태 UI 업데이트
        import time as _time_mod
        self._pipeline_start_time = _time_mod.monotonic()  # 항상 갱신
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
            except Exception:
                pass

        # 실행 중 중복 클릭 방지 — Run 비활성화, Stop 강조
        self._set_pipeline_running(True)

        try:
            from desktop.qt_app.pipeline_worker import PipelineWorker
            self._stopping = False
            _prefer_native_flag = True  # beta26 default
            if self._prefer_native_check is not None:
                try:
                    _prefer_native_flag = bool(
                        self._prefer_native_check.isChecked(),  # type: ignore[attr-defined]
                    )
                except Exception:
                    _prefer_native_flag = True
            # beta29: native tier 선택
            _prefer_native_tier_flag = False
            if self._prefer_native_tier_check is not None:
                try:
                    _prefer_native_tier_flag = bool(
                        self._prefer_native_tier_check.isChecked(),  # type: ignore[attr-defined]
                    )
                except Exception:
                    _prefer_native_tier_flag = False
            # beta2345 — V-series 실험적 플래그를 환경변수로 worker 에 전달.
            # CLI --enable-vvv9h-apply / --enable-offplane-steiner 동등.
            try:
                import os as _os_v9
                _vvv9h_on = bool(
                    self._enable_vvv9h_apply_check.isChecked()
                    if getattr(self, "_enable_vvv9h_apply_check", None)
                    else False
                )
                _offplane_on = bool(
                    self._enable_offplane_steiner_check.isChecked()
                    if getattr(self, "_enable_offplane_steiner_check", None)
                    else False
                )
                if _vvv9h_on:
                    _os_v9.environ["AUTO_TESSELL_VVV9H_APPLY"] = "1"
                if _offplane_on:
                    _os_v9.environ["AUTO_TESSELL_OFFPLANE_STEINER"] = "1"
                # beta2351 — VVV9J/K/P GUI 체크박스 → env vars.
                _vvv9j_on = bool(
                    self._enable_vvv9j_apply_check.isChecked()
                    if getattr(self, "_enable_vvv9j_apply_check", None)
                    else False
                )
                _vvv9k_on = bool(
                    self._enable_vvv9k_apply_check.isChecked()
                    if getattr(self, "_enable_vvv9k_apply_check", None)
                    else False
                )
                _vvv9p_on = bool(
                    self._enable_vvv9p_apply_check.isChecked()
                    if getattr(self, "_enable_vvv9p_apply_check", None)
                    else False
                )
                if _vvv9j_on:
                    _os_v9.environ["AUTO_TESSELL_VVV9J_APPLY"] = "1"
                if _vvv9k_on:
                    _os_v9.environ["AUTO_TESSELL_VVV9K_APPLY"] = "1"
                if _vvv9p_on:
                    _os_v9.environ["AUTO_TESSELL_VVV9P_APPLY"] = "1"
                # C-GUI-8 / beta2419 — 신규 env wiring (CLI parity).
                if (getattr(self, "_seed_gwn_check", None)
                        and self._seed_gwn_check.isChecked()):
                    _os_v9.environ["AUTO_TESSELL_SEED_GWN"] = "1"
                if (getattr(self, "_stellar_split_check", None)
                        and self._stellar_split_check.isChecked()):
                    _os_v9.environ["AUTO_TESSELL_STELLAR_SPLIT"] = "1"
                # C-GUI-D3 / beta2594 — beta2581-2593 env flags.
                if (getattr(self, "_cvt3d_qweight_check", None)
                        and self._cvt3d_qweight_check.isChecked()):
                    _os_v9.environ["AUTO_TESSELL_CVT3D_QUALITY_WEIGHT"] = "1"
                if (getattr(self, "_lcr_auto_reduce_check", None)
                        and self._lcr_auto_reduce_check.isChecked()):
                    _os_v9.environ["AUTO_TESSELL_LCR_AUTO_REDUCE"] = "1"
                if (getattr(self, "_bl_aniso_split_check", None)
                        and self._bl_aniso_split_check.isChecked()):
                    _os_v9.environ["AUTO_TESSELL_BL_ANISO_SPLIT"] = "1"
                _ml_path = getattr(self, "_ml_smooth_model_path", None)
                if _ml_path is not None:
                    _ml_str = _ml_path.text().strip()
                    if _ml_str:
                        _os_v9.environ["AUTO_TESSELL_ML_SMOOTH_MODEL"] = _ml_str
                _bl_path = getattr(self, "_bl_predict_model_path", None)
                if _bl_path is not None:
                    _bl_str = _bl_path.text().strip()
                    if _bl_str:
                        _os_v9.environ["AUTO_TESSELL_BL_PREDICT_MODEL"] = _bl_str
                if (getattr(self, "_parallel_delaunay_check", None)
                        and self._parallel_delaunay_check.isChecked()):
                    _os_v9.environ["AUTO_TESSELL_PARALLEL_DELAUNAY"] = "1"
                # C-GUI-14 / beta2449 — BL floor ratio spin → env.
                if (getattr(self, "_bl_floor_ratio_spin", None) is not None):
                    _val = float(self._bl_floor_ratio_spin.value())
                    if abs(_val - 1.0) > 1e-6:  # default 1.0 → no env.
                        _os_v9.environ["AUTO_TESSELL_BL_FLOOR_RATIO"] = str(_val)
                # C-GUI-15 / beta2460 — patch cap spin → env.
                if (getattr(self, "_patch_cap_spin", None) is not None):
                    _pc_val = int(self._patch_cap_spin.value())
                    if _pc_val != 64:  # default 64 → no env.
                        _os_v9.environ["AUTO_TESSELL_PATCH_CAP"] = str(_pc_val)
                # C-GUI-16 / beta2461 — hex snap budget spin → env.
                if (getattr(self, "_hex_snap_budget_spin", None) is not None):
                    _hs_val = float(self._hex_snap_budget_spin.value())
                    if _hs_val > 0.0:  # 0 = off (default) → no env.
                        _os_v9.environ["AUTO_TESSELL_HEX_WWW7_BUDGET_S"] = str(_hs_val)
                # C-GUI-17 / beta2462 — Lloyd plateau threshold spin → env.
                if (getattr(self, "_lloyd_plateau_spin", None) is not None):
                    _lp_val = float(self._lloyd_plateau_spin.value())
                    if abs(_lp_val - 1e-4) > 1e-9:  # default 1e-4 → no env.
                        _os_v9.environ["AUTO_TESSELL_LLOYD_PLATEAU_THRESH"] = str(_lp_val)
            except Exception:
                pass
            worker = PipelineWorker(
                self._input_path, self._quality_level,
                output_dir=self._output_dir,
                tier_hint=tier_hint,
                mesh_type=str(self._mesh_type or "auto"),
                auto_retry=str(self._auto_retry or "off"),
                prefer_native=_prefer_native_flag,
                prefer_native_tier=_prefer_native_tier_flag,
                element_size=element_size,
                max_cells=max_cells,  # beta2300 GUI cap.
                tier_specific_params=tier_params or None,
                no_repair=bool(self._no_repair_check.isChecked())
                    if self._no_repair_check else False,
                surface_remesh=bool(self._surface_remesh_check.isChecked())
                    if self._surface_remesh_check else True,
                allow_ai_fallback=bool(self._allow_ai_fallback_check.isChecked())
                    if self._allow_ai_fallback_check else False,
                # beta2299 — GUI cross_engine_fallback 체크박스 propagate.
                cross_engine_fallback=(
                    bool(self._cross_engine_fallback_check.isChecked())
                    if getattr(self, "_cross_engine_fallback_check", None)
                    else False
                ),
                # "disabled" 는 orchestrator가 모르는 값 → "auto"로 정규화
                # (단, surface_remesh=False 면 애초에 L2 실행 안 함)
                remesh_engine=(
                    "auto" if self._remesh_engine_text() == "disabled"
                    else self._remesh_engine_text()
                ),
                # Tier 5 엔진 선택을 orchestrator로 전달 (native/checkmesh/disabled)
                validator_engine=self._tier5_engine_text(),
                # 사용자가 명시적으로 엔진을 선택했으면 (auto가 아니면) strict_tier
                # 모드로 돌려 Strategist 가 다른 tier 로 switch 하지 못하게 한다.
                strict_tier=(tier_hint.lower() != "auto"),
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
            if hasattr(worker, "intermediate_ready"):
                try:
                    worker.intermediate_ready.connect(self._on_intermediate_ready)
                except Exception:
                    pass
            worker.finished.connect(self._on_pipeline_finished)
            worker.start()
            self._worker = worker
        except Exception as e:
            self._log(f"[ERR] 파이프라인 실행 실패: {e}")
            if self._design_statusbar is not None:
                self._design_statusbar.set_phase("Failed", busy=False)
            # 실행 실패 시 버튼 상태 복원
            self._set_pipeline_running(False)

    def _set_pipeline_running(self, running: bool) -> None:  # pragma: no cover
        """파이프라인 실행 상태에 맞춰 tier strip의 버튼 그룹을 전환한다."""
        try:
            if self._tier_pipeline is not None:
                # 실행 중: running / 아이들: 이전에 실행했으면 done, 아니면 idle
                if running:
                    self._tier_pipeline.set_state("running")  # type: ignore[union-attr]
                else:
                    has_result = self._pipeline_result is not None
                    self._tier_pipeline.set_state("done" if has_result else "idle")  # type: ignore[union-attr]
        except Exception:
            pass

    def _on_reset_pipeline(self) -> None:  # pragma: no cover
        """초기화 버튼 — Tier 상태/결과를 지우고 idle 상태로 복귀."""
        if self._tier_pipeline is not None:
            try:
                for i in range(self._tier_pipeline.node_count()):  # type: ignore[union-attr]
                    self._tier_pipeline.set_status(i, "pending")  # type: ignore[union-attr]
                self._tier_pipeline.set_state("idle")  # type: ignore[union-attr]
            except Exception:
                pass
        self._pipeline_result = None
        self._log("[INFO] 파이프라인 상태 초기화")

    def _on_tier_node_clicked(self, index: int) -> None:  # pragma: no cover
        """Tier 노드 클릭 → 해당 Tier 파라미터 팝업 표시."""
        from PySide6.QtWidgets import QDialog, QVBoxLayout, QLabel, QTextBrowser, QPushButton
        from desktop.qt_app.widgets.dialog_mixin import EscDismissMixin

        class _TierParamDialog(EscDismissMixin, QDialog):
            pass

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
            spec for spec in self.TIER_PARAM_SPECS
            if self._param_is_applicable(spec[0], tier_hint, self._remesh_engine_text())
        ]
        if relevant_params:
            param_lines.append("")
            param_lines.append(f"── {tier_hint.upper()} 파라미터 (기본값) ──")
            for param_key, param_label, param_type, default in relevant_params[:12]:
                param_lines.append(f"  {param_label}: {default}")

        # 팝업 다이얼로그
        dlg = _TierParamDialog(self._qmain)
        dlg.setWindowTitle(f"Tier {index} 파라미터 (읽기 전용)")
        dlg.setMinimumSize(420, 340)
        dlg.setStyleSheet(get_dialog_qss())
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
            f"QPushButton {{ background: {PALETTE['accent']}; color: {PALETTE['accent_fg']}; "
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
            # 버튼 상태 복원
            self._set_pipeline_running(False)
            return
        self._pipeline_result = result
        success = bool(getattr(result, "success", False))

        # 실행 이력 기록 (성공·실패 무관)
        try:
            from desktop.qt_app import history as _hist

            if self._input_path is not None and self._output_dir is not None:
                entry = _hist.make_entry_from_result(
                    input_file=self._input_path,
                    output_dir=self._output_dir,
                    quality_level=self._quality_level.value,
                    result=result,
                )
                _hist.record(entry)
        except Exception:
            pass

        if success:
            self._log("[OK] 파이프라인 완료")
            # C-GUI-9 / beta2422 — integrity_suspect 시 사용자 경고 로그.
            try:
                _gen_log = getattr(result, "generator_log", None)
                _summary = getattr(_gen_log, "execution_summary", None) if _gen_log else None
                if bool(getattr(_summary, "mesh_integrity_suspect", False)):
                    self._log(
                        "[WARN] Mesh integrity suspect: 셀 수가 비정상적으로 적습니다. "
                        "입력 mesh 의 self-intersect / non-manifold 가 영향 가능. "
                        "history dialog 의 Integrity 컬럼 확인."
                    )
            except Exception:
                pass
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
            # 뷰포트 KPI 오버레이에 완료 시 실제 Tier 이름 + 총 시간 기록
            if self._viewport_overlays is not None:
                try:
                    kpi = self._viewport_overlays.kpi
                    gen_log = getattr(result, "generator_log", None)
                    if gen_log is not None:
                        summary = getattr(gen_log, "execution_summary", None)
                        selected_tier = getattr(summary, "selected_tier", None)
                        if selected_tier:
                            kpi.set_value("Tier", str(selected_tier), highlight=True)
                    total_time = getattr(result, "total_time_seconds", None)
                    if total_time is not None:
                        kpi.set_value("Time", f"{float(total_time):.1f}s")
                    # G6 / beta2606 — 실시간 quality metric KPI 추가.
                    # mean_q / min_q / grade / cells.
                    try:
                        q_report = getattr(result, "quality_report", None)
                        if q_report is not None:
                            ev = getattr(q_report, "evaluation_summary", None)
                            if ev is not None:
                                _mq = getattr(ev, "mean_quality", None)
                                _minq = getattr(ev, "min_quality", None)
                                _grade = getattr(ev, "grade", None)
                                if _mq is not None:
                                    kpi.set_value("Mean Q", f"{float(_mq):.3f}")
                                if _minq is not None:
                                    _warn_minq = float(_minq) < 0.05
                                    kpi.set_value(
                                        "Min Q", f"{float(_minq):.3f}",
                                        warn=_warn_minq,
                                    )
                                if _grade is not None:
                                    _hl = str(_grade) in ("A", "B")
                                    _warn_grade = str(_grade) in ("D", "F")
                                    kpi.set_value(
                                        "Grade", str(_grade),
                                        highlight=_hl, warn=_warn_grade,
                                    )
                        if summary is not None:
                            _nc = getattr(summary, "n_cells", None)
                            if _nc is not None and _nc > 0:
                                kpi.set_value("Cells", f"{int(_nc):,}")
                    except Exception:
                        pass
                except Exception:
                    pass
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
                        # foamToVTK 를 명시적으로 돌려 최신 polyMesh 기반 internal.vtu
                        # 가 생성되도록 보장 (Quality 탭/3D 뷰어가 stale VTU 를 잡지 않게)
                        self._ensure_fresh_foam_to_vtk(Path(out_dir))
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
            # 에러 복구 다이얼로그 — 패턴 매칭해 구체 가이드 제시
            self._show_error_recovery(str(err))
            # v0.4: Evaluator FAIL + auto_retry=off 에서 재시도 prompt
            try:
                self._maybe_show_retry_dialog(result)
            except Exception:
                pass
        # 성공·실패 모두 버튼 상태 복원
        self._set_pipeline_running(False)

    def _maybe_show_retry_dialog(self, result: object) -> None:  # pragma: no cover
        """v0.4: Evaluator FAIL 시 "재시도 / 수락" 다이얼로그 표시.

        auto_retry="off" 기본 경로에서만 (already retried 는 skip). "예" 선택 시
        현재 설정 그대로 파이프라인 재실행 (_on_run_clicked 호출).
        """
        if str(self._auto_retry).lower() != "off":
            return
        q_report = getattr(result, "quality_report", None)
        if q_report is None:
            return
        verdict = getattr(
            getattr(q_report, "evaluation_summary", None), "verdict", None,
        )
        verdict_val = getattr(verdict, "value", verdict)
        if str(verdict_val).upper() != "FAIL":
            return
        try:
            from PySide6.QtWidgets import QMessageBox
        except Exception:
            return
        recs = getattr(q_report.evaluation_summary, "recommendations", []) or []
        rec_text = "\n".join(
            f"  • {getattr(r, 'action', str(r))}" for r in recs[:4]
        )
        msg = (
            "Evaluator 가 품질 기준을 통과하지 못했습니다 (FAIL).\n\n"
            + (f"권고:\n{rec_text}\n\n" if rec_text else "")
            + "Strategist 권고 파라미터로 한 번 더 시도하시겠습니까?"
        )
        try:
            choice = QMessageBox.question(
                self,                         # type: ignore[arg-type]
                "재시도 — AutoTessell",
                msg,
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No,
            )
        except Exception:
            return
        if choice == QMessageBox.StandardButton.Yes:
            # user_decision 기록
            try:
                q_report.evaluation_summary.user_decision = "retry"
            except Exception:
                pass
            # 동일 설정으로 재실행
            try:
                self._log("[INFO] 사용자 재시도 선택 — 파이프라인 재실행")
                self._on_run_clicked()    # type: ignore[attr-defined]
            except Exception as exc:
                self._log(f"[ERR] 재실행 실패: {exc}")
        else:
            try:
                q_report.evaluation_summary.user_decision = "accept"
            except Exception:
                pass
            self._log("[INFO] 사용자가 현재 mesh 를 수락 (재시도 안 함)")

    def _ensure_fresh_foam_to_vtk(self, case_dir: Path) -> None:  # pragma: no cover
        """VTK/ 가 없거나 polyMesh보다 오래됐으면 foamToVTK를 실행한다.

        Quality 탭의 셀 구성 분류(Hex/Tet/...)는 foamToVTK가 만든 internal.vtu
        에 의존한다. 과거 실행의 stale VTU가 남아 있으면 사용자가 실제와 다른
        결과를 보게 되므로 명시적으로 regenerate 한다.
        """
        try:
            vtk_dir = case_dir / "VTK"
            poly_faces = case_dir / "constant" / "polyMesh" / "faces"
            needs_regen = True
            if vtk_dir.exists() and poly_faces.exists():
                try:
                    newest_vtu = max(
                        (p for p in vtk_dir.glob("**/internal.vtu") if p.is_file()),
                        key=lambda p: p.stat().st_mtime,
                        default=None,
                    )
                    if newest_vtu is not None:
                        needs_regen = (
                            newest_vtu.stat().st_mtime < poly_faces.stat().st_mtime
                        )
                except Exception:
                    needs_regen = True

            if not needs_regen:
                return

            # stale VTK 제거 후 foamToVTK 재실행
            if vtk_dir.exists():
                import shutil
                shutil.rmtree(str(vtk_dir), ignore_errors=True)

            from core.utils.openfoam_utils import run_openfoam
            run_openfoam("foamToVTK", case_dir)
            self._log("[INFO] foamToVTK 재생성 완료 — Quality 탭 갱신")
        except Exception as exc:
            self._log(f"[WARN] foamToVTK 실행 실패: {exc}")

    def _show_error_recovery(self, error_message: str) -> None:  # pragma: no cover
        """에러 메시지 패턴 분석 → 복구 다이얼로그 표시."""
        if self._qmain is None:
            return
        from desktop.qt_app.error_recovery import ErrorRecoveryDialog, classify_error

        classified = classify_error(error_message)
        if classified is None:
            return  # 패턴 매칭 실패 — 로그만 남김
        guide, actions = classified
        dlg = ErrorRecoveryDialog(
            parent=self._qmain,
            error_message=error_message,
            guide_text=guide,
            actions=actions,
        )
        dlg.exec()
        if dlg.chosen_action:
            self._handle_recovery_action(dlg.chosen_action)

    def _handle_recovery_action(self, key: str) -> None:  # pragma: no cover
        """복구 다이얼로그에서 선택된 액션 실행."""
        import webbrowser

        if key == "install_openfoam":
            webbrowser.open("https://www.openfoam.com/download/install-binary-linux")
            self._log("[INFO] OpenFOAM 설치 가이드 열림")
        elif key == "lower_quality":
            self._set_quality_level(QualityLevel.DRAFT)
            self._log("[INFO] 품질 Draft로 강등 — 재실행하려면 '실행' 버튼")
        elif key == "raise_quality":
            self._set_quality_level(QualityLevel.FINE)
            self._log("[INFO] 품질 Fine으로 상승 — 재실행하려면 '실행' 버튼")
        elif key == "repair_surface":
            if self._surface_remesh_check is not None:
                try:
                    self._surface_remesh_check.setChecked(True)  # type: ignore[union-attr]
                    self._log("[INFO] 표면 리메쉬 활성화 — 재실행하려면 '실행' 버튼")
                except Exception:
                    pass
        elif key == "enable_ai_fallback":
            if self._allow_ai_fallback_check is not None:
                try:
                    self._allow_ai_fallback_check.setChecked(True)  # type: ignore[union-attr]
                    self._log("[INFO] AI fallback 활성화 — 재실행하려면 '실행' 버튼")
                except Exception:
                    pass
        elif key == "issue_url":
            webbrowser.open("https://github.com/younglin90/AutoTessell/issues/new")
            self._log("[INFO] GitHub 이슈 페이지 열림")

    # 파이프라인 진행 단계 → Tier strip 인덱스 매핑
    # 오케스트레이터의 progress_callback 메시지 키워드 기준
    # Orchestrator stage 이름 → Tier strip index 매핑.
    # Tier strip 라벨: [0 Preprocess, 1 Surface, 2 Remesh, 3 Volume, 4 Layers, 5 Validate]
    # Layers(Tier4) 는 Generate 단계 내부에서 처리되므로 별도 pipeline stage 없음.
    # Evaluate 는 checkMesh + fidelity 실행 — 이게 Tier 5 (Validate) 에 해당.
    _STAGE_TO_TIER: list[tuple[str, int]] = [
        ("Analyze", 0),
        ("Preprocess", 1),
        ("Strateg", 2),
        ("Generat", 3),
        # "Evaluat" 은 Tier 5 (Validate) — 기존엔 4로 잘못 매핑돼
        # "Layers 에서 오래 걸린다" 는 오해를 일으켰다.
        ("Evaluat", 5),
        ("boundary_class", 5),
        ("postprocess_boundary", 5),
    ]

    def _on_progress_line(self, line: str) -> None:  # pragma: no cover
        """워커의 progress 시그널 — 로그 + Tier pipeline 상태 + 뷰포트 KPI 추출."""
        self._log(line)
        import re
        try:
            # 1) 명시적 "Tier N" 패턴 (숫자 인덱스)
            m = re.search(r"[Tt]ier\s*(\d+)", line)
            if m and self._tier_pipeline is not None:
                idx = int(m.group(1))
                if 0 <= idx < 6:
                    for i in range(idx):
                        self._tier_pipeline.set_status(i, "done")
                    self._tier_pipeline.set_status(idx, "active")
            # 2) 단계 키워드 매핑 — "[진행 NN%] Analyze 완료" 등
            elif self._tier_pipeline is not None:
                for keyword, stage_idx in self._STAGE_TO_TIER:
                    if keyword.lower() in line.lower():
                        # 완료 메시지면 done, 아니면 active
                        if "완료" in line or "done" in line.lower() or "finish" in line.lower():
                            for i in range(stage_idx + 1):
                                self._tier_pipeline.set_status(i, "done")
                        else:
                            for i in range(stage_idx):
                                self._tier_pipeline.set_status(i, "done")
                            self._tier_pipeline.set_status(stage_idx, "active")
                        break
        except Exception:
            pass

        # 뷰포트 KPI 오버레이 — 현재 Tier 이름 갱신 (예: "Generate 1/3")
        if self._viewport_overlays is not None:
            try:
                # "[진행 NN%] Generate 1/3", "[진행 42%] Analyze 완료" 등에서 stage 추출
                m_stage = re.search(r"\[진행\s*\d+%\]\s*([^\r\n]{1,40})", line)
                if m_stage:
                    stage = m_stage.group(1).strip()
                    self._viewport_overlays.kpi.set_value("Tier", stage, highlight=True)
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
        # 경과 시간 KPI 갱신 (Job 탭 + 뷰포트 오버레이)
        try:
            import time
            if self._pipeline_start_time > 0:
                elapsed = time.monotonic() - self._pipeline_start_time
                mins, secs = divmod(int(elapsed), 60)
                time_str = f"{mins:02d}:{secs:02d}"
                self.update_kpi(elapsed=time_str)
                if self._viewport_overlays is not None:
                    self._viewport_overlays.kpi.set_value("Time", time_str)
        except Exception:
            pass

    def _on_mesh_stats_computed(self, stats: dict) -> None:  # pragma: no cover
        """MeshViewerWidget.mesh_stats_computed Signal 수신 → KPI + Quality 탭 + 뷰포트 오버레이 갱신."""
        if not stats:
            return
        try:
            # KPI 셀 갱신
            n_cells = stats.get("n_cells", 0)
            cells_str = "—"
            if n_cells > 0:
                cells_str = f"{n_cells:,}" if n_cells < 1_000_000 else f"{n_cells / 1e6:.1f}M"
                self.update_kpi(cells=cells_str)

            hex_ratio = stats.get("hex_ratio", None)
            hex_str = "—"
            if hex_ratio is not None:
                hex_str = f"{hex_ratio * 100:.1f}%"
                self.update_kpi(hex=hex_str)

            # 뷰포트 KPI 오버레이 갱신 (셀/Hex/품질 메트릭)
            if self._viewport_overlays is not None:
                try:
                    kpi = self._viewport_overlays.kpi
                    if n_cells > 0:
                        kpi.set_value("Cells", cells_str)
                    if hex_ratio is not None:
                        kpi.set_value("Hex %", hex_str)
                    max_ar = stats.get("max_aspect_ratio")
                    if max_ar is not None:
                        kpi.set_value(
                            "Aspect", f"{float(max_ar):.2f}",
                            warn=float(max_ar) > 100.0,
                        )
                    max_sk = stats.get("max_skewness")
                    if max_sk is not None:
                        kpi.set_value(
                            "Skew", f"{float(max_sk):.2f}",
                            warn=float(max_sk) > 4.0,
                        )
                    max_no = stats.get("max_non_orthogonality")
                    if max_no is not None:
                        kpi.set_value(
                            "Non-ortho", f"{float(max_no):.1f}°",
                            warn=float(max_no) > 65.0,
                        )
                except Exception:
                    pass

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

    def _on_intermediate_ready(self, path: str, stage_label: str) -> None:  # pragma: no cover
        """중간 artifact 준비 — 뷰포트 자동 로드 + 스테이지 배지 업데이트."""
        if self._mesh_viewer is None:
            return
        from pathlib import Path

        p = Path(path)
        if not p.exists():
            self._log(f"[DBG] 중간 artifact 사라짐: {path}")
            return

        try:
            if p.is_dir():
                # polyMesh 디렉토리
                if (p / "constant" / "polyMesh").exists() or p.name == "polyMesh":
                    case_dir = p if (p / "constant" / "polyMesh").exists() else p.parent.parent
                    self._mesh_viewer.load_polymesh(str(case_dir))  # type: ignore[union-attr]
                else:
                    return
            else:
                # STL/단일 메시 파일
                self._mesh_viewer.load_mesh(str(p))  # type: ignore[union-attr]

            self._log(f"[INFO] 중간 프리뷰 로드: {stage_label} ← {p.name}")
            # Tier/뷰포트 오버레이에 스테이지 표기
            if self._viewport_overlays is not None:
                try:
                    self._viewport_overlays.kpi.set_value(
                        "Tier", f"[Preview] {stage_label}", highlight=True,
                    )
                except Exception:
                    pass
        except Exception as e:
            self._log(f"[DBG] 중간 프리뷰 로드 실패: {e}")

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

            # ── 후처리: OpenFOAM case 템플릿 (system/0.orig) ──
            if opts.get("foam_template", False):
                self._export_foam_template(export_target_dir)

            # ── 후처리: 리포트 PDF ────────────────────────────
            if opts.get("report_pdf", False):
                self._export_report_pdf(export_target_dir)

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
        """beta2282 — mesh_exporter (17 formats) 통해 polyMesh → 다양한 포맷.

        이전: 5 format ext_map. 이후: full mesh_exporter routing (17 formats).
        """
        # Path 1 — polyMesh 가 있으면 mesh_exporter 사용 (17 formats 지원).
        poly_dir = self._output_dir / "constant" / "polyMesh"
        if poly_dir.exists() and (poly_dir / "points").exists():
            try:
                from core.utils.mesh_exporter import (
                    export_mesh as _exp,
                    _FORMAT_EXTENSIONS as _F_EXT,
                )
                ext = _F_EXT.get(fmt, f".{fmt}")
                dst_file = target_dir / f"mesh{ext}"
                result = _exp(self._output_dir, output_path=dst_file, fmt=fmt)
                if result is not None and result.exists():
                    self._log(f"[OK] {fmt.upper()} 저장 (mesh_exporter): {dst_file}")
                    return
            except Exception as exc:
                self._log(f"[WARN] mesh_exporter 실패 ({exc}), meshio fallback 시도")

        # Path 2 — fallback: 기존 meshio convert (legacy ext_map).
        src_file: Path | None = None
        for pattern in ("**/*.vtu", "**/*.vtk", "**/*.msh"):
            candidates = list(self._output_dir.glob(pattern))
            if candidates:
                src_file = max(candidates, key=lambda p: p.stat().st_mtime)
                break
        if src_file is None:
            raise RuntimeError(
                f"변환할 mesh 파일을 찾을 수 없습니다 (format={fmt}).\n"
                "파이프라인이 polyMesh / VTU / VTK / MSH 를 생성했는지 확인하세요."
            )
        ext_map = {
            "vtu": ".vtu", "vtk": ".vtk", "vtp": ".vtp", "xdmf": ".xdmf",
            "cgns": ".cgns", "su2": ".su2",
            "nastran": ".bdf", "abaqus": ".inp", "tecplot": ".dat",
            "fluent": ".msh", "gmsh": ".msh",
            "gmsh22": ".msh", "gmsh40": ".msh", "gmsh41": ".msh",
            "medit": ".mesh", "stl": ".stl", "obj": ".obj", "ply": ".ply",
        }
        ext = ext_map.get(fmt, f".{fmt}")
        dst_file = target_dir / f"mesh{ext}"
        try:
            import meshio
        except ImportError:
            raise RuntimeError("meshio 미설치 — pip install meshio") from None
        mesh = meshio.read(str(src_file))
        meshio.write(str(dst_file), mesh)
        self._log(f"[OK] {fmt.upper()} 저장 (meshio fallback): {dst_file}")

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

    def _export_report_pdf(self, target_dir: Path) -> None:  # pragma: no cover
        """1-페이지 PDF 리포트 생성 — 메타 + 스크린샷 + 3 히스토그램 + 합격 판정."""
        from desktop.qt_app.report_pdf import ReportData, write_pdf

        # C-GUI-10 / beta2427 — selected tier 의 native_bl_phase2 lookup helper.
        def _bl_lookup(res, attr_name):
            try:
                gl = getattr(res, "generator_log", None)
                summary_local = getattr(gl, "execution_summary", None) if gl else None
                if not summary_local:
                    return None
                for at in getattr(summary_local, "tiers_attempted", []) or []:
                    if (getattr(at, "tier", "") == getattr(summary_local, "selected_tier", "")
                            and getattr(at, "status", "") == "success"):
                        bl = getattr(at, "native_bl_phase2", None)
                        return getattr(bl, attr_name, None) if bl else None
            except Exception:
                return None
            return None

        result = self._pipeline_result
        hist_data = self._histogram_data or {}

        # 임시 스크린샷 촬영
        screenshot_path: str | None = None
        if self._mesh_viewer is not None:
            try:
                tmp_png = target_dir / "_report_screenshot.png"
                # Qt grab 방식 (WYSIWYG) — _on_screenshot 로직을 inline
                widget = self._mesh_viewer
                pix = widget.grab()
                if not pix.isNull():
                    pix.save(str(tmp_png), "PNG")
                    screenshot_path = str(tmp_png)
            except Exception:
                pass

        # 품질 메트릭 — Quality 탭에서 이미 계산된 값 사용
        quality_report = getattr(result, "quality_report", None) if result else None
        checkmesh = getattr(quality_report, "check_mesh", None) if quality_report else None
        # beta2355 — fidelity 에서 hausdorff + n_self_intersect_pre capture (P2.6 chain).
        fidelity = (
            getattr(quality_report, "geometry_fidelity", None)
            if quality_report else None
        )

        data = ReportData(
            input_file=str(self._input_path) if self._input_path else "",
            output_dir=str(self._output_dir) if self._output_dir else "",
            tier_used=(
                getattr(getattr(result, "generator_log", None), "execution_summary", None)
                and getattr(result.generator_log.execution_summary, "selected_tier", "")
                or ""
            ),
            quality_level=self._quality_level.value,
            total_time_seconds=float(getattr(result, "total_time_seconds", 0.0) or 0.0),
            n_cells=int(getattr(checkmesh, "cells", 0) or 0),
            n_points=int(getattr(checkmesh, "points", 0) or 0),
            max_aspect_ratio=getattr(checkmesh, "max_aspect_ratio", None),
            max_skewness=getattr(checkmesh, "max_skewness", None),
            max_non_orthogonality=getattr(checkmesh, "max_non_orthogonality", None),
            negative_volumes=getattr(checkmesh, "negative_volumes", None),
            min_cell_volume=getattr(checkmesh, "min_cell_volume", None),
            # beta2355 — Hausdorff + pre-BL SI 도 PDF 에 포함.
            hausdorff_distance=getattr(fidelity, "hausdorff_distance", None),
            hausdorff_relative=getattr(fidelity, "hausdorff_relative", None),
            n_self_intersect_pre=getattr(fidelity, "n_self_intersect_pre", None),
            # C-GUI-2 / beta2413 — mesh_integrity_suspect (ExecutionSummary 경유).
            mesh_integrity_suspect=bool(
                getattr(
                    getattr(getattr(result, "generator_log", None),
                            "execution_summary", None),
                    "mesh_integrity_suspect", False,
                )
                or False,
            ),
            # C-GUI-10 / beta2427 — BL stats (selected attempt 의 native_bl_phase2).
            bl_n_prism_cells=int(
                _bl_lookup(result, "n_prism_cells") or 0,
            ),
            bl_lcr_n_reduced_verts=int(
                _bl_lookup(result, "lcr_n_reduced_verts") or 0,
            ),
            bl_aniso_split_n_would_split=int(
                _bl_lookup(result, "aniso_split_n_would_split") or 0,
            ),
            hist_aspect=hist_data.get("aspect_ratio", []) or [],
            hist_skew=hist_data.get("skewness", []) or [],
            hist_non_ortho=hist_data.get("non_orthogonality", []) or [],
            screenshot_path=screenshot_path,
        )

        pdf_path = target_dir / "mesh_report.pdf"
        try:
            ok = write_pdf(data, pdf_path)
            if ok:
                self._log(f"[OK] PDF 리포트 생성: {pdf_path}")
            else:
                self._log("[WARN] PDF 생성 실패 (matplotlib 미설치?)")
        except Exception as e:
            self._log(f"[WARN] PDF 생성 중 오류: {e}")
        finally:
            # 임시 스크린샷 정리
            if screenshot_path:
                try:
                    Path(screenshot_path).unlink(missing_ok=True)
                except Exception:
                    pass

    def _export_foam_template(self, target_dir: Path) -> None:  # pragma: no cover
        """OpenFOAM case 템플릿 (system/*, 0.orig/) 생성.

        polyMesh 가 target_dir 또는 target_dir/constant/polyMesh 에 있어야 동작.
        """
        from desktop.qt_app.foam_templates import write_case_template

        # polyMesh 상위 디렉토리 찾기 = case_dir
        candidates = [target_dir, target_dir / "constant"]
        case_dir = None
        for c in candidates:
            if (c.parent / "constant" / "polyMesh").exists():
                case_dir = c.parent
                break
            if (c / "polyMesh").exists():
                case_dir = c.parent if c.name == "constant" else c
                break
        if case_dir is None:
            case_dir = target_dir  # polyMesh 없어도 템플릿은 생성

        try:
            written = write_case_template(case_dir)
            if written:
                self._log(
                    f"[OK] OpenFOAM 템플릿 생성 ({len(written)}개): "
                    + ", ".join(Path(p).name for p in written)
                )
            else:
                self._log("[INFO] OpenFOAM 템플릿 — 기존 파일 유지 (덮어쓰기 없음)")
        except Exception as e:
            self._log(f"[WARN] OpenFOAM 템플릿 생성 실패: {e}")

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

    @staticmethod
    def _classify_log_level(raw: str) -> str:
        """로그 라인 → 레벨 (ALL 필터용 분류).

        정규화 규칙:
        - [ERR]/[ERROR]/[오류] → ERR
        - [WARN]/[WARNING]/[경고] → WARN
        - [DBG]/[DEBUG] → DBG
        - [OK]/[INFO]/[진행]/기타 → INFO
        """
        u = raw.upper()
        if "[ERR]" in u or "[ERROR]" in u or "[오류]" in raw:
            return "ERR"
        if "[WARN]" in u or "[WARNING]" in u or "[경고]" in raw:
            return "WARN"
        if "[DBG]" in u or "[DEBUG]" in u:
            return "DBG"
        # OK/INFO/진행 + level 태그 없는 일반 메시지는 모두 INFO로 분류
        return "INFO"

    def _refilter_log(self) -> None:  # pragma: no cover
        if self._log_edit is None or not hasattr(self, "_all_log_lines"):
            return
        job = self._right_column.job_pane
        search = (job.log_search.text() or "").strip().lower()
        levels = self._active_log_levels
        keep = []
        for raw in self._all_log_lines:
            if "ALL" not in levels:
                line_level = self._classify_log_level(raw)
                if line_level not in levels:
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
        self._update_log_chip_counts()

    def _update_log_chip_counts(self) -> None:  # pragma: no cover
        """로그 필터 chip의 카운트 (INFO/WARN/ERR/DBG/ALL)를 갱신."""
        if self._right_column is None or not hasattr(self, "_all_log_lines"):
            return
        try:
            job = self._right_column.job_pane
        except Exception:
            return
        counts = {"INFO": 0, "WARN": 0, "ERR": 0, "DBG": 0}
        for raw in self._all_log_lines:
            lvl = self._classify_log_level(raw)
            if lvl in counts:
                counts[lvl] += 1
        total = len(self._all_log_lines)
        try:
            job.chip_all.set_count(total)
            job.chip_info.set_count(counts["INFO"])
            job.chip_warn.set_count(counts["WARN"])
            job.chip_err.set_count(counts["ERR"])
            job.chip_dbg.set_count(counts["DBG"])
        except Exception:
            pass

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
            # Peak RAM — 현재 프로세스의 RSS 피크를 추적해 Job 탭 KPI로 노출
            try:
                proc = psutil.Process()
                rss_mb = proc.memory_info().rss / (1024 * 1024)
                if not hasattr(self, "_peak_ram_mb"):
                    self._peak_ram_mb = rss_mb
                else:
                    self._peak_ram_mb = max(self._peak_ram_mb, rss_mb)
                if self._right_column is not None:
                    peak = self._peak_ram_mb
                    if peak >= 1024:
                        ram_str = f"{peak / 1024:.2f} GB"
                    else:
                        ram_str = f"{peak:.0f} MB"
                    self._right_column.job_pane.kpi_ram.set_value(ram_str)
            except Exception:
                pass
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


# GUI 짧은 키 → canonical tier 이름 매핑 (engine_policy 판정용)
_GUI_ENGINE_CANONICAL: dict[str, str] = {
    "auto": "auto",
    "tetwild": "tier2_tetwild",
    "wildmesh": "tier_wildmesh",
    "netgen": "tier05_netgen",
    "snappy": "tier1_snappy",
    "cfmesh": "tier15_cfmesh",
    "algohex": "tier_algohex",
    "robust_hex": "tier_robust_hex",
    "hex_classy": "tier_hex_classy_blocks",
    "cinolib_hex": "tier_cinolib_hex",
    "gmsh_hex": "tier_gmsh_hex",
    "hohqmesh": "tier_hohqmesh",
    "mmg3d": "tier_mmg3d",
    "meshpy": "tier_meshpy",
    "jigsaw": "tier_jigsaw",
    "jigsaw_fallback": "tier_jigsaw_fallback",
    "core": "tier0_core",
    "polyhedral": "tier_polyhedral",
    "voro_poly": "tier_voro_poly",
    "classy_blocks": "tier_classy_blocks",
    "2d": "tier0_2d_meshpy",
}


def _resolve_engine_canonical(gui_key: str) -> str:
    """GUI 엔진 키(짧은 이름)를 canonical tier 이름으로 변환."""
    return _GUI_ENGINE_CANONICAL.get(gui_key, gui_key)


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
