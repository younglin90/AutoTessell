"""엔진별 파라미터 spec 레지스트리.

각 tier (엔진) 가 받을 수 있는 파라미터들을 선언적으로 정의한다.
`GenericEngineParamPanel` 이 이 spec 으로 UI를 자동 생성한다.

파라미터 명명 규칙: `<engine>_<param>` 또는 `tier_specific_params` 에서 쓰는 기존 키.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class EngineParamSpec:
    """단일 파라미터 정의."""

    key: str                                      # tier_specific_params 키
    label: str                                    # UI 라벨
    kind: str                                     # "float" | "int" | "bool" | "choice" | "str"
    default: Any
    doc: str = ""                                 # ⓘ 팝업 설명 (multi-line OK)
    # 숫자 파라미터
    min_val: float | None = None
    max_val: float | None = None
    step: float | None = None
    log_scale: bool = False                       # float 에만 의미
    # 선택 파라미터
    choices: list[tuple[str, str]] = field(default_factory=list)  # [(value, display), ...]


# ---------------------------------------------------------------------------
# 엔진별 spec (WildMesh / Polyhedral 은 전용 panel 로 따로 처리됨)
# ---------------------------------------------------------------------------


ENGINE_PARAM_REGISTRY: dict[str, list[EngineParamSpec]] = {
    # ------------------------------------------------------------------
    # TetWild (fTetWild 의 원조)
    # ------------------------------------------------------------------
    "tetwild": [
        EngineParamSpec(
            "tetwild_epsilon", "epsilon", "float", 1e-3,
            min_val=1e-4, max_val=1e-1, log_scale=True,
            doc=(
                "envelope 두께 (bbox 대각선 비율).\n"
                "작을수록 형상 정확 / 시간 증가.\n"
                "draft=2e-2, std=1e-3, fine=5e-4 권장."
            ),
        ),
        EngineParamSpec(
            "tetwild_stop_energy", "stop_energy", "float", 10.0,
            min_val=3.0, max_val=50.0,
            doc=(
                "에너지 최적화 종료 조건. 낮을수록 고품질.\n"
                "5 이하는 수렴 오래 걸림, 20+ 는 sliver 잔존."
            ),
        ),
        EngineParamSpec(
            "tetwild_edge_length", "edge_length (abs)", "float", 0.0,
            min_val=0.0, max_val=2.0,
            doc="절대 타깃 엣지 길이. 0 = 자동 (edge_length_fac 사용).",
        ),
        EngineParamSpec(
            "tetwild_edge_length_fac", "edge_length_fac", "float", 0.1,
            min_val=0.01, max_val=0.5,
            doc="bbox 대각선 대비 엣지 길이 비율. edge_length 가 0일 때 사용.",
        ),
        EngineParamSpec(
            "tw_max_iterations", "max_iterations", "int", 80,
            min_val=10, max_val=500,
            doc="최대 최적화 반복 횟수.",
        ),
    ],

    # ------------------------------------------------------------------
    # Netgen
    # ------------------------------------------------------------------
    "netgen": [
        EngineParamSpec(
            "netgen_grading", "grading", "float", 0.3,
            min_val=0.1, max_val=1.0,
            doc=(
                "셀 크기 전이 부드러움 (0.1~1.0).\n"
                "작을수록 급격한 전이 (조밀→성긴) 허용, 클수록 완만."
            ),
        ),
        EngineParamSpec(
            "netgen_curvaturesafety", "curvature_safety", "float", 2.0,
            min_val=0.5, max_val=10.0,
            doc="곡률 기반 세분화 안전 계수. 클수록 곡면에 조밀한 메쉬.",
        ),
        EngineParamSpec(
            "netgen_segmentsperedge", "segments_per_edge", "float", 1.0,
            min_val=0.5, max_val=5.0,
            doc="엣지당 평균 분할 수.",
        ),
        EngineParamSpec(
            "netgen_closeedgefac", "close_edge_fac", "float", 2.0,
            min_val=0.5, max_val=10.0,
            doc="가까운 엣지 refinement 계수.",
        ),
        EngineParamSpec(
            "ng_max_h", "max_h (auto=0)", "float", 0.0,
            min_val=0.0, max_val=2.0,
            doc="최대 셀 크기 상한. 0 = 자동.",
        ),
        EngineParamSpec(
            "ng_min_h", "min_h (auto=0)", "float", 0.0,
            min_val=0.0, max_val=1.0,
            doc="최소 셀 크기 하한. 0 = 자동.",
        ),
        EngineParamSpec(
            "ng_fineness", "fineness", "float", 0.5,
            min_val=0.0, max_val=1.0,
            doc="Netgen 전체 fineness (0=성긴 … 1=조밀).",
        ),
        EngineParamSpec(
            "ng_second_order", "second_order", "bool", False,
            doc="2차 요소 (curved mid-edge node) 생성.",
        ),
    ],

    # ------------------------------------------------------------------
    # snappyHexMesh
    # ------------------------------------------------------------------
    "snappy": [
        EngineParamSpec(
            "snappy_castellated_level", "castellated_level", "int", 2,
            min_val=0, max_val=6,
            doc=(
                "표면 근처 octree 세분화 레벨.\n"
                "0=세분화 없음, 4+ 는 메모리 급증."
            ),
        ),
        EngineParamSpec(
            "snappy_snap_tolerance", "snap_tolerance", "float", 2.0,
            min_val=0.5, max_val=10.0,
            doc="표면에 snap 할 때 허용 오차 (셀 크기 비율).",
        ),
        EngineParamSpec(
            "snappy_snap_iterations", "snap_iterations", "int", 5,
            min_val=1, max_val=50,
            doc="snap 반복 횟수. 많을수록 표면 정확도 ↑.",
        ),
        EngineParamSpec(
            "snappy_max_local_cells", "max_local_cells", "int", 1_000_000,
            min_val=10_000, max_val=50_000_000,
            doc="로컬(프로세스당) 최대 셀 수.",
        ),
        EngineParamSpec(
            "snappy_max_global_cells", "max_global_cells", "int", 10_000_000,
            min_val=100_000, max_val=500_000_000,
            doc="전체 최대 셀 수 (메모리 제한용).",
        ),
        EngineParamSpec(
            "snappy_min_refinement_cells", "min_refinement_cells", "int", 10,
            min_val=0, max_val=1000,
            doc="최소 refinement 셀 수.",
        ),
        EngineParamSpec(
            "snappy_n_cells_between_levels", "cells_between_levels", "int", 3,
            min_val=1, max_val=10,
            doc="레벨 간 완충 셀 수. 클수록 부드러운 전이.",
        ),
        EngineParamSpec(
            "snappy_snap_smooth_patch", "snap_smooth_patch", "int", 3,
            min_val=0, max_val=20,
            doc="patch smoothing 반복 수.",
        ),
        EngineParamSpec(
            "snappy_snap_relax_iter", "snap_relax_iter", "int", 5,
            min_val=1, max_val=50,
            doc="relaxation 반복 수.",
        ),
        EngineParamSpec(
            "snappy_feature_snap_iter", "feature_snap_iter", "int", 10,
            min_val=0, max_val=50,
            doc="feature edge snap 반복 수.",
        ),
        EngineParamSpec(
            "skip_addLayers", "skip addLayers", "bool", False,
            doc="경계층 생성 건너뛰기. 복잡한 형상에서 ON 권장.",
        ),
    ],

    # ------------------------------------------------------------------
    # cfMesh
    # ------------------------------------------------------------------
    "cfmesh": [
        EngineParamSpec(
            "cfmesh_max_cell_size", "max_cell_size", "float", 0.1,
            min_val=0.001, max_val=2.0,
            doc="최대 셀 크기 (형상 bbox 대비 0.1 정도 권장).",
        ),
        EngineParamSpec(
            "cfmesh_surface_refinement", "surface_refinement", "int", 0,
            min_val=0, max_val=5,
            doc=(
                "표면 refinement 레벨. 각 레벨마다 boundary cell 이 "
                "2^-N 배로 작아져 셀 수가 3D 에서 약 4배씩 증가.\n"
                "• 0 (기본, 권장): 표면 refinement 없음, 빠름 (~수십만 셀)\n"
                "• 1: ~백만 셀, 중간 속도\n"
                "• 2 이상: 수백만 셀 이상, 매우 느림\n"
                "크게 높이면 cfMesh 가 수 분 이상 걸릴 수 있음."
            ),
        ),
        EngineParamSpec(
            "cfmesh_local_refinement", "local_refinement", "int", 0,
            min_val=0, max_val=5,
            doc="국소 refinement 레벨 (patch별 세밀 제어용).",
        ),
        EngineParamSpec(
            "cf_surface_feature_angle", "surface_feature_angle", "float", 30.0,
            min_val=5.0, max_val=180.0,
            doc="feature 로 간주할 각도 임계.",
        ),
    ],

    # ------------------------------------------------------------------
    # MMG3D
    # ------------------------------------------------------------------
    "mmg3d": [
        EngineParamSpec(
            "mmg3d_hmin", "hmin (auto=0)", "float", 0.0,
            min_val=0.0, max_val=1.0,
            doc="최소 엣지 길이. 0 = 자동.",
        ),
        EngineParamSpec(
            "mmg3d_hmax", "hmax (auto=0)", "float", 0.0,
            min_val=0.0, max_val=2.0,
            doc="최대 엣지 길이. 0 = 자동.",
        ),
        EngineParamSpec(
            "mmg3d_hausd", "hausd", "float", 0.01,
            min_val=0.0001, max_val=0.1, log_scale=True,
            doc="Hausdorff 거리 허용치 (형상 보존).",
        ),
        EngineParamSpec(
            "mmg3d_ar", "feature_angle (ar)", "float", 60.0,
            min_val=0.0, max_val=180.0,
            doc="이 각도 이상의 edge를 feature 로 보존.",
        ),
        EngineParamSpec(
            "mmg3d_optim", "optim", "bool", False,
            doc="추가 최적화 pass. 품질↑ 시간↑.",
        ),
    ],

    # ------------------------------------------------------------------
    # MeshPy (TetGen)
    # ------------------------------------------------------------------
    "meshpy": [
        EngineParamSpec(
            "meshpy_min_angle", "min_angle", "float", 25.0,
            min_val=5.0, max_val=40.0,
            doc="최소 dihedral angle. 클수록 고품질 tet.",
        ),
        EngineParamSpec(
            "meshpy_max_volume", "max_volume (auto=0)", "float", 0.0,
            min_val=0.0, max_val=1.0,
            doc="셀당 최대 부피. 0 = 자동.",
        ),
    ],

    # ------------------------------------------------------------------
    # JIGSAW
    # ------------------------------------------------------------------
    "jigsaw": [
        EngineParamSpec(
            "jigsaw_hmax", "hmax (auto=0)", "float", 0.0,
            min_val=0.0, max_val=2.0,
            doc="최대 엣지 길이. 0 = 자동.",
        ),
        EngineParamSpec(
            "jigsaw_hmin", "hmin (auto=0)", "float", 0.0,
            min_val=0.0, max_val=1.0,
            doc="최소 엣지 길이. 0 = 자동.",
        ),
        EngineParamSpec(
            "jigsaw_optm_iter", "optm_iter", "int", 32,
            min_val=4, max_val=256,
            doc="ODT 최적화 반복 수.",
        ),
    ],

    # ------------------------------------------------------------------
    # Geogram CDT
    # ------------------------------------------------------------------
    "core": [
        EngineParamSpec(
            "core_quality", "quality", "float", 2.0,
            min_val=1.0, max_val=10.0,
            doc="Delaunay quality factor.",
        ),
        EngineParamSpec(
            "core_max_vertices", "max_vertices (auto=0)", "int", 0,
            min_val=0, max_val=10_000_000,
            doc="최대 정점 수 제한. 0 = 무제한.",
        ),
    ],

    # ------------------------------------------------------------------
    # GMSH Hex
    # ------------------------------------------------------------------
    "gmsh_hex": [
        EngineParamSpec(
            "gmsh_hex_char_length_factor", "char_length_factor", "float", 1.0,
            min_val=0.1, max_val=5.0,
            doc="요소 크기 scaling factor.",
        ),
        EngineParamSpec(
            "gmsh_hex_algorithm", "algorithm", "choice", "8",
            choices=[
                ("1", "MeshAdapt"), ("2", "Automatic"), ("5", "Delaunay"),
                ("6", "Frontal-Delaunay"), ("8", "Frontal-Delaunay for Quads"),
                ("9", "Packing of Parallelograms"),
            ],
            doc="2D 메쉬 알고리즘. 8 (Quads) 가 hex 재조합에 적합.",
        ),
        EngineParamSpec(
            "gmsh_hex_recombine_all", "recombine_all", "bool", True,
            doc="모든 tri → quad 재조합. hex 비율에 필수.",
        ),
    ],

    # ------------------------------------------------------------------
    # Cinolib Hex
    # ------------------------------------------------------------------
    "cinolib_hex": [
        EngineParamSpec(
            "cinolib_hex_scale", "scale", "float", 1.0,
            min_val=0.1, max_val=10.0,
            doc="메쉬 크기 scaling.",
        ),
    ],

    # ------------------------------------------------------------------
    # Voronoi Polyhedral
    # ------------------------------------------------------------------
    "voro_poly": [
        EngineParamSpec(
            "voro_n_seeds", "n_seeds", "int", 2000,
            min_val=100, max_val=200_000,
            doc="Voronoi seed 수. 많을수록 조밀 + 느림.",
        ),
        EngineParamSpec(
            "voro_relax_iters", "relax_iters", "int", 10,
            min_val=0, max_val=100,
            doc="Lloyd relaxation 반복 수. 클수록 균등 셀.",
        ),
    ],

    # ------------------------------------------------------------------
    # HOHQMesh
    # ------------------------------------------------------------------
    "hohqmesh": [
        EngineParamSpec(
            "hohq_dx", "grid_spacing (auto=0)", "float", 0.0,
            min_val=0.0, max_val=2.0,
            doc="배경 격자 간격. 0 = 자동.",
        ),
        EngineParamSpec(
            "hohq_n_cells", "n_cells_per_dir (auto=0)", "int", 0,
            min_val=0, max_val=1000,
            doc="방향당 셀 수. 0 = 자동.",
        ),
        EngineParamSpec(
            "hohq_poly_order", "poly_order", "int", 1,
            min_val=1, max_val=8,
            doc="spectral element 다항식 차수.",
        ),
        EngineParamSpec(
            "hohq_extrusion_dir", "extrusion_dir", "choice", "3",
            choices=[("1", "X"), ("2", "Y"), ("3", "Z")],
            doc="2.5D extrusion 방향.",
        ),
    ],

    # ------------------------------------------------------------------
    # AlgoHex
    # ------------------------------------------------------------------
    "algohex": [
        EngineParamSpec(
            "algohex_pipeline", "pipeline", "choice", "hexme",
            choices=[
                ("hexme", "HexMe (기본)"),
                ("tet2hex", "Tet2Hex"),
                ("algohex", "AlgoHex full"),
            ],
            doc="내부 frame-field 파이프라인 선택.",
        ),
        EngineParamSpec(
            "algohex_tet_size", "tet_size", "float", 0.05,
            min_val=0.005, max_val=0.5,
            doc="선행 tet mesh 의 타깃 엣지 길이. 작을수록 고해상도.",
        ),
    ],

    # ------------------------------------------------------------------
    # Robust Pure Hex
    # ------------------------------------------------------------------
    "robust_hex": [
        EngineParamSpec(
            "robust_hex_n_cells", "n (octree levels)", "int", 3,
            min_val=1, max_val=6,
            doc="Octree 해상도 레벨. 4 이상은 메모리/시간 폭증.",
        ),
        EngineParamSpec(
            "robust_hex_hausdorff", "hausdorff_ratio", "float", 0.02,
            min_val=0.001, max_val=0.2, log_scale=True,
            doc="형상 충실도 허용치 (bbox 대비).",
        ),
        EngineParamSpec(
            "robust_hex_slim_iter", "slim_iter", "int", 50,
            min_val=10, max_val=500,
            doc="SLIM geometric optimization 반복 수.",
        ),
        EngineParamSpec(
            "robust_hex_timeout", "timeout (s)", "int", 600,
            min_val=30, max_val=3600,
            doc="전체 실행 제한 시간 (초).",
        ),
    ],

    # ------------------------------------------------------------------
    # HexClassyBlocks
    # ------------------------------------------------------------------
    "hex_classy": [
        EngineParamSpec(
            "classy_cell_size", "cell_size (auto=0)", "float", 0.0,
            min_val=0.0, max_val=2.0,
            doc="블록당 타깃 셀 크기. 0 = 자동.",
        ),
        EngineParamSpec(
            "hex_classy_use_snappy", "fallback to snappy", "bool", True,
            doc="분석 실패 시 snappyHexMesh fallback 허용.",
        ),
    ],

    # ------------------------------------------------------------------
    # classy_blocks (single)
    # ------------------------------------------------------------------
    "classy_blocks": [
        EngineParamSpec(
            "classy_cell_size", "cell_size (auto=0)", "float", 0.0,
            min_val=0.0, max_val=2.0,
            doc="블록당 타깃 셀 크기. 0 = 자동.",
        ),
    ],

    # ------------------------------------------------------------------
    # Salome SMESH (volume tier — Salome binary 설치 필요)
    # ------------------------------------------------------------------
    "salome_smesh": [
        EngineParamSpec(
            "salome_smesh_algo", "algorithm", "choice", "netgen_tet",
            choices=[
                ("netgen_tet", "NETGEN (tet, 기본)"),
                ("ghs3d",      "GHS3D / MG-Tetra (상용)"),
                ("hexotic",    "Hexotic / MG-Hexa (상용 hex)"),
            ],
            doc=(
                "Salome SMESH 내부 알고리즘 선택.\n"
                "• netgen_tet: Salome 의 NETGEN plugin (무료, 안정)\n"
                "• ghs3d: MeshGems MG-Tetra — 상용 라이선스 필요\n"
                "• hexotic: MeshGems MG-Hexa — 상용"
            ),
        ),
        EngineParamSpec(
            "salome_smesh_max_size", "max_size", "float", 0.1,
            min_val=0.001, max_val=2.0,
            doc="최대 셀 크기 (bbox 상대). Salome NETGEN 의 SetMaxSize 값.",
        ),
        EngineParamSpec(
            "salome_smesh_timeout", "timeout (s)", "int", 600,
            min_val=60, max_val=7200,
            doc="Salome subprocess 실행 최대 시간 (초).",
        ),
    ],

    # ------------------------------------------------------------------
    # Layers 엔진 — 주 엔진 무관 BL 후처리 (Tier 4 콤보로 선택)
    # ------------------------------------------------------------------
    "layers_post": [
        EngineParamSpec(
            "post_layers_num_layers", "num_layers", "int", 3,
            min_val=1, max_val=20,
            doc="생성할 prism layer 의 개수.",
        ),
        EngineParamSpec(
            "post_layers_growth_ratio", "growth_ratio", "float", 1.2,
            min_val=1.05, max_val=2.0,
            doc=(
                "인접 layer 두께 비율 (thickness[i+1] / thickness[i]).\n"
                "1.2 = 20% 씩 성장 (표준).\n"
                "작을수록 (1.05~1.15) 부드러운 전이, 클수록 (1.3~1.5) 빠른 성장."
            ),
        ),
        EngineParamSpec(
            "post_layers_first_thickness", "first_thickness", "float", 1e-3,
            min_val=1e-6, max_val=1e-1, log_scale=True,
            doc=(
                "첫 번째 layer 의 두께 (bbox 대비 절대값).\n"
                "y+ 목표에 따라 결정 (예: y+~1 → 1e-5, y+~30 → 1e-3)."
            ),
        ),
        EngineParamSpec(
            "post_layers_refine_wall_fraction",
            "refine_wall_fraction", "float", 0.3,
            min_val=0.05, max_val=0.95,
            doc=(
                "refine_wall_layer 엔진 전용: 벽 근처 cell 을 이 비율로 분할.\n"
                "0.3 → 벽 근처 cell 이 원래 크기의 30% 로 조밀화."
            ),
        ),
        # ─── generate_boundary_layers (cfMesh post) 전용 고급 옵션 ────────
        EngineParamSpec(
            "post_layers_allow_discontinuity",
            "allow_discontinuity (cfMesh)", "bool", False,
            doc=(
                "cfMesh generate_boundary_layers 전용: 인접 patch 간 layer 수 불일치 허용.\n"
                "✔ multi-patch 각기 다른 layer 수 지정 시 필요\n"
                "✘ (기본) uniform layer, 품질 균일"
            ),
        ),
        EngineParamSpec(
            "post_layers_optimise_layer",
            "optimise_layer (cfMesh)", "bool", True,
            doc="cfMesh: layer 품질 최적화 pass 활성화.",
        ),
        EngineParamSpec(
            "post_layers_untangle_layers",
            "untangle_layers (cfMesh)", "bool", True,
            doc=(
                "cfMesh: inverted/tangled layer cells 탐지 후 untangling 수행.\n"
                "고곡률/얇은 벽에서 품질 향상."
            ),
        ),
        EngineParamSpec(
            "post_layers_n_smooth_normals",
            "n_smooth_normals", "int", 5,
            min_val=0, max_val=50,
            doc="cfMesh: vertex normal smoothing 반복 수. 많을수록 부드러운 layer 표면.",
        ),
        EngineParamSpec(
            "post_layers_n_smooth_surface_normals",
            "n_smooth_surface_normals", "int", 5,
            min_val=0, max_val=50,
            doc="cfMesh: surface-wide normal smoothing 반복 수.",
        ),
        EngineParamSpec(
            "post_layers_feature_size_factor",
            "feature_size_factor", "float", 0.3,
            min_val=0.01, max_val=2.0,
            doc=(
                "cfMesh: feature edge 근처 layer 크기 조절 factor.\n"
                "작을수록 날카로운 feature 보존, 클수록 매끄러운 전이."
            ),
        ),
        EngineParamSpec(
            "post_layers_at_bottleneck",
            "n_layers_at_bottleneck", "int", 1,
            min_val=0, max_val=10,
            doc=(
                "cfMesh: 좁은 gap (bottleneck) 구간에서 최소 유지 layer 수.\n"
                "0 = 자동 축소 허용 (권장). 1+ = 강제 유지 (collision 위험)."
            ),
        ),
        EngineParamSpec(
            "post_layers_2d",
            "2D mode (-2DLayers)", "bool", False,
            doc=(
                "cfMesh 2DLayers 옵션 — 얇은 extruded 2.5D case 전용.\n"
                "일반 3D mesh 에선 끔."
            ),
        ),
    ],

    # ------------------------------------------------------------------
    # beta67 — native_* 엔진 (v0.4 native-first 기본 경로)
    # ------------------------------------------------------------------
    "native_tet": [
        EngineParamSpec(
            "seed_density", "seed_density", "int", 12,
            min_val=4, max_val=40,
            doc="bbox_diag / seed_density = target_edge. 값↑ → cell↑.",
        ),
        EngineParamSpec(
            "max_iter", "max_iter", "int", 2,
            min_val=1, max_val=5,
            doc="harness Gen↔Eval 반복 횟수.",
        ),
        EngineParamSpec(
            "sliver_quality_threshold", "sliver q_thresh", "float", 0.05,
            min_val=0.0, max_val=0.3, step=0.01,
            doc=(
                "shape quality (정사면체≈1, sliver≈0) 하한.\n"
                "낮게=관대 (cell 보존↑), 높게=엄격 (non_ortho↓).\n"
                "draft 0.02 / standard 0.05 / fine 0.10 기본."
            ),
        ),
    ],
    "native_hex": [
        EngineParamSpec(
            "seed_density", "seed_density", "int", 16,
            min_val=6, max_val=50,
            doc="bbox_diag / seed_density = hex edge length.",
        ),
        EngineParamSpec(
            "max_cells_per_axis", "max_cells_per_axis", "int", 50,
            min_val=10, max_val=200,
            doc=(
                "각 축당 최대 cell 수 (총 cell <= N^3).\n"
                "너무 작은 target_edge 가 grid 폭주 방지용 cap."
            ),
        ),
        EngineParamSpec(
            "snap_boundary", "snap_boundary", "bool", False,
            doc="True: hex vertex 를 STL 표면으로 projection (fine 권장).",
        ),
        EngineParamSpec(
            "preserve_features", "preserve_features", "bool", False,
            doc=(
                "True: sharp corner / edge 근처 hex vertex 를 feature vertex 로\n"
                "직접 snap. snap_boundary=True 와 함께 쓸 때만 효과."
            ),
        ),
        EngineParamSpec(
            "feature_angle_deg", "feature_angle_deg", "float", 45.0,
            min_val=15.0, max_val=90.0, step=5.0,
            doc="인접 triangle dihedral > 이 각도면 feature edge 로 간주.",
        ),
    ],
    "native_poly": [
        EngineParamSpec(
            "seed_density", "seed_density", "int", 10,
            min_val=4, max_val=30,
            doc="tet base seed_density — 최종 poly cell 수에 직결.",
        ),
        EngineParamSpec(
            "max_iter", "max_iter", "int", 3,
            min_val=1, max_val=5,
            doc="harness 반복 (재시도 시 seed 1.5× 증가).",
        ),
        EngineParamSpec(
            "max_tet_cells", "max_tet_cells", "int", 30000,
            min_val=1000, max_val=200000,
            doc="tet base 의 cell 수 상한 (dual 변환 비용 방지).",
        ),
    ],
}


# Aliases — 사용자가 콤보에서 고르는 값과 registry 키의 매핑
ENGINE_KEY_ALIASES: dict[str, str] = {
    "tier_wildmesh":   "wildmesh",
    "tier_polyhedral": "polyhedral",
    "tier2_tetwild":   "tetwild",
    "tier05_netgen":   "netgen",
    "tier1_snappy":    "snappy",
    "tier15_cfmesh":   "cfmesh",
    "tier_mmg3d":      "mmg3d",
    "tier_meshpy":     "meshpy",
    "tier_jigsaw":     "jigsaw",
    "tier_jigsaw_fallback": "jigsaw",
    "tier0_core":      "core",
    "tier_gmsh_hex":   "gmsh_hex",
    "tier_cinolib_hex": "cinolib_hex",
    "tier_voro_poly":  "voro_poly",
    "tier_hohqmesh":   "hohqmesh",
    "tier_algohex":    "algohex",
    "tier_robust_hex": "robust_hex",
    "tier_hex_classy_blocks": "hex_classy",
    "tier_classy_blocks": "classy_blocks",
    # beta67 — native_* 엔진 aliases
    "tier_native_tet":  "native_tet",
    "tier_native_hex":  "native_hex",
    "tier_native_poly": "native_poly",
}


def resolve_engine_key(tier_or_engine: str) -> str:
    """콤보 value ('wildmesh', 'tetwild', ...) 또는 canonical tier name 을 정규화."""
    s = tier_or_engine.lower()
    if s in ENGINE_PARAM_REGISTRY or s in ("wildmesh", "polyhedral"):
        return s
    return ENGINE_KEY_ALIASES.get(s, s)


def get_specs_for_engine(engine_key: str) -> list[EngineParamSpec]:
    """엔진 key → spec 리스트. 없으면 빈 리스트."""
    return ENGINE_PARAM_REGISTRY.get(resolve_engine_key(engine_key), [])


# Tier 4 콤보에서 독립 BL 엔진 선택 시 spec 을 조합해서 반환.
_LAYERS_POST_ENGINES = {
    "generate_boundary_layers",
    "refine_wall_layer",
    "snappy_addlayers",
}


def is_layers_post_engine(value: str) -> bool:
    return str(value).lower() in _LAYERS_POST_ENGINES
