from __future__ import annotations

import numpy as np


def _module():
    import native_tet_bl_authoritative_graph

    return native_tet_bl_authoritative_graph


def _mesh():
    points = np.asarray(
        [
            [0.0, 0.0, 0.0],
            [1.0, 0.0, 0.0],
            [0.0, 1.0, 0.0],
            [0.0, 0.0, 1.0],
            [0.0, 0.0, -1.0],
        ],
        dtype=np.float64,
    )
    tets = np.asarray([[0, 1, 2, 3], [0, 2, 1, 4]], dtype=np.int64)
    return points, tets


def test_single_cpp_artifact_envelope_carries_graph_serializer_and_quality() -> None:
    points, tets = _mesh()
    artifact = _module().artifact(points, tets)

    assert artifact["accepted"] is True
    assert artifact["status"] == "authoritative_candidate_artifact"
    assert artifact["candidate_artifact"] is True
    assert artifact["collision_surface_source"] == "writer_owned_face_table"
    assert artifact["face_count"] == 7
    assert artifact["quality"]["max_non_orthogonality"] >= 0.0

    verified = _module().readback(points, tets, artifact)
    assert verified["accepted"] is True
    assert verified["readback_verified"] is True


def test_single_cpp_artifact_bl0_is_zero_work() -> None:
    points, _ = _mesh()
    artifact = _module().artifact(points, np.empty((0, 4), dtype=np.int64))

    assert artifact["accepted"] is True
    assert artifact["status"] == "bl0_identity_artifact"
    assert artifact["work_performed"] is False
    assert artifact["collision_surface_source"] == "none"

