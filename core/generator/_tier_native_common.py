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
        "draft":    {"seed_density": 10, "max_iter": 1},
        "standard": {"seed_density": 12, "max_iter": 2},
        "fine":     {"seed_density": 16, "max_iter": 3},
    },
    "tier_native_hex": {
        # native_hex 는 uniform grid (harness 미사용). seed_density 만 의미.
        "draft":    {"seed_density": 12},
        "standard": {"seed_density": 16},
        "fine":     {"seed_density": 24},
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
        extra_kwargs: caller 가 고정하고 싶은 파라미터. ``HARNESS_PARAMS`` 의
            per-quality 기본값보다 **우선**. 즉 caller 가 명시한 값은 override 되지
            않는다.

    Returns:
        TierAttempt (success / failed).

    v0.4.0-beta17+: tier × quality 기본 harness 파라미터를 ``get_harness_params`` 로
    조회해 runner_fn 에 주입. caller 가 ``extra_kwargs`` 로 명시한 키는 존중.
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

    # quality-specific harness 기본값 (caller override 를 우선) — beta17
    params = get_harness_params(tier_name, strategy.quality_level)
    params.update(dict(extra_kwargs or {}))  # caller override 는 마지막에 덮어씀
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
