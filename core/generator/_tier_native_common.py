"""native_* tier wrapper 공용 로직 — STL read + target_edge 파싱 + TierAttempt 조립.

각 tier_native_{tet,hex,poly}.py 가 동일하게 반복하던 패턴을 한 곳에 모은다.
runner_fn 이 실제 엔진 (generate_native_* 또는 run_native_*_harness) 을 호출하고
결과의 (success, n_cells, n_points, n_faces, message) 를 반환해야 한다.
"""
from __future__ import annotations

import time
from pathlib import Path
from typing import Any, Callable, Protocol

from core.schemas import MeshStats, MeshStrategy, TierAttempt
from core.utils.logging import get_logger

log = get_logger(__name__)


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
        tier_name: TierAttempt.tier.
        strategy: MeshStrategy (target_cell_size 파싱용).
        preprocessed_path: 입력 STL path.
        case_dir: 출력 디렉터리.
        extra_kwargs: runner_fn 에 전달할 추가 kwargs (e.g. seed_density=16).

    Returns:
        TierAttempt (success / failed).
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

    kwargs = dict(extra_kwargs or {})
    kwargs["target_edge_length"] = target_edge

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
