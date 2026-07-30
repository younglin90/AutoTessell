"""Minimal L0 contract for source vertices before fallback replacement."""

from __future__ import annotations

import numpy as np

from core.generator.native_tet.mesher import (
    _input_vertices_exactly_present_l0,
    _p4c_candidate_meets_acceptance_l0,
)


def test_input_vertex_presence_accepts_a_reordered_exact_copy() -> None:
    source = np.asarray(((0, 0, 0), (1, 0, 0), (0, 1, 0)), dtype=np.float64)
    candidate = np.asarray(((0, 1, 0), (2, 2, 2), (0, 0, 0), (1, 0, 0)), dtype=np.float64)

    accepted, missing = _input_vertices_exactly_present_l0(source, candidate)

    assert accepted
    assert missing == 0
    assert _input_vertices_exactly_present_l0(source, candidate) == (accepted, missing)


def test_input_vertex_presence_rejects_a_dropped_sharp_corner() -> None:
    source = np.asarray(((0, 0, 0), (1, 0, 0), (0, 1, 0)), dtype=np.float64)
    candidate = np.asarray(((0, 0, 0), (1, 0, 0), (0.0, 1.0 + 1e-12, 0)), dtype=np.float64)

    accepted, missing = _input_vertices_exactly_present_l0(source, candidate)

    assert not accepted
    assert missing == 1


def test_input_vertex_presence_fails_closed_for_a_malformed_candidate() -> None:
    source = np.asarray(((0, 0, 0), (1, 0, 0), (0, 1, 0)), dtype=np.float64)
    candidate = source.copy()
    candidate[2, 2] = np.nan

    accepted, missing = _input_vertices_exactly_present_l0(source, candidate)

    assert not accepted
    assert missing == len(source)


def test_p4c_acceptance_rejects_better_quality_when_a_source_corner_is_missing() -> None:
    source = np.asarray(
        ((0, 0, 0), (1, 0, 0), (0, 1, 0), (0, 0, 1)), dtype=np.float64
    )
    candidate = np.asarray(
        ((0, 0, 0), (1, 0, 0), (0, 1 + 1e-12, 0), (0, 0, 1)),
        dtype=np.float64,
    )

    accepted, missing, topology = _p4c_candidate_meets_acceptance_l0(
        source,
        candidate,
        np.asarray(((0, 1, 2, 3),), dtype=np.int64),
        old_mean_quality=0.1,
        candidate_mean_quality=0.9,
        old_cell_count=100,
        candidate_cell_count=10_000,
    )

    assert not accepted
    assert missing == 1
    assert topology.valid


def test_p4c_acceptance_keeps_quality_and_cell_floor_after_source_gate() -> None:
    source = np.asarray(
        ((0, 0, 0), (1, 0, 0), (0, 1, 0), (0, 0, 1)), dtype=np.float64
    )
    candidate = source[[2, 0, 3, 1]].copy()

    accepted, missing, topology = _p4c_candidate_meets_acceptance_l0(
        source,
        candidate,
        np.asarray(((1, 3, 0, 2),), dtype=np.int64),
        old_mean_quality=0.1,
        candidate_mean_quality=0.2,
        old_cell_count=100,
        candidate_cell_count=50,
    )

    assert accepted
    assert missing == 0
    assert topology.valid


def test_p4c_acceptance_rejects_duplicate_tet_topology() -> None:
    points = np.asarray(
        ((0, 0, 0), (1, 0, 0), (0, 1, 0), (0, 0, 1)), dtype=np.float64
    )
    duplicate_tets = np.asarray(
        ((0, 1, 2, 3), (0, 1, 2, 3)), dtype=np.int64
    )

    accepted, missing, topology = _p4c_candidate_meets_acceptance_l0(
        points,
        points.copy(),
        duplicate_tets,
        old_mean_quality=0.1,
        candidate_mean_quality=0.9,
        old_cell_count=100,
        candidate_cell_count=10_000,
    )

    assert not accepted
    assert missing == 0
    assert topology.n_duplicate_tets == 1
