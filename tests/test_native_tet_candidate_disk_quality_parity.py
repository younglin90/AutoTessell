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


def test_serializer_assigns_internal_faces_before_boundary_and_readback_verifies() -> None:
    points, tets = _mesh()
    serialized = _module().serialize(points, tets)

    assert serialized["accepted"] is True
    assert serialized["status"] == "candidate_serialized"
    assert serialized["publication_eligible"] is False
    assert serialized["work_performed"] is True
    assert serialized["neighbour"].strip() == "1"
    assert serialized["boundary"].startswith("defaultPatch ")
    assert list(serialized["disk_face_ids"].values()) == [0, 1, 2, 3, 4, 5, 6]

    verified = _module().readback(points.copy(), tets.copy(), serialized)
    assert verified["accepted"] is True
    assert verified["status"] == "candidate_disk_readback_verified"
    assert verified["readback_verified"] is True
    assert verified["artifact_tree_sha256"] == serialized["artifact_tree_sha256"]


def test_serializer_tamper_is_fail_closed_and_bl0_does_no_serialization_work() -> None:
    points, tets = _mesh()
    serialized = _module().serialize(points, tets)
    tampered = dict(serialized)
    tampered["faces"] = tampered["faces"] + "tamper"
    refused = _module().readback(points, tets, tampered)
    assert refused["accepted"] is False
    assert refused["candidate_discarded"] is True
    assert refused["refusal_reason"] == "readback_canonical_bytes_mismatch"

    empty = _module().serialize(points, np.empty((0, 4), dtype=np.int64))
    assert empty["accepted"] is True
    assert empty["work_performed"] is False
    assert empty["status"] == "empty_candidate_serialization"

