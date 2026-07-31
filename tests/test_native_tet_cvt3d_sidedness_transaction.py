"""Atomic strict-topology transaction for the native-Tet CVT pass."""

from __future__ import annotations

import hashlib

import numpy as np

from core.generator.native_tet.mesher import (
    _commit_cvt3d_sidedness_nonincreasing_candidate,
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


def test_cvt_overlap_rejects_quality_trade_and_rolls_back_exact_objects() -> None:
    before_points, before_tets = _opposite_pair()
    before_hashes = (_hash(before_points), _hash(before_tets))
    candidate_points = before_points.copy()
    # This mimics an unsafe geometry-only CVT update: the opposite apex is
    # moved through the shared face while connectivity remains unchanged.
    candidate_points[4, 2] = 0.5
    candidate_tets = before_tets.copy()

    selected_points, selected_tets, report = _commit_cvt3d_sidedness_nonincreasing_candidate(
        before_points,
        before_tets,
        candidate_points,
        candidate_tets,
    )

    assert report["accepted"] is False
    assert report["exact_rollback"] is True
    assert report["before_same_side_internal_faces"] == 0
    assert report["candidate_same_side_internal_faces"] == 1
    assert selected_points is before_points
    assert selected_tets is before_tets
    assert (_hash(selected_points), _hash(selected_tets)) == before_hashes


def test_cvt_safe_candidate_commits_exact_candidate_objects() -> None:
    before_points, before_tets = _opposite_pair()
    candidate_points = before_points.copy()
    candidate_points[3, 2] = 0.8
    candidate_tets = before_tets.copy()

    selected_points, selected_tets, report = _commit_cvt3d_sidedness_nonincreasing_candidate(
        before_points,
        before_tets,
        candidate_points,
        candidate_tets,
    )

    assert report["accepted"] is True
    assert report["exact_rollback"] is False
    assert selected_points is candidate_points
    assert selected_tets is candidate_tets
    assert report["candidate_same_side_internal_faces"] == 0
    assert report["candidate_ambiguous_internal_faces"] == 0
