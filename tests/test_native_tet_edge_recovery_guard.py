from __future__ import annotations

import numpy as np

from core.generator.native_tet.edge_flip_recovery import recover_edges_via_flip


def _two_tet_bipyramid(apex_b: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    points = np.asarray(
        [
            [0.0, 0.0, 0.0],
            [1.0, 0.0, 0.0],
            [0.0, 1.0, 0.0],
            [0.25, 0.25, 1.0],
            apex_b,
        ],
        dtype=np.float64,
    )
    tets = np.asarray([[0, 1, 2, 3], [0, 1, 2, 4]], dtype=np.int64)
    return points, tets


def test_edge_flip_guard_accepts_valid_local_23_flip(monkeypatch) -> None:
    monkeypatch.setenv("AUTO_TESSELL_TET_EDGE_FLIP_INDEX", "1")
    monkeypatch.setenv("AUTO_TESSELL_TET_EDGE_FLIP_GUARD", "1")
    points, tets = _two_tet_bipyramid(np.asarray([0.25, 0.25, -1.0]))

    result_tets, result = recover_edges_via_flip(
        points, tets, [(3, 4)], max_attempts=1,
    )

    assert result.n_edges_attempted == 1
    assert result.n_edges_recovered == 1
    assert result.n_guard_rejected == 0
    assert result_tets.shape == (3, 4)


def test_edge_flip_guard_rejects_degenerate_new_tet(monkeypatch) -> None:
    monkeypatch.setenv("AUTO_TESSELL_TET_EDGE_FLIP_INDEX", "1")
    monkeypatch.setenv("AUTO_TESSELL_TET_EDGE_FLIP_GUARD", "1")
    # a, b, u, v are coplanar, while both original apex tets are non-degenerate.
    points, tets = _two_tet_bipyramid(np.asarray([0.5, 0.0, 0.5]))
    points[3] = [0.25, 0.0, 1.0]

    result_tets, result = recover_edges_via_flip(
        points, tets, [(3, 4)], max_attempts=1,
    )

    assert result.n_edges_attempted == 1
    assert result.n_edges_recovered == 0
    assert result.n_guard_rejected == 1
    np.testing.assert_array_equal(result_tets, tets)


def test_edge_flip_canonicalizes_candidate_order(monkeypatch) -> None:
    monkeypatch.setenv("AUTO_TESSELL_TET_EDGE_FLIP_INDEX", "1")
    monkeypatch.setenv("AUTO_TESSELL_TET_EDGE_FLIP_GUARD", "1")
    first_points, first_tets = _two_tet_bipyramid(
        np.asarray([0.25, 0.25, -1.0]),
    )
    second_points, second_tets = _two_tet_bipyramid(
        np.asarray([0.25, 0.25, -1.0]),
    )
    second_points += np.asarray([2.0, 0.0, 0.0])
    second_tets += 5
    points = np.vstack([first_points, second_points])
    tets = np.vstack([first_tets, second_tets])

    forward_tets, forward = recover_edges_via_flip(
        points, tets, [(3, 4), (8, 9)], max_attempts=2,
    )
    reverse_tets, reverse = recover_edges_via_flip(
        points, tets, [(8, 9), (3, 4)], max_attempts=2,
    )

    np.testing.assert_array_equal(forward_tets, reverse_tets)
    assert forward == reverse
