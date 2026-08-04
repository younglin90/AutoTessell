from __future__ import annotations

import numpy as np


def _module():
    import native_tet_bl_authoritative_graph

    return native_tet_bl_authoritative_graph


def _single_tet():
    points = np.asarray(
        [[0.0, 0.0, 0.0], [1.0, 0.0, 0.0], [0.0, 1.0, 0.0], [0.0, 0.0, 1.0]],
        dtype=np.float64,
    )
    tets = np.asarray([[0, 1, 2, 3]], dtype=np.int64)
    return points, tets


def test_graph_emits_oriented_writer_face_table_and_canonical_hash() -> None:
    points, tets = _single_tet()
    result = _module().build(points, tets)

    assert result["accepted"] is True
    assert result["status"] == "authoritative_candidate_graph"
    assert result["face_count"] == 4
    assert result["publication_eligible"] is False
    assert len(result["graph_sha256"]) == 64
    assert all(row["owner"] == 0 for row in result["faces"])
    assert all(row["neighbour"] == -1 for row in result["faces"])
    assert all(row["role"] == "boundary" for row in result["faces"])
    assert [row["writer_face_id"] for row in result["faces"]] == [
        "face-0", "face-1", "face-2", "face-3"
    ]


def test_graph_builds_shared_owner_neighbour_face_with_opposite_cycles() -> None:
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
    result = _module().build(points, tets)

    assert result["accepted"] is True
    shared = [row for row in result["faces"] if row["neighbour"] == 1]
    assert len(shared) == 1
    assert shared[0]["owner"] == 0
    assert shared[0]["role"] == "internal"


def test_graph_refuses_inverted_duplicate_and_non_manifold_candidates() -> None:
    points, tets = _single_tet()
    inverted = _module().build(points, np.asarray([[0, 2, 1, 3]], dtype=np.int64))
    assert inverted["accepted"] is False
    assert inverted["refusal_reason"] == "tet_signed_volume_nonpositive"

    duplicate = _module().build(points, np.asarray([[0, 1, 2, 3], [0, 1, 2, 3]], dtype=np.int64))
    assert duplicate["accepted"] is False
    assert duplicate["refusal_reason"] == "duplicate_tet"

    non_manifold_points = np.vstack(
        [points, [[0.0, 0.0, -1.0], [0.0, 0.0, -2.0]]]
    )
    non_manifold = _module().build(
        non_manifold_points,
        np.asarray(
            [[0, 1, 2, 3], [0, 2, 1, 4], [0, 2, 1, 5]],
            dtype=np.int64,
        ),
    )
    assert non_manifold["accepted"] is False
    assert non_manifold["refusal_reason"] == "non_manifold_face"


def test_bl0_empty_graph_and_candidate_disk_quality_are_deterministic() -> None:
    points, tets = _single_tet()
    empty = _module().build(points, np.empty((0, 4), dtype=np.int64))
    assert empty["accepted"] is True
    assert empty["status"] == "empty_candidate_graph"
    assert empty["work_performed"] is False
    assert empty["face_count"] == 0

    first = _module().quality(points, tets)
    second = _module().quality(points.copy(), tets.copy())
    assert first["accepted"] is True
    assert first["status"] == "shared_candidate_disk_quality"
    assert first["graph_sha256"] == second["graph_sha256"]
    assert first["quality"] == second["quality"]
    assert first["quality"]["max_non_orthogonality"] >= 0.0
    assert first["quality"]["max_skewness"] >= 0.0

