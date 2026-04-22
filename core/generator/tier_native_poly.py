"""Tier wrapper for native_poly 엔진.

v0.4.0-beta7: tet→poly dual + harness 경로 기본화.
scipy Voronoi 경로는 fallback (dual 실패 시).
"""
from __future__ import annotations

import time
from pathlib import Path

from core.generator.native_poly import (
    generate_native_poly_voronoi,
    run_native_poly_harness,
)
from core.schemas import MeshStats, MeshStrategy, TierAttempt
from core.utils.logging import get_logger

log = get_logger(__name__)

TIER_NAME = "tier_native_poly"


class TierNativePolyGenerator:
    """AutoTessell 자체 polyhedral 엔진 (scipy Voronoi, MVP)."""

    TIER_NAME = TIER_NAME

    def run(
        self,
        strategy: MeshStrategy,
        preprocessed_path: Path,
        case_dir: Path,
    ) -> TierAttempt:
        t_start = time.monotonic()

        try:
            from core.analyzer.readers import read_stl  # noqa: PLC0415
        except Exception as exc:
            return TierAttempt(
                tier=self.TIER_NAME, status="failed",
                time_seconds=time.monotonic() - t_start,
                error_message=f"reader import 실패: {exc}",
            )
        try:
            m = read_stl(preprocessed_path)
        except Exception as exc:
            return TierAttempt(
                tier=self.TIER_NAME, status="failed",
                time_seconds=time.monotonic() - t_start,
                error_message=f"STL 읽기 실패: {exc}",
            )

        target_edge = None
        try:
            target_edge = float(strategy.surface_mesh.target_cell_size)
            if target_edge <= 0:
                target_edge = None
        except Exception:
            target_edge = None

        # v0.4: harness (tet→poly dual + Evaluator 반복) 를 먼저 시도.
        hres = run_native_poly_harness(
            m.vertices, m.faces, case_dir,
            target_edge_length=target_edge,
            seed_density=10, max_iter=3,
        )
        if hres.success:
            stats = MeshStats(
                num_cells=hres.n_cells,
                num_points=hres.n_points,
                num_faces=0,
                num_internal_faces=0,
                num_boundary_patches=1,
            )
            return TierAttempt(
                tier=self.TIER_NAME, status="success",
                time_seconds=time.monotonic() - t_start,
                mesh_stats=stats,
            )
        log.warning(
            "native_poly_harness_fail_falling_back_to_voronoi",
            message=hres.message,
        )
        # fallback: 기존 scipy Voronoi
        res = generate_native_poly_voronoi(
            m.vertices, m.faces, case_dir,
            target_edge_length=target_edge,
            seed_density=10,
        )
        elapsed = time.monotonic() - t_start
        if not res.success:
            return TierAttempt(
                tier=self.TIER_NAME, status="failed",
                time_seconds=elapsed, error_message=res.message,
            )
        stats = MeshStats(
            num_cells=res.n_cells,
            num_points=res.n_points,
            num_faces=res.n_faces,
            num_internal_faces=0,
            num_boundary_patches=1,
        )
        return TierAttempt(
            tier=self.TIER_NAME, status="success",
            time_seconds=elapsed, mesh_stats=stats,
        )
