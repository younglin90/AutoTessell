"""TET-FLOW-2 -- Leng 2013 penalized active-set interior smoothing
(``core/generator/native_tet/flow2.py``)."""
from __future__ import annotations

import numpy as np

from core.generator.native_tet.flow2 import (
    _EDGE_PAIRS,
    _ROTATE_TO_FRONT,
    _quality_grad_wrt_vertex,
    penalized_active_set_smooth,
    penalized_energy,
    run_flow2_pass,
    tet_volume_length_quality,
)


def _regular_tet() -> np.ndarray:
    return np.array(
        [
            [1.0, 1.0, 1.0],
            [1.0, -1.0, -1.0],
            [-1.0, 1.0, -1.0],
            [-1.0, -1.0, 1.0],
        ],
        dtype=np.float64,
    )


def _inversions(perm: np.ndarray) -> int:
    return sum(
        1
        for i in range(len(perm))
        for j in range(i + 1, len(perm))
        if perm[i] > perm[j]
    )


def test_rotate_to_front_rows_are_even_permutations() -> None:
    """Signed volume must survive the rotation used by the gradient."""
    for k in range(4):
        row = _ROTATE_TO_FRONT[k]
        assert int(row[0]) == k
        assert sorted(int(x) for x in row) == [0, 1, 2, 3]
        assert _inversions(row) % 2 == 0


def test_volume_length_quality_regular_is_one_and_flat_is_zero() -> None:
    pts = _regular_tet()
    tets = np.array([[0, 1, 2, 3]], dtype=np.int64)
    assert abs(float(tet_volume_length_quality(pts, tets)[0]) - 1.0) < 1e-12

    flat = np.array(
        [[0.0, 0.0, 0.0], [1.0, 0.0, 0.0], [0.2, 1.0, 0.0], [0.3, 0.3, 0.0]],
        dtype=np.float64,
    )
    assert float(tet_volume_length_quality(flat, tets)[0]) == 0.0


def test_quality_gradient_matches_central_finite_differences() -> None:
    """The analytic first variation must agree with a numeric derivative."""
    rng = np.random.default_rng(20260726)
    tets = np.array([[0, 1, 2, 3]], dtype=np.int64)
    for _ in range(25):
        pts = rng.normal(size=(4, 3))
        if abs(
            float(np.dot(pts[1] - pts[0], np.cross(pts[2] - pts[0], pts[3] - pts[0])))
        ) < 1e-3:
            continue  # skip near-degenerate draws (derivative is ill-conditioned)
        for slot in range(4):
            g = _quality_grad_wrt_vertex(
                pts[None, :, :], np.array([slot], dtype=np.int64)
            )[0]
            num = np.zeros(3)
            h = 1e-6
            for axis in range(3):
                pp = pts.copy()
                pm = pts.copy()
                pp[slot, axis] += h
                pm[slot, axis] -= h
                num[axis] = (
                    float(tet_volume_length_quality(pp, tets)[0])
                    - float(tet_volume_length_quality(pm, tets)[0])
                ) / (2.0 * h)
            assert np.allclose(g, num, rtol=2e-4, atol=2e-6), (slot, g, num)


def test_penalized_energy_is_zero_for_good_tets_and_positive_for_slivers() -> None:
    assert penalized_energy(np.array([1.0, 0.95])) == 0.0
    e = penalized_energy(np.array([0.5]))
    assert e > 0.0
    # p = 4 punishes the worse tet much harder.
    assert penalized_energy(np.array([0.1])) > 1000.0 * e


def _bipyramid_with_offcentre_apex() -> tuple[np.ndarray, np.ndarray]:
    """Octahedron-like fan whose single interior vertex is badly placed.

    The 6 outer vertices are the boundary (locked); vertex 6 is the only free
    vertex and starts far off-centre, so a correct descent must pull it back.
    """
    pts = np.array(
        [
            [1.0, 0.0, 0.0],
            [0.0, 1.0, 0.0],
            [-1.0, 0.0, 0.0],
            [0.0, -1.0, 0.0],
            [0.0, 0.0, 1.0],
            [0.0, 0.0, -1.0],
            [0.42, 0.31, 0.03],  # interior apex, off-centre
        ],
        dtype=np.float64,
    )
    faces = [
        (0, 1, 4), (1, 2, 4), (2, 3, 4), (3, 0, 4),
        (1, 0, 5), (2, 1, 5), (3, 2, 5), (0, 3, 5),
    ]
    tets = np.array([[a, b, c, 6] for (a, b, c) in faces], dtype=np.int64)
    # Orient every tet positively so the fan is a valid tiling.
    for i, t in enumerate(tets):
        v = pts[t]
        if np.dot(v[1] - v[0], np.cross(v[2] - v[0], v[3] - v[0])) < 0:
            tets[i] = t[[1, 0, 2, 3]]
    return pts, tets


def test_smoothing_improves_min_quality_and_never_moves_the_boundary() -> None:
    pts, tets = _bipyramid_with_offcentre_apex()
    new_pts, rep = penalized_active_set_smooth(pts, tets, n_sweeps=6)

    assert rep.accepted, rep.reject_reason
    assert rep.n_moved > 0
    assert rep.n_free_vertices == 1  # only the apex is interior
    assert rep.min_q_vl_after > rep.min_q_vl_before
    assert rep.energy_after < rep.energy_before
    assert rep.boundary_preserved
    assert rep.boundary_vertices_bitwise_equal
    # boundary vertices are bitwise identical
    assert np.array_equal(new_pts[:6], pts[:6])
    # the input array is never mutated
    assert pts[6, 0] == 0.42


def test_smoothing_is_deterministic() -> None:
    pts, tets = _bipyramid_with_offcentre_apex()
    a, ra = penalized_active_set_smooth(pts.copy(), tets, n_sweeps=4)
    b, rb = penalized_active_set_smooth(pts.copy(), tets, n_sweeps=4)
    assert np.array_equal(a, b)
    assert ra.n_moved == rb.n_moved


def test_all_boundary_mesh_is_a_no_op() -> None:
    """A single tet has no interior vertex, so nothing may move."""
    pts = _regular_tet()
    tets = np.array([[0, 1, 2, 3]], dtype=np.int64)
    new_pts, rep = penalized_active_set_smooth(pts, tets, n_sweeps=3)
    assert rep.n_moved == 0
    assert not rep.accepted
    assert rep.reject_reason == "no_free_vertices"
    assert np.array_equal(new_pts, pts)


def test_degenerate_ring_vertex_is_skipped_not_repaired() -> None:
    """A ring containing an exactly zero-volume tet is left alone."""
    pts, tets = _bipyramid_with_offcentre_apex()
    pts[6] = np.array([0.0, 0.0, 0.0])  # apex exactly on the equatorial plane
    # collapse one outer vertex onto the plane through the apex so a tet is flat
    flat_pts = pts.copy()
    flat_pts[4] = np.array([0.0, 0.0, 0.0])
    _, rep = penalized_active_set_smooth(flat_pts, tets, n_sweeps=2)
    assert rep.n_moved == 0
    assert rep.n_skipped_degenerate > 0


def test_run_flow2_pass_locks_the_surface_prefix() -> None:
    pts, tets = _bipyramid_with_offcentre_apex()
    # Declare *all* 7 points as surface points -> nothing may move.
    _, rep = run_flow2_pass(pts, tets, 7, n_sweeps=2)
    assert rep["n_free_vertices"] == 0
    assert rep["n_moved"] == 0


def test_edge_pairs_cover_all_six_tet_edges() -> None:
    assert len(set(_EDGE_PAIRS)) == 6
