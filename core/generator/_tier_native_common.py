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
        "draft":    {"seed_density": 10, "max_iter": 1, "sliver_quality_threshold": 0.02},
        "standard": {"seed_density": 12, "max_iter": 2, "sliver_quality_threshold": 0.05},
        "fine":     {"seed_density": 16, "max_iter": 3, "sliver_quality_threshold": 0.10},
    },
    "tier_native_hex": {
        # native_hex 는 uniform grid (harness 미사용). seed_density / snap_boundary 만 의미.
        # beta22: fine quality 는 기본적으로 surface snap 활성화.
        # beta66: fine quality 는 preserve_features=True 로 sharp corner snap 개선.
        "draft":    {"seed_density": 12, "snap_boundary": False},
        "standard": {"seed_density": 16, "snap_boundary": False},
        "fine":     {"seed_density": 24, "snap_boundary": True, "preserve_features": True},
    },
    "tier_native_poly": {
        "draft":    {"seed_density": 8,  "max_iter": 2},
        "standard": {"seed_density": 10, "max_iter": 3},
        "fine":     {"seed_density": 14, "max_iter": 4},
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
