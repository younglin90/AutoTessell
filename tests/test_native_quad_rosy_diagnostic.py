"""Log-only QUAD-ROSY1 4-RoSy field diagnostic tests.

Nothing here mutates a mesh -- ``run_rosy_diagnostic`` and its helpers are
read-only measurement by construction (diagnostic-only card, same discipline
as ``test_native_hex_match_diagnostic.py`` / ``test_native_tet_boundary_invariant.py``).

The load-bearing assertion in this file is **Poincare-Hopf**: on a closed
oriented surface the fractional singularity indices must sum to the Euler
characteristic.  That is a theorem, not a tuned expectation, so it is asserted
exactly.  Everything else (energy values, singularity counts) is asserted only
for finiteness/sanity, because those depend on the local solver's minimum and
are not stable numbers worth freezing.
"""

from __future__ import annotations

import math
from pathlib import Path

import numpy as np
import pytest

from core.preprocessor.native_remesh.rosy_diagnostic import (
    _best_match_extrinsic_4,
    _best_match_extrinsic_index_4,
    _rotate_into_plane,
    estimate_curvature_tensors,
    initial_orientation_field,
    orientation_energy,
    run_rosy_diagnostic,
    vertex_normals,
    weld_vertices,
)

STL_DIR = Path(__file__).parent / "stl"


# --------------------------------------------------------------------------
# fixtures
# --------------------------------------------------------------------------


def _flat_grid(n: int = 5) -> tuple[np.ndarray, np.ndarray]:
    """Planar (n x n) vertex grid triangulated in the z=0 plane."""
    xs, ys = np.meshgrid(np.arange(n, dtype=np.float64), np.arange(n, dtype=np.float64))
    V = np.column_stack([xs.ravel(), ys.ravel(), np.zeros(n * n)])
    tris = []
    for i in range(n - 1):
        for j in range(n - 1):
            a = i * n + j
            tris.append([a, a + 1, a + n])
            tris.append([a + 1, a + n + 1, a + n])
    return V, np.array(tris, dtype=np.int64)


def _tetrahedron() -> tuple[np.ndarray, np.ndarray]:
    """Smallest closed genus-0 surface: chi = 2, so indices must sum to 2."""
    V = np.array(
        [[0.0, 0.0, 0.0], [1.0, 0.0, 0.0], [0.0, 1.0, 0.0], [0.0, 0.0, 1.0]]
    )
    # outward-oriented.
    F = np.array([[0, 2, 1], [0, 1, 3], [0, 3, 2], [1, 2, 3]], dtype=np.int64)
    return V, F


def _octahedron() -> tuple[np.ndarray, np.ndarray]:
    V = np.array(
        [
            [1.0, 0.0, 0.0],
            [-1.0, 0.0, 0.0],
            [0.0, 1.0, 0.0],
            [0.0, -1.0, 0.0],
            [0.0, 0.0, 1.0],
            [0.0, 0.0, -1.0],
        ]
    )
    F = np.array(
        [
            [0, 2, 4], [2, 1, 4], [1, 3, 4], [3, 0, 4],
            [2, 0, 5], [1, 2, 5], [3, 1, 5], [0, 3, 5],
        ],
        dtype=np.int64,
    )
    return V, F


def _load_stl(name: str) -> tuple[np.ndarray, np.ndarray]:
    trimesh = pytest.importorskip("trimesh")
    mesh = trimesh.load(str(STL_DIR / name), process=True)
    mesh.merge_vertices()
    return np.asarray(mesh.vertices, dtype=np.float64), np.asarray(
        mesh.faces, dtype=np.int64
    )


# --------------------------------------------------------------------------
# primitives
# --------------------------------------------------------------------------


def test_best_match_picks_the_aligned_symmetry_representative() -> None:
    n = np.array([0.0, 0.0, 1.0])
    q0 = np.array([1.0, 0.0, 0.0])
    # q1 is q0 rotated by exactly one quarter turn: the 4-RoSy classes agree.
    q1 = np.array([0.0, 1.0, 0.0])
    a, b = _best_match_extrinsic_4(q0, n, q1, n)
    assert np.allclose(a, b), "a quarter-turn apart must match perfectly"
    ka, kb = _best_match_extrinsic_index_4(q0, n, q1, n)
    assert (ka, kb) in {(0, 1), (1, 0), (1, 2), (0, 3)}


def test_quarter_turn_offset_costs_zero_energy() -> None:
    n = np.array([0.0, 0.0, 1.0])
    normals = np.array([n, n])
    Q = np.array([[1.0, 0.0, 0.0], [0.0, 1.0, 0.0]])
    edges = np.array([[0, 1]], dtype=np.int64)
    assert orientation_energy(Q, normals, edges) == pytest.approx(0.0, abs=1e-12)


def test_eighth_turn_offset_is_the_worst_case() -> None:
    """45 degrees is maximally far inside a 4-fold class: E = 2 - 2cos(45)."""
    n = np.array([0.0, 0.0, 1.0])
    normals = np.array([n, n])
    s = math.sqrt(0.5)
    Q = np.array([[1.0, 0.0, 0.0], [s, s, 0.0]])
    edges = np.array([[0, 1]], dtype=np.int64)
    expected = 2.0 - 2.0 * math.cos(math.radians(45.0))
    assert orientation_energy(Q, normals, edges) == pytest.approx(expected, abs=1e-12)


def test_rotate_into_plane_lands_in_the_target_tangent_plane() -> None:
    n0 = np.array([0.0, 0.0, 1.0])
    n1 = np.array([0.0, 1.0, 0.0])
    v = np.array([1.0, 0.0, 0.0])
    out = _rotate_into_plane(v, n0, n1)
    assert float(np.dot(out, n1)) == pytest.approx(0.0, abs=1e-12)
    assert float(np.linalg.norm(out)) == pytest.approx(1.0, abs=1e-12)


def test_initial_field_is_tangent_unit_and_deterministic() -> None:
    V, F = _octahedron()
    N = vertex_normals(V, F)
    a = initial_orientation_field(N, seed=7)
    b = initial_orientation_field(N, seed=7)
    assert np.allclose(a, b)
    assert np.allclose(np.linalg.norm(a, axis=1), 1.0)
    assert np.allclose(np.sum(a * N, axis=1), 0.0, atol=1e-12)


def test_weld_collapses_duplicated_stl_corners_without_touching_input() -> None:
    # two triangles sharing an edge, written per-facet (no shared indices).
    V = np.array(
        [
            [0.0, 0.0, 0.0], [1.0, 0.0, 0.0], [0.0, 1.0, 0.0],
            [1.0, 0.0, 0.0], [1.0, 1.0, 0.0], [0.0, 1.0, 0.0],
        ]
    )
    F = np.array([[0, 1, 2], [3, 4, 5]], dtype=np.int64)
    V_in, F_in = V.copy(), F.copy()
    wV, wF = weld_vertices(V, F)
    assert wV.shape[0] == 4
    assert wF.shape[0] == 2
    assert np.array_equal(V, V_in) and np.array_equal(F, F_in), "input mutated"


# --------------------------------------------------------------------------
# flat patch: the no-singularity / zero-energy baseline
# --------------------------------------------------------------------------


def test_flat_patch_relaxes_to_zero_energy_and_no_singularities() -> None:
    V, F = _flat_grid(5)
    report = run_rosy_diagnostic(V, F, "flat_grid", n_sweeps=30, with_curvature=False)
    assert report.n_boundary_edges > 0, "an open patch must have boundary edges"
    # a plane admits a perfectly smooth field, so the energy must collapse.
    # Gauss-Seidel diffusion is geometric, not exact, so this is a ratio
    # assertion rather than an exact zero (measured: 12.54 -> 8.2e-7).
    assert report.energy_after < 1e-5
    assert report.energy_after < 1e-6 * report.energy_before
    assert report.n_singularities == 0
    assert math.isfinite(report.intrinsic_energy_after)
    # on a flat patch intrinsic and extrinsic coincide (transport is identity).
    assert report.intrinsic_energy_after == pytest.approx(
        report.energy_after, abs=1e-9
    )


def test_flat_patch_is_not_mutated_by_the_diagnostic() -> None:
    V, F = _flat_grid(4)
    V_in, F_in = V.copy(), F.copy()
    run_rosy_diagnostic(V, F, "flat_grid", n_sweeps=5)
    assert np.array_equal(V, V_in)
    assert np.array_equal(F, F_in)


# --------------------------------------------------------------------------
# forced singularities: hand-verifiable by Poincare-Hopf
# --------------------------------------------------------------------------


@pytest.mark.parametrize("seed", [0, 1, 2, 3, 4])
def test_octahedron_indices_sum_to_euler_characteristic(seed: int) -> None:
    """The hand-verifiable forced-singularity case.

    A closed genus-0 surface admits no singularity-free 4-RoSy field, so
    singularities are forced to exist, and Poincare-Hopf forces their
    fractional indices to sum to chi = 2 -- independent of the seed, because
    the theorem does not care which local minimum the solver landed in.  The
    octahedron resolves this exactly: one +1/4 per face, 8 * 1/4 = 2.
    """
    V, F = _octahedron()
    report = run_rosy_diagnostic(
        V, F, "octahedron", n_sweeps=30, seed=seed, with_curvature=False
    )
    assert report.closed
    assert report.euler_characteristic == 2
    assert report.n_singularities > 0, "no smooth 4-RoSy field exists on a sphere"
    assert report.poincare_hopf_ok
    assert report.index_sum == 8
    assert report.index_histogram == {1: 8}
    assert sum(s.fractional_index for s in report.singularities) == pytest.approx(2.0)
    # both discrete connections must agree on a shape this well-resolved.
    assert report.intrinsic is not None
    assert report.intrinsic.poincare_hopf_ok


@pytest.mark.parametrize("seed", [0, 1, 2])
def test_tetrahedron_is_too_coarse_for_a_faithful_index(seed: int) -> None:
    """Documents the discrete index's sampling limit, so it stays visible.

    Adjacent vertex normals on a bare tetrahedron are ~109 degrees apart --
    past the quarter turn at which "smallest aligning rotation" still
    recovers the true symmetry jump.  Both connections then under-count, and
    Poincare-Hopf is not even reconcilable.  This is a property of the mesh,
    not of the solver, and it is asserted here so that a future card which
    changes it (finer sampling, hierarchy, a different connection) flips this
    test rather than passing silently.
    """
    V, F = _tetrahedron()
    report = run_rosy_diagnostic(
        V, F, "tetrahedron", n_sweeps=30, seed=seed, with_curvature=False
    )
    assert report.euler_characteristic == 2
    assert report.n_singularities > 0
    assert report.index_sum == 4, "measured aliased value; 4 * chi would be 8"
    assert not report.poincare_hopf_reconcilable
    assert report.intrinsic is not None
    assert report.intrinsic.index_sum == 4, "the intrinsic readout aliases too"


def test_singularity_centroids_lie_on_their_faces() -> None:
    V, F = _octahedron()
    report = run_rosy_diagnostic(V, F, "octahedron", n_sweeps=20, with_curvature=False)
    for sing in report.singularities:
        expected = V[F[sing.face]].mean(axis=0)
        assert np.allclose(np.array(sing.centroid), expected)
        assert sing.index in (-1, 1, 2)
        assert sing.fractional_index == sing.index / 4.0


# --------------------------------------------------------------------------
# curvature tensor / alignment
# --------------------------------------------------------------------------


def test_curvature_tensor_vanishes_on_a_plane() -> None:
    V, F = _flat_grid(5)
    T, areas = estimate_curvature_tensors(V, F)
    assert np.all(np.abs(T) < 1e-9), "a plane has zero curvature everywhere"
    assert np.all(areas >= 0.0)


# --------------------------------------------------------------------------
# real-shape smoke tests
# --------------------------------------------------------------------------


def test_cube_gives_eight_quarter_index_corner_singularities() -> None:
    """The cube is the sanity check the card asks for: a 4-RoSy field on a box
    should put a +1/4 singularity at each of the 8 corners, and 8 * 1/4 = 2 is
    exactly the cube's Euler characteristic."""
    V, F = _load_stl("01_easy_cube.stl")
    report = run_rosy_diagnostic(V, F, "01_easy_cube", n_sweeps=20)
    assert report.closed
    assert report.euler_characteristic == 2
    assert report.poincare_hopf_ok
    assert report.n_singularities == 8
    assert report.index_histogram == {1: 8}
    assert report.energy_after <= report.energy_before


def test_cylinder_report_is_well_formed() -> None:
    V, F = _load_stl("02_medium_cylinder.stl")
    report = run_rosy_diagnostic(V, F, "02_medium_cylinder", n_sweeps=20)
    assert report.closed
    assert report.poincare_hopf_ok
    assert report.energy_after < report.energy_before
    assert math.isfinite(report.mean_edge_energy_after)
    assert len(report.energy_trace) == report.n_sweeps + 1
    assert report.curvature is not None
    assert report.curvature.n_anisotropic_vertices > 0
    # a curved shape is the case where curvature alignment should actually
    # beat the ~22.5 deg random-field baseline.
    assert (
        report.curvature.mean_deviation_deg
        < report.curvature.mean_deviation_deg_initial
    )


def test_bracket_report_is_well_formed() -> None:
    V, F = _load_stl("03_hard_bracket.stl")
    report = run_rosy_diagnostic(V, F, "03_hard_bracket", n_sweeps=20)
    assert report.closed
    assert report.euler_characteristic == -4
    # sharp-featured input leaves ambiguous +-1/2 faces, so the exact readout
    # can miss while the theorem itself stays satisfiable -- see
    # SingularityCensus.poincare_hopf_reconcilable.
    assert report.poincare_hopf_reconcilable
    assert report.intrinsic is not None
    assert report.intrinsic.poincare_hopf_reconcilable
    # the intrinsic connection resolves far fewer ambiguous faces here; this
    # gap is the card's main finding about sharp-featured input.
    assert report.intrinsic.n_half_index < report.n_half_index
    assert all(math.isfinite(e) for e in report.energy_trace)


def test_diagnostic_is_deterministic_for_a_fixed_seed() -> None:
    V, F = _load_stl("02_medium_cylinder.stl")
    a = run_rosy_diagnostic(V, F, "c", n_sweeps=10, seed=3, with_curvature=False)
    b = run_rosy_diagnostic(V, F, "c", n_sweeps=10, seed=3, with_curvature=False)
    assert a.energy_after == b.energy_after
    assert a.index_sum == b.index_sum
    assert [s.face for s in a.singularities] == [s.face for s in b.singularities]
