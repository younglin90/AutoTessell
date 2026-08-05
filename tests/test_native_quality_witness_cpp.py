from __future__ import annotations

import numpy as np
import pytest

from core.utils.native_extensions import import_native_extension


native_witness = pytest.importorskip("native_quality_witness")


def _two_tet_faces() -> tuple[np.ndarray, list[list[int]], np.ndarray, np.ndarray]:
    points = np.array(
        [[0.0, 0.0, 0.0], [1.0, 0.0, 0.0], [0.0, 1.0, 0.0],
         [0.0, 0.0, 1.0], [0.0, 0.0, -1.0]], dtype=np.float64,
    )
    faces = [
        [0, 1, 2], [0, 3, 1], [1, 3, 2], [2, 3, 0],
        [0, 4, 1], [1, 4, 2], [2, 4, 0],
    ]
    owner = np.array([0, 0, 0, 0, 1, 1, 1], dtype=np.int64)
    neighbour = np.array([1], dtype=np.int64)
    return points, faces, owner, neighbour


def test_cpp_witness_tags_internal_and_boundary_distributions(monkeypatch) -> None:
    monkeypatch.setenv("AUTOTESSELL_EXT_BUILD_DIR", "/tmp/autotessell_quality_witness_build")
    points, faces, owner, neighbour = _two_tet_faces()
    result = native_witness.build_quality_witness(points, faces, owner, neighbour)
    assert result["accepted"] is True
    assert result["quality"]["internal_non_orthogonality"]["max"] == pytest.approx(0.0)
    assert result["quality"]["internal_skewness"]["max"] == pytest.approx(0.23570226039551578)
    assert result["quality"]["boundary_skewness"]["status"] == "measured"
    assert result["quality"]["release_skew"]["max"] >= result["quality"]["internal_skewness"]["max"]
    assert result["faces"][0]["face_class"] == "internal"
    assert result["faces"][1]["face_class"] == "boundary"
    assert result["faces"][1]["non_orthogonality"] is None


def test_cpp_witness_refuses_nan_points(monkeypatch) -> None:
    monkeypatch.setenv("AUTOTESSELL_EXT_BUILD_DIR", "/tmp/autotessell_quality_witness_build")
    points, faces, owner, neighbour = _two_tet_faces()
    points[0, 0] = np.nan
    result = native_witness.build_quality_witness(points, faces, owner, neighbour)
    assert result["accepted"] is False
    assert result["reason"] == "nonfinite_point"
