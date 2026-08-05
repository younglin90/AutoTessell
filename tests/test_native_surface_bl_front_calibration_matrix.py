"""Report-only BL=0/1/3 calibration matrix for the shared-front candidate."""

from __future__ import annotations

import hashlib
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path("/tmp/autotessell_surface_bl_front_shared_build")))
from native_surface_bl_front_shared import plan_shared_surface_wall_edge_front  # noqa: E402


CASES = (
    ("cube", Path("tests/benchmarks/cube.stl")),
    ("sphere", Path("tests/benchmarks/sphere_watertight.stl")),
    ("naca0012", Path("tests/benchmarks/naca0012.stl")),
    ("complex_duct", Path("tests/benchmarks/trimesh_duct.stl")),
)


def _fixture():
    return (
        np.array([[0.0, 0.0, 0.0], [1.0, 0.0, 0.0], [1.0, 1.0, 0.0]], dtype=float),
        np.array([[11, 0, 1, 0], [12, 1, 2, 0]], dtype=np.int64),
        np.array([[0.0, 0.0, 1.0]], dtype=float),
    )


def test_corpus_bl_matrix_is_repeatable_and_report_only() -> None:
    points, edges, normals = _fixture()
    measurements = []
    for case, path in CASES:
        source_sha256 = hashlib.sha256(path.read_bytes()).hexdigest()
        for layers in (0, 1, 3):
            result = plan_shared_surface_wall_edge_front(
                points, edges, normals, ["wall"], ["unclassified_boundary"], ["fluid_wall"],
                layers, 0.1, 1.2,
            )
            assert result["accepted"] is True
            assert result["actual_layers"] == layers
            if layers == 0:
                assert result["status"] == "disabled_identity"
            else:
                assert result["quality"]["max_skewness"] <= 0.50
                assert result["quality"]["max_non_orthogonality"] <= 50.0
                assert result["quality"]["min_step"] >= 1.0e-8
            measurements.append((case, source_sha256, layers, result["status"], result["quality"] if layers else None))
    assert len(measurements) == 12
    assert len({repr(row) for row in measurements}) == 12
