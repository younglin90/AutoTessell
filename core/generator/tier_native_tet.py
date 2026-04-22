"""Tier wrapper: native_tet MVP 엔진을 Generator Tier 인터페이스로 감싼다.

run(strategy, preprocessed_path, case_dir) → TierAttempt 패턴을 따른다.
"""
from __future__ import annotations

import time
from pathlib import Path

from core.generator.native_tet import (
    generate_native_tet,
    run_native_tet_harness,
)
from core.schemas import MeshStats, MeshStrategy, TierAttempt
from core.utils.logging import get_logger

log = get_logger(__name__)

TIER_NAME = "tier_native_tet"


class TierNativeTetGenerator:
    """AutoTessell 자체 tet 엔진 (scipy Delaunay + envelope check)."""

    TIER_NAME = TIER_NAME

    def run(
        self,
        strategy: MeshStrategy,
        preprocessed_path: Path,
        case_dir: Path,
    ) -> TierAttempt:
        t_start = time.monotonic()

        # 입력 surface 읽기 (자체 reader)
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

        # v0.4.0-beta7+: harness (Gen ↔ Eval 반복) 를 우선. FAIL 시 기본
        # generate_native_tet 로 fallback (단일 시도).
        hres = run_native_tet_harness(
            m.vertices, m.faces, case_dir,
            target_edge_length=target_edge,
            seed_density=12, max_iter=2,
        )
        if hres.success or hres.n_cells > 0:
            # PASS 또는 best-effort 결과가 있으면 그걸 사용
            elapsed = time.monotonic() - t_start
            stats = MeshStats(
                num_cells=hres.n_cells,
                num_points=hres.n_points,
                num_faces=0,
                num_internal_faces=0,
                num_boundary_patches=1,
            )
            return TierAttempt(
                tier=self.TIER_NAME, status="success",
                time_seconds=elapsed, mesh_stats=stats,
            )
        # 완전 실패 → 기본 경로로 한 번 더
        res = generate_native_tet(
            m.vertices, m.faces, case_dir,
            target_edge_length=target_edge,
            seed_density=12,
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
            num_faces=0,
            num_internal_faces=0,
            num_boundary_patches=1,
        )
        return TierAttempt(
            tier=self.TIER_NAME, status="success",
            time_seconds=elapsed, mesh_stats=stats,
        )
