"""Tier0 MeshPy host-process safety tests."""
from __future__ import annotations

from pathlib import Path

import numpy as np

from core.generator.tier0_2d_meshpy import Tier2DMeshPyGenerator
from core.schemas import (
    BoundaryLayerConfig,
    DomainConfig,
    MeshStrategy,
    SurfaceMeshConfig,
    SurfaceQualityLevel,
)
from core.utils.stl_writer import write_stl_ascii


def _strategy() -> MeshStrategy:
    return MeshStrategy(
        surface_quality_level=SurfaceQualityLevel.L1_REPAIR,
        selected_tier="tier0_2d_meshpy",
        flow_type="internal",
        domain=DomainConfig(
            type="box", min=[-1.0, -1.0, -1.0], max=[1.0, 1.0, 1.0],
            base_cell_size=0.1, location_in_mesh=[0.0, 0.0, 0.0],
        ),
        surface_mesh=SurfaceMeshConfig(
            input_file="cube.stl", target_cell_size=0.1, min_cell_size=0.01,
        ),
        boundary_layers=BoundaryLayerConfig(
            enabled=False, num_layers=0, first_layer_thickness=0.0,
            growth_ratio=1.0, max_total_thickness=0.0, min_thickness_ratio=0.0,
        ),
    )


def test_tier0_rejects_nonplanar_surface_before_meshpy_build(tmp_path: Path) -> None:
    """Closed 3-D fallback input must return a failure, never call Triangle."""
    vertices = np.array([
        [0.0, 0.0, 0.0], [1.0, 0.0, 0.0], [0.0, 1.0, 0.0], [0.0, 0.0, 1.0],
    ])
    faces = np.array([[0, 2, 1], [0, 1, 3], [1, 2, 3], [2, 0, 3]])
    source = tmp_path / "tetra.stl"
    write_stl_ascii(vertices, faces, source)
    result = Tier2DMeshPyGenerator().run(_strategy(), source, tmp_path / "case")
    assert result.status == "failed"
    assert "non-planar 3-D" in (result.error_message or "")
