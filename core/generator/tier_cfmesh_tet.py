"""Tier cfMesh tetMesh — vendored cfMesh tetMesh exe wrapper.

Used as fallback for mesh_type=tet (primary remains tier_wildmesh / vendored
fTetWild for higher quality). Calls auto_tessell_core/build/cfmesh_native.so
which runs third_party/cfmesh/build/tetMesh on a prepared OpenFOAM case.
"""
from __future__ import annotations

import time
from pathlib import Path
from typing import Any

from core.generator.openfoam_writer import OpenFOAMWriter
from core.schemas import MeshStrategy, TierAttempt, GeneratorStep
from core.utils.logging import get_logger

logger = get_logger(__name__)

TIER_NAME = "tier_cfmesh_tet"


def _import_vendored():
    import sys
    build_dir = Path(__file__).resolve().parents[2] / "auto_tessell_core" / "build"
    if str(build_dir) not in sys.path:
        sys.path.insert(0, str(build_dir))
    import cfmesh_native  # type: ignore
    return cfmesh_native


class CfMeshTetGenerator:
    """vendored cfMesh tetMesh wrapper."""

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
                steps=[GeneratorStep(name="import_cfmesh_native", status="failed", time=0.0)],
                error_message=f"cfmesh_native import 실패: {exc}",
            )

        if case_dir is None:
            case_dir = Path("./case")
        case_dir.mkdir(parents=True, exist_ok=True)
        (case_dir / "constant" / "triSurface").mkdir(parents=True, exist_ok=True)

        # preprocessed_path 우선, 없으면 strategy.surface_mesh.path.
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
        sm = strategy.surface_mesh
        bl = getattr(strategy, "boundary_layers", None)
        # BETA2846 — Strategist 의 cell size 정책 활용 (STL 형상 보존).
        # max_cell_size: tier_specific_params 우선, 없으면 base_cell_size * 4.
        # boundary_cell_size: target_cell_size (surface 셀).
        # min_cell_size: min_cell_size (sharp feature 셀).
        # SurfaceMeshConfig fields: target_cell_size, min_cell_size, feature_angle.
        _target = float(getattr(sm, "target_cell_size", 0.0) or 0.0) if sm else 0.0
        _min = float(getattr(sm, "min_cell_size", 0.0) or 0.0) if sm else 0.0
        max_cell = float(params.get(
            "cfmesh_max_cell_size",
            _target * 4 if _target > 0 else 0.2,
        ))
        boundary_cell = float(params.get(
            "cfmesh_boundary_cell_size", _target,
        ))
        min_cell = float(params.get(
            "cfmesh_min_cell_size", _min,
        ))
        n_layers = 0
        thickness_ratio = 1.2
        max_first = 0.0
        if bl and getattr(bl, "enabled", False):
            n_layers = int(getattr(bl, "num_layers", 0) or 0)
            thickness_ratio = float(getattr(bl, "growth_ratio", 1.2) or 1.2)
            max_first = float(getattr(bl, "first_layer_thickness", 0.0) or 0.0)

        t_step = time.monotonic()
        r = cfm.tet_mesh(
            str(stl_path), str(case_dir),
            max_cell_size=max_cell,
            min_cell_size=min_cell,
            boundary_cell_size=boundary_cell,
            bl_n_layers=n_layers,
            bl_thickness_ratio=thickness_ratio,
            bl_max_first_layer=max_first,
            feature_angle_deg=float(params.get("bl_feature_angle", 30.0)),
            keep_cells_intersecting_boundary=True,
        )
        step_time = time.monotonic() - t_step
        elapsed = time.monotonic() - t_start

        if not r.get("success"):
            return TierAttempt(
                tier=TIER_NAME,
                status="failed",
                time_seconds=elapsed,
                steps=[GeneratorStep(name="cfmesh_tetMesh", status="failed", time=step_time)],
                error_message=f"cfmesh tetMesh 실패: {r.get('log', '')[-300:]}",
            )

        logger.info("cfmesh_tet_vendored_used", polymesh=r.get("polymesh_dir"))
        return TierAttempt(
            tier=TIER_NAME,
            status="success",
            time_seconds=elapsed,
            steps=[GeneratorStep(name="cfmesh_tetMesh", status="success", time=step_time)],
        )
