"""Default poly must remain usable when the optional cfMesh module is absent."""

from __future__ import annotations

from pathlib import Path

from core.evaluator.native_checker import NativeMeshChecker
from core.pipeline.orchestrator import PipelineOrchestrator


_REPO = Path(__file__).resolve().parents[1]


def test_default_poly_cube_smoke_without_cfmesh_requirement(tmp_path: Path) -> None:
    result = PipelineOrchestrator().run(
        _REPO / "tests" / "benchmarks" / "cube.stl",
        tmp_path / "case",
        quality_level="draft",
        mesh_type="poly",
        max_iterations=1,
        auto_retry="off",
        write_of_case=True,
        max_cells=2_000,
        tier_specific_params={"max_cells": 2_000, "target_cells": 2_000},
    )

    assert result.success, result.error
    checked = NativeMeshChecker().run(tmp_path / "case")
    assert checked.cells > 0
    assert checked.negative_volumes == 0
    assert checked.mesh_ok
