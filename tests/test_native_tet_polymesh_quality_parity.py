from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pytest


_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_ROOT / "auto_tessell_core" / "build"))
sys.path.insert(0, str(_ROOT / "tests"))
import native_tet_polymesh_quality as native  # noqa: E402
from test_native_tet_polymesh_quality_internal import _write_two_cubes  # noqa: E402

from core.evaluator.native_checker import NativeMeshChecker  # noqa: E402
from core.utils.polymesh_reader import (  # noqa: E402
    parse_foam_faces,
    parse_foam_labels_array,
    parse_foam_points_array,
)


def test_disk_oracle_matches_independent_python_checker_fixture(tmp_path: Path) -> None:
    root = tmp_path / "polyMesh"
    _write_two_cubes(root)
    points_file = root / "points"
    points_file.write_text(
        points_file.read_text(encoding="utf-8").replace("(2 1 0)", "(2 1.2 0)"),
        encoding="utf-8",
    )

    result = dict(native.audit(str(root)))
    points = parse_foam_points_array(points_file)
    faces = parse_foam_faces(root / "faces")
    owner = parse_foam_labels_array(root / "owner")
    neighbour = parse_foam_labels_array(root / "neighbour")
    checker = NativeMeshChecker()
    face_centres = checker._compute_face_centres(points, faces)
    face_normals, _areas = checker._compute_face_normals_areas(points, faces)
    cell_centres = checker._compute_cell_centres_from_vertices(
        points, faces, owner, 2, neighbour
    )
    py_no, _py_avg, _py_severe = checker._compute_non_orthogonality(
        face_centres, face_normals, cell_centres, owner, neighbour, 1
    )
    py_internal_skew = checker._compute_skewness(
        face_centres, cell_centres, owner, neighbour, 1
    )
    py_boundary_skew = checker._compute_boundary_skewness(
        face_centres, face_normals, cell_centres, owner, 1
    )
    py_aspect = checker._compute_max_aspect_ratio(points, faces, owner, 2, 1)

    assert result["valid"] is True
    assert result["max_non_orthogonality"] == pytest.approx(py_no, abs=1e-12)
    assert result["max_internal_skewness"] == pytest.approx(py_internal_skew, abs=1e-12)
    assert result["max_boundary_skewness"] == pytest.approx(py_boundary_skew, abs=1e-12)
    assert result["max_aspect_ratio"] == pytest.approx(py_aspect, abs=1e-12)
    assert np.isfinite(result["max_skewness"])
