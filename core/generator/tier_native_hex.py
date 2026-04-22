"""Tier wrapper for native_hex MVP 엔진."""
from __future__ import annotations

import time
from pathlib import Path

from core.generator.native_hex import generate_native_hex
from core.schemas import MeshStats, MeshStrategy, TierAttempt
from core.utils.logging import get_logger

log = get_logger(__name__)

TIER_NAME = "tier_native_hex"


class TierNativeHexGenerator:
    """AutoTessell 자체 hex-dominant 엔진 (uniform grid + inside filter)."""

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

        res = generate_native_hex(
            m.vertices, m.faces, case_dir,
            target_edge_length=target_edge,
            seed_density=16,
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
