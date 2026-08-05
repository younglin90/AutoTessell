import numpy as np
import pytest

from core.utils.native_extensions import import_native_extension


native_witness = pytest.importorskip("native_quality_witness")


def _two_tet_faces():
    points = np.array(
        [[0.0, 0.0, 0.0], [1.0, 0.0, 0.0], [0.0, 1.0, 0.0],
         [0.0, 0.0, 1.0], [0.0, 0.0, -1.0]], dtype=np.float64
    )
    faces = [
        [0, 1, 2], [0, 3, 1], [1, 3, 2], [2, 3, 0],
        [0, 4, 1], [1, 4, 2], [2, 4, 0],
    ]
    owner = np.array([0, 0, 0, 0, 1, 1, 1], dtype=np.int64)
    neighbour = np.array([1], dtype=np.int64)
    return points, faces, owner, neighbour


def test_cpp_volume_witness_has_full_aspect_population(monkeypatch):
    monkeypatch.setenv("AUTOTESSELL_EXT_BUILD_DIR", "/tmp/autotessell_quality_witness_build")
    points, faces, owner, neighbour = _two_tet_faces()
    result = native_witness.build_volume_quality_witness(
        points, faces, owner, neighbour,
        ["core", "boundary_layer"], ["cell:0", "cell:1"],
    )
    assert result["accepted"] is True
    assert result["volume_quality"]["full_population"] is True
    assert result["quality"]["aspect_ratio"]["status"] == "measured"
    assert result["quality"]["aspect_ratio"]["max"] >= 1.0
    rows = list(result["volume_quality"]["cells"])
    assert [row["partition"] for row in rows] == ["core", "boundary_layer"]
    assert all(row["positive_geometry"] for row in rows)


def test_cpp_volume_witness_refuses_partition_length(monkeypatch):
    monkeypatch.setenv("AUTOTESSELL_EXT_BUILD_DIR", "/tmp/autotessell_quality_witness_build")
    points, faces, owner, neighbour = _two_tet_faces()
    result = native_witness.build_volume_quality_witness(
        points, faces, owner, neighbour, ["core"], ["cell:0", "cell:1"],
    )
    assert result["accepted"] is False
    assert result["reason"] == "cell_partition_length"
