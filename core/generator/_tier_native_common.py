"""native_* tier wrapper 공용 로직 — STL read + target_edge 파싱 + TierAttempt 조립.

각 tier_native_{tet,hex,poly}.py 가 동일하게 반복하던 패턴을 한 곳에 모은다.
runner_fn 이 실제 엔진 (generate_native_* 또는 run_native_*_harness) 을 호출하고
결과의 (success, n_cells, n_points, n_faces, message) 를 반환해야 한다.

v0.4.0-beta17+: quality-specific harness 파라미터 테이블 (``HARNESS_PARAMS``) 을
여기에 중앙 집중. ``get_harness_params(tier_name, quality)`` 를 호출해 tier 별
per-quality 기본값 획득.
"""
from __future__ import annotations

import time
from pathlib import Path
from typing import Any, Callable, Protocol

from core.schemas import MeshStats, MeshStrategy, QualityLevel, TierAttempt
from core.utils.logging import get_logger

log = get_logger(__name__)


# ---------------------------------------------------------------------------
# Per-tier × per-quality harness 파라미터 테이블 (v0.4.0-beta17)
# ---------------------------------------------------------------------------
#
# 각 native tier 의 harness (Gen ↔ Eval 반복) 기본 파라미터. quality 가 올라갈수록
# seed_density / max_iter 를 올려 품질↑, 단 실행 시간도 늘어난다. bench 결과
# (``tests/stl/bench_v04_result.json``) 를 기반으로 튜닝된 값.
#
# 각 entry keys:
#   - ``seed_density``: bbox_diag / seed_density 로 target_edge 자동 계산.
#                       값이 클수록 셀이 작아지고 수가 늘어난다.
#   - ``max_iter``: harness 의 최대 Gen↔Eval 반복 횟수.
#
# runner_fn 에 ``**extra_kwargs`` 로 주입되므로 그대로 seed_density / max_iter
# signature 를 요구하는 ``run_native_{tet,poly}_harness`` 와 호환.

HARNESS_PARAMS: dict[str, dict[str, dict[str, Any]]] = {
    "tier_native_tet": {
        # beta62: sliver_quality_threshold 를 quality 별로. 낮은 threshold 는
        # 관대 (cell 보존↑, 수렴↑), 높은 threshold 는 엄격 (non_ortho↓ 품질↑).
        #   draft  0.02 → 복잡 형상에서도 cell 이 남아 harness 수렴
        #   standard 0.05 → 기존 기본값
        #   fine   0.10 → sliver 공격적 제거 → 최고 품질
        "draft":    {"seed_density": 10, "max_iter": 1, "sliver_quality_threshold": 0.02,
                     "max_input_vertices": 100000},
        "standard": {"seed_density": 14, "max_iter": 2, "sliver_quality_threshold": 0.05,
                     "max_input_vertices": 100000,
                     # beta310: standard 부터 Phase B 를 비활성화.
                     # Phase B (split/collapse/flip local ops) 는 inverted tet 를 다수
                     # 생성하고 (validate 에서 1885개 검출), 이후 skewness 가 13+ 로 폭등한다.
                     # Phase B 비활성화 시 skewness 13 → 3.7 로 대폭 개선.
                     # non-ortho 는 tet mesh 의 구조적 특성 (sliver boundary cell) 으로
                     # Phase B 관계없이 89-90° 수준. evaluator 에서 tier-specific 완화.
                     "enable_phase_b": False,
                     # CDT recovery 로 surface edge conformity 개선 시도.
                     "enable_cdt_recovery": True,
                     "cdt_recovery_max_cycles": 3,
                     "cdt_recovery_points_budget": 200,
                     "cdt_recovery_outer_iter": 2,
                     "cdt_recovery_target_ratio": 0.7},
        "fine":     {"seed_density": 16, "max_iter": 3, "sliver_quality_threshold": 0.10,
                     "max_input_vertices": 200000,
                     # fine: Phase B + C (envelope + quality stop) + adaptive +
                     # beta520: curvature-aligned anisotropic metric.
                     "enable_phase_b": True, "local_ops_iterations": 2,
                     "flip_iterations": 2, "tangent_smooth_iterations": 2,
                     "enable_phase_c": True, "envelope_eps_relative": 0.01,
                     "use_adaptive_sizing": True,
                     "use_anisotropic_metric": True, "anisotropic_ratio": 0.5,
                     # BSP + Bowyer-Watson 경로 활성 (fTetWild recovery parity).
                     "enable_bsp_insertion": True,
                     # beta630: fine 에서 edge recovery 활성.
                     "enable_edge_recovery": True,
                     "edge_recovery_max_iter": 2,
                     # beta1380: fine 에서 통합 CDT recovery + AMIPS smoothing.
                     "enable_cdt_recovery": True,
                     "cdt_recovery_max_cycles": 4,
                     "cdt_recovery_points_budget": 300,
                     "cdt_recovery_outer_iter": 3,
                     "cdt_recovery_target_ratio": 0.9,
                     "enable_amips_smooth": True,
                     "amips_iterations": 2,
                     "amips_alpha": 1.0,
                     # P2.2 / beta2310: fine 에서 torch (CUDA 가용 시 GPU)
                     # AMIPS 라우팅. amips_torch.is_available() 가 False 면
                     # mesher 가 자동 numpy fallback.
                     "use_torch_amips": True,
                     # C1.5 / beta2373: fine 에서 QED 더 적극 (10k face 부터).
                     # Hu 2018 §3.4 simplification — sliver 격감 효과.
                     "qed_min_faces": 10000,
                     # C1.7 / beta2378: fine 에서 Stellar split-pass 자동 ON.
                     # _apply_op_queue 후반의 split_sliver_longest_edge 활성 →
                     # 추가 sliver 제거. monotone guard 통과 시만 채택.
                     "enable_stellar_split": True,
                     # beta810: fine 에서는 더 엄격한 sliver drop.
                     "sliver_drop_min_dihedral_deg": 1.0,
                     "sliver_drop_max_aspect": 5e4,
                     # beta2332: fine 에서 Phase B collapse 더 적극.
                     # 200 → 1000 (5×). cell_drop_rollback_ratio 가 안전망 —
                     # 50% 이상 cell 떨어지면 자동 revert.
                     "max_collapses_per_iter": 1000},
    },
    "tier_native_hex": {
        # native_hex 는 uniform grid (harness 미사용). seed_density / snap_boundary 만 의미.
        # beta22: fine quality 는 기본적으로 surface snap 활성화.
        # beta66: fine quality 는 preserve_features=True 로 sharp corner snap 개선.
        # beta860: fine 에 N-level octree n_levels=4 + snap_iterations=5 더 강화.
        # beta2297: fine 에 X3 boundary Laplacian post-smooth 자동 활성 — snap 후
        #          skewness 개선 (snappyHexMesh 'smooth-after-snap' 동등 default).
        "draft":    {"seed_density": 12, "snap_boundary": False},
        "standard": {"seed_density": 16, "snap_boundary": True,
                     "adaptive": True, "n_levels": 2, "snap_iterations": 2},
        "fine":     {"seed_density": 24, "snap_boundary": True, "preserve_features": True,
                     "adaptive": True, "n_levels": 4, "snap_iterations": 5,
                     "refinement_distance_factor": 2.5,
                     "feature_angle_deg": 40.0,
                     "enable_post_smooth": True,
                     "post_smooth_iterations": 3,
                     "post_smooth_relax": 0.3,
                     # P2.4 / beta2313 — fine 에 buffer 1 cell (snappy default).
                     "hex_buffer_cells": 1},
    },
    "tier_native_poly": {
        # beta97: smooth_iters — dual 이후 Laplacian smoothing 횟수.
        # draft: 0 (빠름), standard: 3 (균형), fine: 5 (품질 우선).
        # beta850: fine 은 tet base 에 더 큰 seed_density → dual 셀 품질 개선.
        # beta2297: voronoi fallback 의 Lloyd CVT iteration 도 quality 별 차등.
        #          draft=2 (default), standard=3, fine=5 — geogram polyDual fine 동등.
        "draft":    {"seed_density": 8,  "max_iter": 2, "smooth_iters": 0,
                     "smooth_relax": 0.25, "n_lloyd": 2},
        "standard": {"seed_density": 10, "max_iter": 3, "smooth_iters": 3,
                     "smooth_relax": 0.3, "n_lloyd": 3},
        "fine":     {"seed_density": 16, "max_iter": 5, "smooth_iters": 7,
                     "smooth_relax": 0.35, "max_tet_cells": 60000,
                     "n_lloyd": 5},
    },
}


def get_harness_params(tier_name: str, quality: str | QualityLevel) -> dict[str, Any]:
    """tier × quality 조합의 harness 기본 파라미터 반환.

    Args:
        tier_name: ``tier_native_tet`` / ``tier_native_hex`` / ``tier_native_poly``.
        quality: ``draft`` / ``standard`` / ``fine`` (또는 QualityLevel enum).

    Returns:
        dict (seed_density / max_iter ...). 매핑이 없으면 빈 dict. 상위 호출자는
        이 dict 를 **그대로 runner_fn 에 주입** 하거나 자신의 override 와 merge.
    """
    if isinstance(quality, QualityLevel):
        q = quality.value
    else:
        q = str(quality or "").lower()
    table = HARNESS_PARAMS.get(tier_name) or {}
    # quality 가 알려진 값이면 그대로, 아니면 standard 로 fallback
    return dict(table.get(q) or table.get("standard") or {})


class _NativeRunOutcome(Protocol):
    """runner_fn 반환값이 만족해야 할 duck-type.

    native_tet/hex/poly 엔진과 harness 모두 동일 필드를 갖는다:
        success: bool
        n_cells: int
        n_points: int
        n_faces: int   (없으면 0)
        message: str
    """
    success: bool
    n_cells: int
    n_points: int
    message: str


def _parse_target_edge(strategy: MeshStrategy) -> float | None:
    """strategy.surface_mesh.target_cell_size 파싱. 0/음수/오류 시 None."""
    try:
        target = float(strategy.surface_mesh.target_cell_size)
        if target <= 0:
            return None
        return target
    except Exception:
        return None


def run_native_tier(
    runner_fn: Callable[..., _NativeRunOutcome],
    tier_name: str,
    strategy: MeshStrategy,
    preprocessed_path: Path,
    case_dir: Path,
    *,
    extra_kwargs: dict[str, Any] | None = None,
) -> TierAttempt:
    """tier wrapper 공용 entry.

    Args:
        runner_fn: 실제 엔진 호출 함수 — `(vertices, faces, case_dir, target_edge_length=..., **extra_kwargs)` 를 받음.
            반환값이 `success/n_cells/n_points/message` 필드를 가져야 한다.
        tier_name: TierAttempt.tier — 또한 ``HARNESS_PARAMS`` lookup key.
        strategy: MeshStrategy (target_cell_size 및 quality_level 파싱용).
        preprocessed_path: 입력 STL path.
        case_dir: 출력 디렉터리.
        extra_kwargs: caller 가 고정하고 싶은 파라미터. 우선순위 최상위.

    Returns:
        TierAttempt (success / failed).

    파라미터 병합 우선순위 (beta20):
        1. ``extra_kwargs`` (caller override — 최우선)
        2. ``strategy.tier_specific_params`` (Strategist / CLI ``--tier-param`` 주입)
        3. ``HARNESS_PARAMS[tier][quality]`` (테이블 기본값)
        4. 함수 signature default

    ``strategy.tier_specific_params`` 에서는 ``seed_density`` / ``max_iter`` /
    ``snap_boundary`` 등 runner_fn kwargs 와 일치하는 키만 전달된다. 그 외 키
    (``engine_selection`` / ``recommended_mesh_type``) 는 runner_fn 의 ``**_unused``
    로 흡수되거나 silently 무시.

    v0.4.0-beta17+: HARNESS_PARAMS 테이블 기반 quality-aware 주입.
    v0.4.0-beta20+: strategy.tier_specific_params 도 merge 대상.
    """
    t_start = time.monotonic()

    try:
        from core.analyzer.readers import read_stl  # noqa: PLC0415
    except Exception as exc:
        return TierAttempt(
            tier=tier_name, status="failed",
            time_seconds=time.monotonic() - t_start,
            error_message=f"reader import 실패: {exc}",
        )
    try:
        m = read_stl(preprocessed_path)
    except Exception as exc:
        return TierAttempt(
            tier=tier_name, status="failed",
            time_seconds=time.monotonic() - t_start,
            error_message=f"STL 읽기 실패: {exc}",
        )

    target_edge = _parse_target_edge(strategy)

    # beta17: tier × quality 기본값
    params = get_harness_params(tier_name, strategy.quality_level)

    # beta20: strategy.tier_specific_params 의 runner-호환 키를 merge (HARNESS_PARAMS
    # 위, extra_kwargs 아래 우선순위). runner_fn 이 인식하지 못하는 키는 **_unused
    # 로 흡수되거나 dropped.
    _TIER_PARAM_KEYS = {
        "seed_density", "max_iter", "snap_boundary",
        "max_cells_per_axis",  # beta61: native_hex grid cap override
        "max_tet_cells",       # beta56: native_poly harness cap
        "sliver_quality_threshold",  # beta62: native_tet sliver filter
        "preserve_features",   # beta66: native_hex feature-aware snap
        "feature_angle_deg",   # beta66
        "adaptive",            # beta91: native_hex octree adaptive refinement
        "n_levels",            # beta92: N-level octree refinement depth
        "refinement_distance_factor",  # beta92: surface distance threshold factor
        "max_input_vertices",  # beta77: native_tet large input guardrail
        "snap_iterations",     # beta94: iterative snap step (snappyHexMesh snap 근사)
        "smooth_iters",        # beta97: native_poly Laplacian smoothing
        "smooth_relax",        # beta97
        # beta2293: native_hex X3 boundary Laplacian post-smooth — 이전엔
        # mesher 시그너쳐에 있어도 allowlist 누락으로 silently dropped.
        "enable_post_smooth",      # native_hex X3 (beta1840)
        "post_smooth_iterations",  # native_hex X3
        "post_smooth_relax",       # native_hex X3
        # beta2294: native_poly voronoi fallback — 이전엔 _runner 의
        # **_unused 가 흡수해 silently dropped.
        "n_lloyd",                 # native_poly Lloyd CVT iterations
        "auto_escalate",           # native_poly DD2 fallback retry
        "auto_escalate_max",       # native_poly retry 최대 횟수
        # beta2295: native_tet TetWild-lite knobs — _runner **kwargs forward
        # 도 함께 추가했고 (tier_native_tet.py beta2295) 이젠 GUI/CLI 도달.
        "target_cells",            # fTetWild target_num_cells 동등 (beta330)
        "enable_amips_smooth",     # AMIPS analytic optimizer (beta1350)
        "enable_chunked_delaunay", # 자동 perf 스케일링 (beta1360)
        "enable_cdt_recovery",     # CDT envelope recovery (beta1370)
        "enable_phase_b",          # local ops 통합 (split/collapse/flip, beta120)
        "enable_phase_c",          # envelope+quality stop (beta125)
        # P2.2 / beta2310: AMIPS torch 라우팅 (fine + CUDA 자동).
        "use_torch_amips",
        # P2.4 / beta2313: hex buffer cells (snappy nBufferCellsNoExtrude 동등).
        "hex_buffer_cells",
        # beta2332: native_tet Phase B collapse cap (fine 1000, default 200).
        "max_collapses_per_iter",
        # C1.5 / beta2373: tier-aware QED simplification threshold.
        "qed_min_faces",
        # C1.7 / beta2378: Stellar split-pass auto-enable for fine.
        "enable_stellar_split",
    }
    tsp = getattr(strategy, "tier_specific_params", None) or {}
    for k in _TIER_PARAM_KEYS:
        if k in tsp:
            params[k] = tsp[k]

    # extra_kwargs 가 최상위 우선
    params.update(dict(extra_kwargs or {}))
    params["target_edge_length"] = target_edge
    kwargs = params

    try:
        res = runner_fn(m.vertices, m.faces, case_dir, **kwargs)
    except Exception as exc:
        return TierAttempt(
            tier=tier_name, status="failed",
            time_seconds=time.monotonic() - t_start,
            error_message=f"{tier_name} 실행 실패: {exc}",
        )

    elapsed = time.monotonic() - t_start

    success = bool(getattr(res, "success", False))
    n_cells = int(getattr(res, "n_cells", 0) or 0)

    # success=False 이고 cells 도 0 인 경우만 completely failed
    if not success and n_cells == 0:
        return TierAttempt(
            tier=tier_name, status="failed",
            time_seconds=elapsed,
            error_message=str(getattr(res, "message", "실패")),
        )

    stats = MeshStats(
        num_cells=n_cells,
        num_points=int(getattr(res, "n_points", 0) or 0),
        num_faces=int(getattr(res, "n_faces", 0) or 0),
        num_internal_faces=0,
        num_boundary_patches=1,
    )
    return TierAttempt(
        tier=tier_name, status="success",
        time_seconds=elapsed, mesh_stats=stats,
    )
