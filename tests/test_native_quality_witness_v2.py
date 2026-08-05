from __future__ import annotations

import numpy as np
import pytest

from core.utils.native_extensions import import_native_extension


native_witness = pytest.importorskip("native_quality_witness")


def _two_tet_faces(reversed_internal: bool = False):
    points = np.array(
        [[0.0, 0.0, 0.0], [1.0, 0.0, 0.0], [0.0, 1.0, 0.0],
         [0.0, 0.0, 1.0], [0.0, 0.0, -1.0]], dtype=np.float64
    )
    internal = [0, 1, 2] if reversed_internal else [0, 2, 1]
    faces = [
        internal, [0, 3, 1], [1, 3, 2], [2, 3, 0],
        [0, 4, 1], [1, 4, 2], [2, 4, 0],
    ]
    owner = np.array([0, 0, 0, 0, 1, 1, 1], dtype=np.int64)
    neighbour = np.array([1], dtype=np.int64)
    return points, faces, owner, neighbour


def test_full_volume_witness_checks_orientation_and_worst_uids(monkeypatch):
    monkeypatch.setenv("AUTOTESSELL_EXT_BUILD_DIR", "/tmp/autotessell_quality_witness_build")
    points, faces, owner, neighbour = _two_tet_faces()
    result = native_witness.build_full_volume_quality_witness(
        points, faces, owner, neighbour,
        ["core", "boundary_layer"], ["cell:0", "cell:1"],
    )
    assert result["accepted"] is True
    assert result["schema"].endswith("/v2")
    assert result["orientation_checked"] is True
    assert result["full_population"] is True
    assert result["quality"]["internal_non_orthogonality"]["worst_uid"]
    assert result["quality"]["internal_skewness"]["worst_uid"]
    assert result["quality"]["aspect_ratio"]["worst_uid"]


def test_full_volume_witness_refuses_reversed_internal_winding(monkeypatch):
    monkeypatch.setenv("AUTOTESSELL_EXT_BUILD_DIR", "/tmp/autotessell_quality_witness_build")
    points, faces, owner, neighbour = _two_tet_faces(reversed_internal=True)
    result = native_witness.build_full_volume_quality_witness(
        points, faces, owner, neighbour,
        ["core", "boundary_layer"], ["cell:0", "cell:1"],
    )
    assert result["accepted"] is False
    assert result["reason"] == "reversed_internal_winding"


def test_full_volume_witness_requires_producer_population(monkeypatch):
    monkeypatch.setenv("AUTOTESSELL_EXT_BUILD_DIR", "/tmp/autotessell_quality_witness_build")
    points, faces, owner, neighbour = _two_tet_faces()
    result = native_witness.build_full_volume_quality_witness(
        points, faces, owner, neighbour, None, ["cell:0", "cell:1"],
    )
    assert result["accepted"] is False
    assert result["reason"] == "full_readback_partition_or_uid_missing"



def _oriented_cube():
    points = np.array([[0.,0.,0.],[1.,0.,0.],[1.,1.,0.],[0.,1.,0.],[0.,0.,1.],[1.,0.,1.],[1.,1.,1.],[0.,1.,1.]], dtype=np.float64)
    faces = [[0,3,2,1],[4,5,6,7],[0,1,5,4],[1,2,6,5],[2,3,7,6],[3,0,4,7]]
    owner = np.zeros(6, dtype=np.int64)
    neighbour = np.empty(0, dtype=np.int64)
    return points, faces, owner, neighbour


def test_authority_bound_witness_uses_oriented_centroid_and_face_height_aspect():
    points, faces, owner, neighbour = _oriented_cube()
    result = native_witness.build_authority_bound_volume_quality_witness(
        points, faces, owner, neighbour, ["core"], ["cube:0"]
    )
    assert result["accepted"] is True, result
    assert result["geometry_readback"] is True
    assert result["authority_bound_metrics"] is True
    assert result["quality"]["centres_definition"] == "oriented face-pyramid centroid"
    assert result["quality"]["aspect_definition"] == "face-pyramid height, not bbox/min-edge"
    assert result["volume_quality"]["cells"][0]["volume"] == pytest.approx(1.0)
    assert result["volume_quality"]["cells"][0]["centroid"] == pytest.approx([0.5, 0.5, 0.5])
    assert result["quality"]["boundary_skewness"]["max"] < 1.0e-12
    assert result["quality"]["aspect_ratio"]["max"] == pytest.approx(3.4641016151)


def test_authority_bound_witness_rejects_duplicate_persisted_face():
    points, faces, owner, neighbour = _oriented_cube()
    result = native_witness.build_authority_bound_volume_quality_witness(
        points, faces + [faces[0]], np.zeros(7, dtype=np.int64), neighbour, ["core"], ["cube:0"]
    )
    assert result["accepted"] is False
    assert result["reason"] in {"duplicate_face", "cell_without_closed_geometry"}
