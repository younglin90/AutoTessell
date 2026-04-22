"""Tier wrapper: native_tet MVP 엔진 + harness (Gen↔Eval)."""
from __future__ import annotations

from pathlib import Path

from core.generator._tier_native_common import run_native_tier
from core.generator.native_tet import (
    generate_native_tet,
    run_native_tet_harness,
)
from core.schemas import MeshStrategy, TierAttempt
from core.utils.logging import get_logger

log = get_logger(__name__)

TIER_NAME = "tier_native_tet"


def _runner(vertices, faces, case_dir, *, target_edge_length=None, **kwargs):
    """harness 우선, 완전 실패 시 기본 generate_native_tet 로 fallback.

    반환값은 run_native_tier 가 요구하는 duck-type (success/n_cells/n_points/message)
    를 만족한다.
    """
    hres = run_native_tet_harness(
        vertices, faces, case_dir,
        target_edge_length=target_edge_length,
        seed_density=12, max_iter=2,
    )
    if hres.success or hres.n_cells > 0:
        return hres
    # 완전 실패 → 기본 경로로 한 번 더
    return generate_native_tet(
        vertices, faces, case_dir,
        target_edge_length=target_edge_length,
        seed_density=12,
    )


class TierNativeTetGenerator:
    """AutoTessell 자체 tet 엔진 (scipy Delaunay + envelope check)."""

    TIER_NAME = TIER_NAME

    def run(
        self,
        strategy: MeshStrategy,
        preprocessed_path: Path,
        case_dir: Path,
    ) -> TierAttempt:
        return run_native_tier(
            _runner, self.TIER_NAME,
            strategy, preprocessed_path, case_dir,
        )
