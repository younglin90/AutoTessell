"""Read-only TET-LAZY-2 cavity evidence tests."""

from __future__ import annotations

import numpy as np

from core.generator.native_tet.lazy_flip_diagnostic import run_lazy_flip_diagnostic


def _thin_octahedron() -> tuple[np.ndarray, np.ndarray]:
    points = np.array(
        [
            [0.0, 0.0, 3.0],
            [0.0, 0.0, -3.0],
            [1.0, 0.0, 0.0],
            [0.0, 1.0, 0.0],
            [-1.0, 0.0, 0.0],
            [0.0, -1.0, 0.0],
        ],
        dtype=np.float64,
    )
    tets = np.array(
        [[0, 1, 2, 3], [0, 1, 3, 4], [0, 1, 4, 5], [0, 1, 5, 2]],
        dtype=np.int64,
    )
    return points, tets


def test_lazy_flip2_records_cavity_guards_and_rejects_mixed_orientation() -> None:
    points, tets = _thin_octahedron()
    points_before = points.copy()
    tets_before = tets.copy()

    report = run_lazy_flip_diagnostic(
        points,
        tets,
        n_surface_vertices=6,
        max_rounds=2,
        max_edges=1,
    )

    assert report["card"] == "TET-LAZY-2"
    assert report["production_route_touched"] is False
    assert report["parallel"] is False
    assert report["input_unchanged"] is True
    assert report["surface_vertices_moved"] is False
    assert np.array_equal(points, points_before)
    assert np.array_equal(tets, tets_before)
    assert report["n_candidate_records"] == 1

    candidate = report["candidates"][0]
    assert candidate["edge"] == [0, 1]
    assert candidate["criterion"] == "angle"
    assert candidate["after"] is not None
    assert candidate["before"]["signed_volume6"]
    assert candidate["after"]["signed_volume6"]
    assert candidate["before"]["quality"]
    assert candidate["after"]["quality"]
    assert candidate["cavity_boundary_face_set"]["equal"] is True
    assert candidate["global_boundary"]["preserved"] is True
    assert candidate["signed_volume_guard"]["volume_tiling_ok"] is True
    assert candidate["signed_volume_guard"]["orientation_ok"] is False
    assert "signed_volume_guard" in candidate["guard_reasons"]
    assert report["n_accepted_candidates"] == 0
    assert report["sequence_decision"] == "rollback"


def test_lazy_flip2_replay_is_byte_deterministic() -> None:
    points, tets = _thin_octahedron()
    first = run_lazy_flip_diagnostic(points, tets, n_surface_vertices=6, max_edges=1)
    second = run_lazy_flip_diagnostic(points, tets, n_surface_vertices=6, max_edges=1)
    assert first == second


def test_lazy_flip2_uses_only_interior_edges() -> None:
    points, tets = _thin_octahedron()
    report = run_lazy_flip_diagnostic(points, tets, max_edges=None, max_rounds=1)
    assert report["n_interior_edges_first_round"] == 1
    assert report["attempted_edges"] == [[0, 1]]
