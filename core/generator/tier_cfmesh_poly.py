"""Tier cfMesh pMesh — vendored cfMesh pMesh exe wrapper for mesh_type=poly.

Primary backend for polyhedral mesh generation. Calls
auto_tessell_core/build/cfmesh_native.so which runs
third_party/cfmesh/build/pMesh on a prepared OpenFOAM case.
"""
from __future__ import annotations

import time
from pathlib import Path
from typing import Any

from core.generator.openfoam_writer import OpenFOAMWriter
from core.schemas import MeshStrategy, TierAttempt, GeneratorStep
from core.utils.logging import get_logger

logger = get_logger(__name__)

TIER_NAME = "tier_cfmesh_poly"


def _import_vendored():
    import sys
    build_dir = Path(__file__).resolve().parents[2] / "auto_tessell_core" / "build"
    if str(build_dir) not in sys.path:
        sys.path.insert(0, str(build_dir))
    import cfmesh_native  # type: ignore
    return cfmesh_native


class CfMeshPolyGenerator:
    def __init__(self) -> None:
        self._writer = OpenFOAMWriter()

    def run(
        self,
        strategy: MeshStrategy,
        preprocessed_path: Path | None = None,
        case_dir: Path | None = None,
        **_kwargs,
    ) -> TierAttempt:
        t_start = time.monotonic()
        try:
            cfm = _import_vendored()
        except Exception as exc:
            return TierAttempt(
                tier=TIER_NAME,
                status="failed",
                time_seconds=time.monotonic() - t_start,
                error_message=f"cfmesh_native import 실패: {exc}",
            )

        if case_dir is None:
            case_dir = Path("./case")
        case_dir.mkdir(parents=True, exist_ok=True)
        (case_dir / "constant" / "triSurface").mkdir(parents=True, exist_ok=True)

        stl_path = (
            preprocessed_path if preprocessed_path is not None
            else (strategy.surface_mesh.path if strategy.surface_mesh else None)
        )
        if stl_path is None or not Path(stl_path).exists():
            return TierAttempt(
                tier=TIER_NAME,
                status="failed",
                time_seconds=time.monotonic() - t_start,
                error_message="surface_mesh.path 없음",
            )

        params = strategy.tier_specific_params or {}
        max_cell = float(params.get("cfmesh_max_cell_size", 0.2))
        min_cell = float(params.get("cfmesh_min_cell_size", 0.0))

        t_step = time.monotonic()
        r = cfm.poly_mesh(str(stl_path), str(case_dir),
                          max_cell_size=max_cell, min_cell_size=min_cell)
        step_time = time.monotonic() - t_step
        elapsed = time.monotonic() - t_start

        if not r.get("success"):
            return TierAttempt(
                tier=TIER_NAME,
                status="failed",
                time_seconds=elapsed,
                steps=[GeneratorStep(name="cfmesh_pMesh", status="failed", time=step_time)],
                error_message=f"cfmesh pMesh 실패: {r.get('log', '')[-300:]}",
            )

        logger.info("cfmesh_poly_vendored_used", polymesh=r.get("polymesh_dir"))
        return TierAttempt(
            tier=TIER_NAME,
            status="success",
            time_seconds=elapsed,
            steps=[GeneratorStep(name="cfmesh_pMesh", status="success", time=step_time)],
        )
