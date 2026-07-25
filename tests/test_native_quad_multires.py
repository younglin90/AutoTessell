"""QUAD-MULTIRES1 coarse-to-fine 4-RoSy relaxation tests.

Diagnostic-only, exactly like ``test_native_quad_rosy_diagnostic.py``: nothing
here mutates a mesh, and the load-bearing assertion is still **Poincare-Hopf**.
A hierarchy that broke the identity would mean the prolongation is corrupting
the field, so that check is asserted on every shape under multires and not
softened.

Two other things are asserted as theorems rather than tuned expectations:

* the hierarchy's vertex count is **strictly** decreasing (a structural
  property of ``_coarsen_level``, which refuses to emit a level that is not
  smaller), and
* prolongation output is tangent and unit-norm at every vertex (the frame
  invariant ``optimize_orientations`` relies on).

Everything numeric -- energies, singularity counts -- is compared
*between the two modes*, never frozen to a literal, because those depend on
which local minimum the solver landed in.  The one place a literal appears is
the documented seed-1 exception in
``test_bracket_multires_is_within_tolerance_and_far_more_stable``.

Expensive shapes are computed once in module-scoped fixtures (the bracket
sweep is 10 relaxations); see the analogous note in
``.claude/rules/lessons-learned.md`` about repeated heavy native calls in one
pytest process.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest

from core.preprocessor.native_remesh.rosy_diagnostic import (
    _edge_face_count,
    _vertex_adjacency,
    allocate_sweeps,
    build_coarsening_hierarchy,
    initial_orientation_field,
    orientation_energy,
    prolongate_orientations,
    run_rosy_diagnostic,
    vertex_areas,
    vertex_normals,
)

STL_DIR = Path(__file__).parent / "stl"

SEEDS = (0, 1, 2, 3, 4)


# --------------------------------------------------------------------------
# fixtures
# --------------------------------------------------------------------------


def _flat_grid(n: int = 5) -> tuple[np.ndarray, np.ndarray]:
    xs, ys = np.meshgrid(np.arange(n, dtype=np.float64), np.arange(n, dtype=np.float64))
    V = np.column_stack([xs.ravel(), ys.ravel(), np.zeros(n * n)])
    tris = []
    for i in range(n - 1):
        for j in range(n - 1):
            a = i * n + j
            tris.append([a, a + 1, a + n])
            tris.append([a + 1, a + n + 1, a + n])
    return V, np.array(tris, dtype=np.int64)


def _octahedron() -> tuple[np.ndarray, np.ndarray]:
    V = np.array(
        [
            [1.0, 0.0, 0.0], [-1.0, 0.0, 0.0], [0.0, 1.0, 0.0],
            [0.0, -1.0, 0.0], [0.0, 0.0, 1.0], [0.0, 0.0, -1.0],
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


def _tetrahedron() -> tuple[np.ndarray, np.ndarray]:
    V = np.array([[0.0, 0.0, 0.0], [1.0, 0.0, 0.0], [0.0, 1.0, 0.0], [0.0, 0.0, 1.0]])
    F = np.array([[0, 2, 1], [0, 1, 3], [0, 3, 2], [1, 2, 3]], dtype=np.int64)
    return V, F


def _load_stl(name: str) -> tuple[np.ndarray, np.ndarray]:
    trimesh = pytest.importorskip("trimesh")
    mesh = trimesh.load(str(STL_DIR / name), process=True)
    mesh.merge_vertices()
    return (
        np.asarray(mesh.vertices, dtype=np.float64),
        np.asarray(mesh.faces, dtype=np.int64),
    )


def _graph_inputs(V: np.ndarray, F: np.ndarray):
    """The four graph arrays ``build_coarsening_hierarchy`` consumes."""
    normals = vertex_normals(V, F)
    areas = vertex_areas(V, F)
    adjacency = _vertex_adjacency(F, V.shape[0])
    edges = np.array(sorted(_edge_face_count(F).keys()), dtype=np.int64).reshape(-1, 2)
    return normals, areas, adjacency, edges


@pytest.fixture(scope="module")
def cylinder() -> tuple[np.ndarray, np.ndarray]:
    return _load_stl("02_medium_cylinder.stl")


@pytest.fixture(scope="module")
def bracket() -> tuple[np.ndarray, np.ndarray]:
    return _load_stl("03_hard_bracket.stl")


@pytest.fixture(scope="module")
def cube() -> tuple[np.ndarray, np.ndarray]:
    return _load_stl("01_easy_cube.stl")


@pytest.fixture(scope="module")
def bracket_sweep(bracket):
    """One single-res and one multires relaxation per seed, budget 20."""
    V, F = bracket
    out = {}
    for seed in SEEDS:
        out[seed] = (
            run_rosy_diagnostic(V, F, "bracket", n_sweeps=20, seed=seed, with_curvature=False),
            run_rosy_diagnostic(
                V, F, "bracket", n_sweeps=20, seed=seed, multires=True, with_curvature=False
            ),
        )
    return out


@pytest.fixture(scope="module")
def cylinder_sweep(cylinder):
    V, F = cylinder
    out = {}
    for seed in (0, 1, 2):
        out[seed] = (
            run_rosy_diagnostic(V, F, "cyl", n_sweeps=20, seed=seed, with_curvature=False),
            run_rosy_diagnostic(
                V, F, "cyl", n_sweeps=20, seed=seed, multires=True, with_curvature=False
            ),
        )
    return out


# --------------------------------------------------------------------------
# hierarchy construction
# --------------------------------------------------------------------------


def test_hierarchy_vertex_count_is_strictly_decreasing(cylinder) -> None:
    V, F = cylinder
    levels = build_coarsening_hierarchy(V, *_graph_inputs(V, F))
    counts = [lv.n_vertices for lv in levels]
    assert counts[0] == V.shape[0], "level 0 must be the input mesh"
    assert len(counts) > 1, "a 256-vertex mesh must admit at least one coarsening"
    assert all(b < a for a, b in zip(counts, counts[1:])), counts


def test_hierarchy_is_deterministic_and_carries_no_rng(cylinder) -> None:
    """Two builds must be byte-identical.

    The matching is a pure function of positions/normals/areas/adjacency --
    there is deliberately no ``seed`` parameter on the builder at all -- so
    this is stronger than "reproducible for a fixed seed": it is reproducible
    full stop, which is what makes the multires numbers comparable across
    runs.
    """
    V, F = cylinder
    args = _graph_inputs(V, F)
    a = build_coarsening_hierarchy(V, *args)
    b = build_coarsening_hierarchy(V, *args)
    assert len(a) == len(b)
    for la, lb in zip(a, b):
        assert np.array_equal(la.positions, lb.positions)
        assert np.array_equal(la.normals, lb.normals)
        assert np.array_equal(la.areas, lb.areas)
        assert np.array_equal(la.edges, lb.edges)
        assert (la.parent is None) == (lb.parent is None)
        if la.parent is not None and lb.parent is not None:
            assert np.array_equal(la.parent, lb.parent)


def test_hierarchy_respects_max_levels_and_min_vertices(cylinder) -> None:
    V, F = cylinder
    args = _graph_inputs(V, F)
    capped = build_coarsening_hierarchy(V, *args, max_levels=3)
    assert len(capped) == 3
    floored = build_coarsening_hierarchy(V, *args, min_vertices=100)
    assert all(lv.n_vertices >= 100 for lv in floored[:-1])
    assert floored[-1].n_vertices < 256


def test_hierarchy_parent_maps_are_valid_surjective_clusterings(cylinder) -> None:
    V, F = cylinder
    levels = build_coarsening_hierarchy(V, *_graph_inputs(V, F))
    for k in range(len(levels) - 1):
        parent = levels[k].parent
        assert parent is not None, "every non-coarsest level must know its parent map"
        assert parent.shape[0] == levels[k].n_vertices
        n_coarse = levels[k + 1].n_vertices
        assert parent.min() >= 0 and parent.max() == n_coarse - 1
        sizes = np.bincount(parent, minlength=n_coarse)
        assert sizes.min() >= 1, "no empty cluster (surjective)"
        assert sizes.max() <= 2, "single-pass matching yields clusters of size 1 or 2"
    assert levels[-1].parent is None


def test_hierarchy_coarse_graphs_are_symmetric_and_loop_free(cylinder) -> None:
    V, F = cylinder
    levels = build_coarsening_hierarchy(V, *_graph_inputs(V, F))
    for lv in levels[1:]:
        assert np.all(lv.edges[:, 0] < lv.edges[:, 1]), "edges are sorted, no self-loops"
        assert len(set(map(tuple, lv.edges.tolist()))) == lv.n_edges, "no duplicates"
        from_adj = {
            (min(i, int(j)), max(i, int(j)))
            for i, nb in enumerate(lv.adjacency)
            for j in nb
        }
        assert from_adj == set(map(tuple, lv.edges.tolist()))


def test_hierarchy_conserves_area_and_keeps_unit_normals(cylinder) -> None:
    V, F = cylinder
    levels = build_coarsening_hierarchy(V, *_graph_inputs(V, F))
    total = float(levels[0].areas.sum())
    for lv in levels:
        assert float(lv.areas.sum()) == pytest.approx(total, rel=1e-12)
        assert np.allclose(np.linalg.norm(lv.normals, axis=1), 1.0)


def test_hierarchy_terminates_when_no_pair_can_be_matched() -> None:
    """Two isolated vertices cannot be matched, so no coarser level exists."""
    V = np.array([[0.0, 0.0, 0.0], [1.0, 0.0, 0.0]])
    normals = np.array([[0.0, 0.0, 1.0], [0.0, 0.0, 1.0]])
    areas = np.ones(2)
    adjacency = [np.array([], dtype=np.int64), np.array([], dtype=np.int64)]
    edges = np.zeros((0, 2), dtype=np.int64)
    levels = build_coarsening_hierarchy(
        V, normals, areas, adjacency, edges, min_vertices=1
    )
    assert len(levels) == 1
    assert levels[0].parent is None


# --------------------------------------------------------------------------
# prolongation
# --------------------------------------------------------------------------


def test_prolongation_is_tangent_and_unit_norm(cylinder) -> None:
    """The frame invariant ``optimize_orientations`` assumes on entry."""
    V, F = cylinder
    levels = build_coarsening_hierarchy(V, *_graph_inputs(V, F))
    coarse = levels[-1]
    Qc = initial_orientation_field(coarse.normals, seed=1)
    for k in range(len(levels) - 2, -1, -1):
        fine, above = levels[k], levels[k + 1]
        assert fine.parent is not None
        ref = initial_orientation_field(fine.normals, seed=1)
        Qf = prolongate_orientations(Qc, above.normals, fine.normals, fine.parent, ref)
        assert Qf.shape == fine.normals.shape
        assert np.allclose(np.linalg.norm(Qf, axis=1), 1.0, atol=1e-12)
        assert np.allclose(np.sum(Qf * fine.normals, axis=1), 0.0, atol=1e-12)
        Qc = Qf


def test_prolongation_without_a_reference_still_yields_a_valid_frame(cylinder) -> None:
    V, F = cylinder
    levels = build_coarsening_hierarchy(V, *_graph_inputs(V, F))
    fine, above = levels[0], levels[1]
    assert fine.parent is not None
    Qc = initial_orientation_field(above.normals, seed=4)
    Qf = prolongate_orientations(Qc, above.normals, fine.normals, fine.parent)
    assert np.allclose(np.linalg.norm(Qf, axis=1), 1.0, atol=1e-12)
    assert np.allclose(np.sum(Qf * fine.normals, axis=1), 0.0, atol=1e-12)


def test_prolongation_onto_identical_normals_preserves_the_4rosy_class() -> None:
    """With no normal change there is nothing to project, so the child must
    land in the parent's own 4-RoSy class -- i.e. at zero pair energy."""
    n = np.array([0.0, 0.0, 1.0])
    coarse_N = np.array([n])
    coarse_Q = np.array([[np.sqrt(0.5), np.sqrt(0.5), 0.0]])
    fine_N = np.tile(n, (3, 1))
    parent = np.zeros(3, dtype=np.int64)
    ref = initial_orientation_field(fine_N, seed=2)
    Qf = prolongate_orientations(coarse_Q, coarse_N, fine_N, parent, ref)
    for i in range(3):
        e = orientation_energy(
            np.vstack([Qf[i], coarse_Q[0]]),
            np.vstack([n, n]),
            np.array([[0, 1]], dtype=np.int64),
        )
        assert e == pytest.approx(0.0, abs=1e-20)


def test_prolongation_recovers_a_frame_when_the_projection_degenerates() -> None:
    """Parent representative parallel to the child normal: the plane
    projection collapses and the parallel-transport fallback must take over
    rather than emitting a zero (non-unit, non-tangent) vector."""
    coarse_N = np.array([[0.0, 0.0, 1.0]])
    coarse_Q = np.array([[1.0, 0.0, 0.0]])
    fine_N = np.array([[1.0, 0.0, 0.0]])  # exactly parallel to coarse_Q
    parent = np.zeros(1, dtype=np.int64)
    Qf = prolongate_orientations(coarse_Q, coarse_N, fine_N, parent)
    assert float(np.linalg.norm(Qf[0])) == pytest.approx(1.0, abs=1e-12)
    assert float(np.dot(Qf[0], fine_N[0])) == pytest.approx(0.0, abs=1e-12)


# --------------------------------------------------------------------------
# sweep budget
# --------------------------------------------------------------------------


def test_allocate_sweeps_conserves_the_total_budget() -> None:
    for n_levels in range(1, 9):
        for budget in (0, 1, 5, 20, 60):
            alloc = allocate_sweeps(n_levels, budget)
            assert len(alloc) == n_levels
            assert sum(alloc) == budget
            assert max(alloc) - min(alloc) <= 1, "as even as an integer split allows"


def test_multires_spends_exactly_the_single_resolution_budget(cylinder) -> None:
    V, F = cylinder
    r = run_rosy_diagnostic(V, F, "cyl", n_sweeps=20, multires=True, with_curvature=False)
    assert r.multires is not None
    assert r.multires.total_sweeps == 20
    assert sum(r.multires.sweeps_per_level) == 20
    assert r.multires.n_levels == len(r.multires.vertex_counts)


# --------------------------------------------------------------------------
# Poincare-Hopf under multires -- the falsification gate
# --------------------------------------------------------------------------


@pytest.mark.parametrize("seed", SEEDS)
def test_multires_octahedron_indices_still_sum_to_chi(seed: int) -> None:
    """Same theorem as the single-resolution octahedron test.

    The octahedron is small enough that the hierarchy has to be forced with
    ``min_hierarchy_vertices=2``; that is the point -- it exercises a real
    3-level cascade (6 -> 4 -> 2) on a shape whose right answer is known.
    Multires additionally drives the edge energy to *exactly* zero here, which
    single-resolution does not, while the 8 forced +1/4 singularities remain:
    the index is a topological obstruction, not an energetic one.
    """
    V, F = _octahedron()
    r = run_rosy_diagnostic(
        V, F, "octahedron", n_sweeps=30, seed=seed, multires=True,
        min_hierarchy_vertices=2, with_curvature=False,
    )
    assert r.multires is not None and r.multires.n_levels >= 2
    assert r.poincare_hopf_ok
    assert r.index_sum == 8 == 4 * r.euler_characteristic
    assert r.index_histogram == {1: 8}
    assert r.intrinsic is not None and r.intrinsic.poincare_hopf_ok
    assert r.energy_after < 1e-9


def test_multires_cube_keeps_the_eight_corner_singularities(cube) -> None:
    """The cube has only 8 welded vertices, so under the default
    ``min_hierarchy_vertices=16`` the hierarchy degenerates to a single level
    and multires is *identical* to single-resolution -- asserted here so the
    degenerate path stays exercised.  Forcing a hierarchy on it changes the
    energy by ~0.3% and nothing about the singularity structure."""
    V, F = cube
    default = run_rosy_diagnostic(V, F, "cube", n_sweeps=20, multires=True)
    single = run_rosy_diagnostic(V, F, "cube", n_sweeps=20)
    assert default.multires is not None and default.multires.n_levels == 1
    assert default.energy_after == single.energy_after
    assert default.index_histogram == single.index_histogram == {1: 8}

    forced = run_rosy_diagnostic(
        V, F, "cube", n_sweeps=20, multires=True, min_hierarchy_vertices=4
    )
    assert forced.multires is not None and forced.multires.n_levels >= 2
    assert forced.poincare_hopf_ok
    assert forced.n_singularities == 8
    assert forced.index_histogram == {1: 8}


def test_multires_cylinder_satisfies_poincare_hopf(cylinder_sweep) -> None:
    for _single, multi in cylinder_sweep.values():
        assert multi.closed
        assert multi.euler_characteristic == 0
        assert multi.poincare_hopf_ok
        assert multi.intrinsic is not None and multi.intrinsic.poincare_hopf_ok


def test_multires_bracket_satisfies_poincare_hopf(bracket_sweep) -> None:
    for _single, multi in bracket_sweep.values():
        assert multi.closed
        assert multi.euler_characteristic == -4
        assert multi.poincare_hopf_reconcilable
        assert multi.intrinsic is not None
        assert multi.intrinsic.poincare_hopf_reconcilable


def test_multires_does_not_repair_the_tetrahedron_sampling_limit() -> None:
    """The coarse-index aliasing pinned by
    ``test_tetrahedron_is_too_coarse_for_a_faithful_index`` is a property of
    the *mesh*, so a hierarchy cannot fix it -- and does not.  Asserted so a
    future card that changes the index readout flips this test instead of
    quietly improving a number nobody checked."""
    V, F = _tetrahedron()
    r = run_rosy_diagnostic(
        V, F, "tetrahedron", n_sweeps=30, multires=True,
        min_hierarchy_vertices=2, with_curvature=False,
    )
    assert r.index_sum == 4, "still the aliased value; 4 * chi would be 8"
    assert not r.poincare_hopf_reconcilable


# --------------------------------------------------------------------------
# multires vs single-resolution at a matched sweep budget
# --------------------------------------------------------------------------


def test_flat_patch_multires_relaxes_further_than_single_resolution() -> None:
    """A plane admits a perfectly smooth field, so lower is strictly better
    and there is no local-minimum ambiguity to argue about.  Measured:
    8.2e-7 single-resolution vs 5.6e-12 multires at 30 sweeps."""
    V, F = _flat_grid(5)
    single = run_rosy_diagnostic(V, F, "grid", n_sweeps=30, with_curvature=False)
    multi = run_rosy_diagnostic(
        V, F, "grid", n_sweeps=30, multires=True, with_curvature=False
    )
    assert multi.multires is not None and multi.multires.n_levels >= 2
    assert multi.energy_after < single.energy_after
    assert multi.n_singularities == 0 == single.n_singularities


@pytest.mark.parametrize("seed", (0, 1, 2))
def test_cylinder_multires_beats_single_resolution_at_matched_budget(
    cylinder_sweep, seed: int
) -> None:
    """The card's headline comparison: same 20-sweep budget, strictly lower
    energy.  Measured margins at seeds 0/1/2 are 4.9% / 3.3% / 2.3%, and
    multires wins 5/5 seeds at both 20 and 30 sweeps."""
    single, multi = cylinder_sweep[seed]
    assert multi.energy_after < single.energy_after
    assert multi.energy_before == single.energy_before, "same starting field"


def test_bracket_multires_is_within_tolerance_and_far_more_stable(
    bracket_sweep,
) -> None:
    """The documented exception to "multires energy <= single-res energy".

    Multires wins 4 of 5 seeds on the bracket (ratios 0.961-0.999) but
    *loses* at seed 1, where single-resolution happened to fall into a
    slightly better minimum: 43.72 vs 44.11, a ratio of 1.0088.  So the
    matched-budget energy assertion is stated with a 2% tolerance rather than
    as a strict inequality -- claiming strictness would be false.

    What is unambiguous is the variance.  Across the same five seeds the
    single-resolution result spans 2.17 energy units while multires spans
    0.004 -- a ~580x reduction.  Coarse-to-fine continuation is not reliably
    finding a *lower* minimum on this shape; it is reliably finding the
    *same* one, which is the property a downstream integer solver actually
    needs.
    """
    singles = np.array([s.energy_after for s, _ in bracket_sweep.values()])
    multis = np.array([m.energy_after for _, m in bracket_sweep.values()])
    assert np.all(multis <= singles * 1.02)
    assert multis.mean() < singles.mean()
    single_spread = float(singles.max() - singles.min())
    multi_spread = float(multis.max() - multis.min())
    assert multi_spread < single_spread / 10.0, (single_spread, multi_spread)


def test_bracket_connection_disagreement_survives_multires(bracket_sweep) -> None:
    """The card's falsifiable question, answered in the negative.

    QUAD-ROSY1 found the extrinsic and intrinsic readouts disagreeing on the
    bracket's ambiguous +-1/2 faces (18 vs 4) and asked whether that was an
    artifact of single-resolution relaxation stalling in a local minimum.  It
    is not: the split is 18/4 under *every* seed in *both* modes.  It is a
    geometric property of the bracket's sharp edges -- the two discrete
    connections genuinely differ where the normal turns by ~90 degrees across
    an edge -- so no amount of better optimization will close it, and
    ``QUAD-POSY1`` cannot rely on the gap going away.
    """
    for seed, (single, multi) in bracket_sweep.items():
        assert multi.intrinsic is not None and single.intrinsic is not None
        assert multi.n_half_index == 18, seed
        assert multi.intrinsic.n_half_index == 4, seed
        assert multi.intrinsic.n_half_index < multi.n_half_index
        # single-resolution lands on the same split (18/4) at 4 of 5 seeds and
        # on 19/4 at seed 2 -- never anywhere near agreement.
        assert single.n_half_index >= 18
        assert single.intrinsic.n_half_index == 4


# --------------------------------------------------------------------------
# discipline: determinism, no mutation, default unchanged
# --------------------------------------------------------------------------


def test_multires_is_deterministic_for_a_fixed_seed(bracket) -> None:
    V, F = bracket
    a = run_rosy_diagnostic(
        V, F, "b", n_sweeps=20, seed=2, multires=True, with_curvature=False
    )
    b = run_rosy_diagnostic(
        V, F, "b", n_sweeps=20, seed=2, multires=True, with_curvature=False
    )
    assert a.energy_after == b.energy_after
    assert a.index_sum == b.index_sum
    assert [s.face for s in a.singularities] == [s.face for s in b.singularities]
    assert a.multires is not None and b.multires is not None
    assert a.multires.vertex_counts == b.multires.vertex_counts


def test_multires_does_not_mutate_the_input_mesh() -> None:
    V, F = _flat_grid(6)
    V_in, F_in = V.copy(), F.copy()
    run_rosy_diagnostic(V, F, "grid", n_sweeps=10, multires=True)
    assert np.array_equal(V, V_in)
    assert np.array_equal(F, F_in)


def test_single_resolution_remains_the_untouched_default(cylinder) -> None:
    """QUAD-ROSY1's numbers must be reproducible after this card."""
    V, F = cylinder
    default = run_rosy_diagnostic(V, F, "cyl", n_sweeps=10, seed=3, with_curvature=False)
    explicit = run_rosy_diagnostic(
        V, F, "cyl", n_sweeps=10, seed=3, multires=False, with_curvature=False
    )
    assert default.multires is None
    assert default.energy_after == explicit.energy_after
    assert len(default.energy_trace) == default.n_sweeps + 1
