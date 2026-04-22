"""Tier wrapper for native_poly 엔진.

harness (tet→poly dual + Evaluator) 기본, 실패 시 scipy Voronoi fallback.
"""
from __future__ import annotations

from pathlib import Path

from core.generator._tier_native_common import run_native_tier
from core.generator.native_poly import (
    generate_native_poly_voronoi,
    run_native_poly_harness,
)
from core.schemas import MeshStrategy, TierAttempt
from core.utils.logging import get_logger

log = get_logger(__name__)

TIER_NAME = "tier_native_poly"


def _runner(vertices, faces, case_dir, *, target_edge_length=None,
            seed_density=10, max_iter=3, **_unused):
    """harness 우선, 실패 시 scipy Voronoi fallback.

    quality-specific 파라미터는 run_native_tier 가 HARNESS_PARAMS 에서 주입.
    """
    hres = run_native_poly_harness(
        vertices, faces, case_dir,
        target_edge_length=target_edge_length,
        seed_density=int(seed_density), max_iter=int(max_iter),
    )
    if hres.success:
        return hres
    log.warning(
        "native_poly_harness_fail_falling_back_to_voronoi",
        message=hres.message,
    )
    return generate_native_poly_voronoi(
        vertices, faces, case_dir,
        target_edge_length=target_edge_length,
        seed_density=int(seed_density),
    )


class TierNativePolyGenerator:
    """AutoTessell 자체 polyhedral 엔진."""

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
