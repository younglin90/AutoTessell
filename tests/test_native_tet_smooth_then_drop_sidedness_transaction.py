"""Atomic sidedness transaction for the native-Tet JJ3 smoothing pass."""

from __future__ import annotations

import hashlib

import numpy as np

from core.generator.native_tet.mesher import (
    _commit_sidedness_nonincreasing_candidate,
)


def _hash(array: np.ndarray) -> str:
    return hashlib.sha256(np.ascontiguousarray(array)).hexdigest()


def _opposite_pair() -> tuple[np.ndarray, np.ndarray]:
    points = np.asarray(
        (
            (0.0, 0.0, 0.0),
            (1.0, 0.0, 0.0),
            (0.0, 1.0, 0.0),
            (0.0, 0.0, 1.0),
            (0.25, 0.25, -1.0),
        ),
        dtype=np.float64,
    )
    tets = np.asarray(((0, 1, 2, 3), (0, 2, 1, 4)), dtype=np.int64)
    return points, tets


def test_safe_candidate_commits_exact_candidate_objects() -> None:
    before_points, before_tets = _opposite_pair()
    candidate_points = before_points.copy()
    candidate_points[3, 2] = 0.8
    candidate_tets = before_tets.copy()

    selected_points, selected_tets, report = (
        _commit_sidedness_nonincreasing_candidate(
            before_points,
            before_tets,
            candidate_points,
            candidate_tets,
        )
    )

    assert report["accepted"] is True
    assert report["exact_rollback"] is False
    assert selected_points is candidate_points
    assert selected_tets is candidate_tets
    assert report["candidate_same_side_internal_faces"] == 0
    assert report["candidate_ambiguous_internal_faces"] == 0


def test_overlap_candidate_rolls_back_exact_arrays_and_hashes() -> None:
    before_points, before_tets = _opposite_pair()
    before_hashes = (_hash(before_points), _hash(before_tets))
    candidate_points = before_points.copy()
    candidate_points[4, 2] = 0.5
    candidate_tets = before_tets.copy()

    selected_points, selected_tets, report = (
        _commit_sidedness_nonincreasing_candidate(
            before_points,
            before_tets,
            candidate_points,
            candidate_tets,
        )
    )

    assert report["accepted"] is False
    assert report["exact_rollback"] is True
    assert selected_points is before_points
    assert selected_tets is before_tets
    assert (_hash(selected_points), _hash(selected_tets)) == before_hashes
    assert report["before_same_side_internal_faces"] == 0
    assert report["candidate_same_side_internal_faces"] == 1


def test_overlap_increase_cannot_trade_against_ambiguity_decrease() -> None:
    valid_points, valid_tets = _opposite_pair()
    ambiguous_points = valid_points + np.asarray((2.0, 0.0, 0.0))
    ambiguous_points[4, 2] = -1e-15
    before_points = np.vstack((valid_points, ambiguous_points))
    before_tets = np.vstack((valid_tets, valid_tets + 5))
    candidate_points = before_points.copy()
    candidate_points[4, 2] = 0.5
    candidate_points[9, 2] = -1.0
    candidate_tets = before_tets.copy()

    selected_points, selected_tets, report = (
        _commit_sidedness_nonincreasing_candidate(
            before_points,
            before_tets,
            candidate_points,
            candidate_tets,
        )
    )

    assert report["before_same_side_internal_faces"] == 0
    assert report["candidate_same_side_internal_faces"] == 1
    assert report["before_ambiguous_internal_faces"] == 1
    assert report["candidate_ambiguous_internal_faces"] == 0
    assert report["accepted"] is False
    assert selected_points is before_points
    assert selected_tets is before_tets
