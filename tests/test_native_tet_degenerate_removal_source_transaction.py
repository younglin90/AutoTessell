"""Unit contracts for the BETA2825 degenerate-removal commit boundary."""

from __future__ import annotations

import numpy as np

from core.generator.native_tet.mesher import (
    _commit_degenerate_removal_source_candidate,
)


def _source_tetrahedron() -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    points = np.array(
        [[0.0, 0.0, 0.0], [1.0, 0.0, 0.0], [0.0, 1.0, 0.0], [0.0, 0.0, 1.0]],
        dtype=np.float64,
    )
    faces = np.array(
        [[0, 2, 1], [0, 1, 3], [1, 2, 3], [2, 0, 3]], dtype=np.int64
    )
    tets = np.array([[0, 1, 2, 3]], dtype=np.int64)
    return points, faces, tets


def test_degenerate_transaction_commits_source_preserving_candidate() -> None:
    points, faces, before_tets = _source_tetrahedron()

    selected_points, selected_tets, report = (
        _commit_degenerate_removal_source_candidate(
            points, faces, points, before_tets, points, before_tets.copy()
        )
    )

    assert report == {
        "accepted": True,
        "before_component_bijective": True,
        "candidate_component_bijective": True,
        "before_source_faces_preserved": True,
        "candidate_source_faces_preserved": True,
        "before_unowned_candidate_faces": 0,
        "candidate_unowned_candidate_faces": 0,
        "before_inverted_tets": 0,
        "candidate_inverted_tets": 0,
        "exact_rollback": False,
    }
    assert selected_points is points
    assert selected_tets is not before_tets
    assert np.array_equal(selected_tets, before_tets)


def test_degenerate_transaction_rolls_back_source_component_loss_exactly() -> None:
    points, faces, before_tets = _source_tetrahedron()
    candidate_tets = np.array(
        [[0, 1, 2, 3], [0, 1, 3, 2]], dtype=np.int64
    )

    selected_points, selected_tets, report = (
        _commit_degenerate_removal_source_candidate(
            points, faces, points, before_tets, points, candidate_tets
        )
    )

    assert report["accepted"] is False
    assert report["candidate_component_bijective"] is False
    assert report["candidate_source_faces_preserved"] is False
    assert report["candidate_inverted_tets"] > report["before_inverted_tets"]
    assert report["exact_rollback"] is True
    assert selected_points is points
    assert selected_tets is before_tets


def test_degenerate_transaction_rolls_back_inversion_without_provenance_debt() -> None:
    points, faces, before_tets = _source_tetrahedron()
    candidate_tets = np.array([[0, 2, 1, 3]], dtype=np.int64)

    selected_points, selected_tets, report = (
        _commit_degenerate_removal_source_candidate(
            points, faces, points, before_tets, points, candidate_tets
        )
    )

    assert report["candidate_component_bijective"] is True
    assert report["candidate_source_faces_preserved"] is True
    assert report["candidate_unowned_candidate_faces"] == 0
    assert report["candidate_inverted_tets"] > report["before_inverted_tets"]
    assert report["accepted"] is False
    assert report["exact_rollback"] is True
    assert selected_points is points
    assert selected_tets is before_tets
