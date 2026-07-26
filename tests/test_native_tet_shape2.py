"""Focused contracts for the isolated TET-SHAPE-2 pass."""

from __future__ import annotations

from typing import Any

import numpy as np
from numpy.typing import NDArray

from core.generator.native_tet.shape2 import (
    _gsm_score_and_gradient,
    gsm_score,
    run_shape2_pass,
)


def _regular_tet() -> NDArray[Any]:
    return np.array(
        [
            [0.0, 0.0, 0.0],
            [1.0, 0.0, 0.0],
            [0.5, np.sqrt(3.0) / 2.0, 0.0],
            [0.5, np.sqrt(3.0) / 6.0, np.sqrt(2.0 / 3.0)],
        ],
        dtype=np.float64,
    )


def _interior_vertex_fan() -> tuple[NDArray[Any], NDArray[Any]]:
    points = np.array(
        [
            [1.0, 0.0, 0.0],
            [0.0, 1.0, 0.0],
            [-1.0, 0.0, 0.0],
            [0.0, -1.0, 0.0],
            [0.0, 0.0, 1.0],
            [0.0, 0.0, -1.0],
            [0.42, 0.31, 0.03],
        ],
        dtype=np.float64,
    )
    faces = [
        (0, 1, 4),
        (1, 2, 4),
        (2, 3, 4),
        (3, 0, 4),
        (1, 0, 5),
        (2, 1, 5),
        (3, 2, 5),
        (0, 3, 5),
    ]
    tets = np.asarray([[a, b, c, 6] for a, b, c in faces], dtype=np.int64)
    for index, tet in enumerate(tets):
        corners = points[tet]
        signed = np.dot(
            corners[1] - corners[0],
            np.cross(corners[2] - corners[0], corners[3] - corners[0]),
        )
        if signed < 0.0:
            tets[index] = tet[[1, 0, 2, 3]]
    return points, tets


def test_gsm_inverse_height_equation_is_three_for_a_regular_tet() -> None:
    points = _regular_tet()
    tets = np.array([[0, 1, 2, 3]], dtype=np.int64)
    score = gsm_score(points, tets, np.array([1.0], dtype=np.float64))
    assert np.allclose(score, [3.0], rtol=1e-12, atol=1e-12)


def test_gsm_gradient_matches_central_difference() -> None:
    rng = np.random.default_rng(20260726)
    points = rng.normal(size=(4, 3))
    tets = np.array([[0, 1, 2, 3]], dtype=np.int64)
    corners = points[tets]
    edge_squared = np.array(
        [
            np.mean(
                [
                    np.dot(corners[0, j] - corners[0, i], corners[0, j] - corners[0, i])
                    for i, j in ((0, 1), (0, 2), (0, 3), (1, 2), (1, 3), (2, 3))
                ]
            )
        ],
        dtype=np.float64,
    )
    for slot in range(4):
        _, analytic = _gsm_score_and_gradient(
            corners, np.array([slot], dtype=np.int64), edge_squared
        )
        numeric = np.zeros(3, dtype=np.float64)
        for axis in range(3):
            plus = points.copy()
            minus = points.copy()
            plus[slot, axis] += 1e-6
            minus[slot, axis] -= 1e-6
            numeric[axis] = float(
                (gsm_score(plus, tets, edge_squared)[0] - gsm_score(minus, tets, edge_squared)[0])
                / (2e-6)
            )
        assert np.allclose(analytic[0], numeric, rtol=2e-4, atol=2e-6)


def test_shape2_is_boundary_hard_pinned_transactional_and_deterministic() -> None:
    points, tets = _interior_vertex_fan()
    original = points.copy()
    first, report_first = run_shape2_pass(
        points, tets, n_surface_vertices=6, n_sweeps=6, gsm_weight=0.35
    )
    second, report_second = run_shape2_pass(
        points, tets, n_surface_vertices=6, n_sweeps=6, gsm_weight=0.35
    )

    assert report_first.accepted
    assert report_first.strict_axes_pass
    assert report_first.boundary_preserved
    assert report_first.boundary_vertices_bitwise_equal
    assert report_first.exact_orientation_preserved
    assert report_first.n_moved > 0
    assert np.array_equal(first[:6], original[:6])
    assert np.array_equal(points, original)
    assert np.array_equal(first, second)
    assert report_first.as_dict() == report_second.as_dict()


def test_shape2_has_noop_for_all_boundary_mesh() -> None:
    points = _regular_tet()
    tets = np.array([[0, 1, 2, 3]], dtype=np.int64)
    new_points, report = run_shape2_pass(points, tets, n_sweeps=3)
    assert report.reject_reason == "no_free_vertices"
    assert not report.accepted
    assert np.array_equal(new_points, points)
