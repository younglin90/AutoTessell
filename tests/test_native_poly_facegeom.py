"""POLY-AGGLOM-FACEGEOM1 -- unit + real-shape tests for interface merging.

The synthetic tests pin the loop-extraction contract (what is merged, what is
refused, and that the vector-area identity holds).  The real-shape tests run
the same tet primal through the facet-union build and the merged build and
check the invariants that make the merged variant a legitimate comparison
rather than a different mesh: identical boundary faces, identical total
volume, and no new negative cells.

``generate_native_tet`` is called exactly once per module (session-scoped
fixture) -- calling it twice in one pytest process on a non-trivial mesh has a
known non-deterministic native crash (``.claude/rules/lessons-learned.md``).
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest

from core.generator.native_poly.facegeom_experiment import (
    _closed_cell_volume,
    _facet_components,
    _patch_boundary_loop,
    _patch_vector_area,
    _polygon_vector_area,
    build_merged_cell_faces,
)

REPO = Path(__file__).resolve().parents[1]
CUBE = REPO / "tests" / "benchmarks" / "cube.stl"


# ---------------------------------------------------------------------------
# Boundary-loop extraction
# ---------------------------------------------------------------------------


def test_two_triangle_square_merges_to_quad():
    """The canonical case: two CCW triangles -> one 4-gon, same vector area."""
    pts = np.array([[0.0, 0, 0], [1, 0, 0], [1, 1, 0], [0, 1, 0]])
    tris = [(0, 1, 2), (0, 2, 3)]

    loop, reason = _patch_boundary_loop(tris)
    assert reason == "ok"
    assert loop == [0, 1, 2, 3]

    np.testing.assert_allclose(
        _polygon_vector_area(pts, loop), _patch_vector_area(pts, tris), atol=1e-12
    )
    # +z normal, unit area
    np.testing.assert_allclose(_polygon_vector_area(pts, loop), [0, 0, 1.0], atol=1e-12)


def test_patch_with_hole_is_rejected():
    """An annular patch has two boundary loops and cannot be one polygon."""
    outer = [[0.0, 0, 0], [2, 0, 0], [2, 2, 0], [0, 2, 0]]
    inner = [[0.5, 0.5, 0], [1.5, 0.5, 0], [1.5, 1.5, 0], [0.5, 1.5, 0]]
    pts = np.array(outer + inner)
    tris: list[tuple[int, int, int]] = []
    for i in range(4):
        o0, o1 = i, (i + 1) % 4
        i0, i1 = 4 + i, 4 + (i + 1) % 4
        tris.append((o0, o1, i1))
        tris.append((o0, i1, i0))

    # sanity: the annulus is one face-connected component
    assert len(_facet_components(tris)) == 1
    loop, reason = _patch_boundary_loop(tris)
    assert loop is None
    assert reason == "multiple_loops"


def test_vertex_touching_triangles_split_into_two_components():
    """Touching at a single vertex is not face adjacency -- split, never pinch."""
    pts = np.array([[0.0, 0, 0], [1, 0, 0], [1, 1, 0], [2, 1, 0], [2, 2, 0]])
    tris = [(0, 1, 2), (2, 3, 4)]
    comps = _facet_components(tris)
    assert len(comps) == 2
    assert sorted(len(c) for c in comps) == [1, 1]


def test_jagged_patch_preserves_vector_area_exactly():
    """Vector area is a boundary integral: out-of-plane wiggle must not change it."""
    rng = np.random.default_rng(20260726)
    # a 3x3 grid whose interior vertex is pushed far out of plane
    xs, ys = np.meshgrid(np.linspace(0, 1, 3), np.linspace(0, 1, 3))
    pts = np.stack([xs.ravel(), ys.ravel(), np.zeros(9)], axis=1)
    interior = [4]
    pts[interior, 2] = 0.7
    pts[[0, 2, 6, 8], 2] += rng.normal(0, 0.0, 4)  # corners stay planar

    tris: list[tuple[int, int, int]] = []
    for r in range(2):
        for c in range(2):
            a = r * 3 + c
            b = a + 1
            d = a + 3
            e = d + 1
            tris.append((a, b, e))
            tris.append((a, e, d))

    loop, reason = _patch_boundary_loop(tris)
    assert reason == "ok"
    assert len(loop) == 8  # perimeter of the 3x3 grid
    np.testing.assert_allclose(
        _polygon_vector_area(pts, loop), _patch_vector_area(pts, tris), atol=1e-12
    )
    # the jagged patch has strictly more scalar area than its spanning polygon
    scalar = sum(
        0.5 * float(np.linalg.norm(np.cross(pts[b] - pts[a], pts[c] - pts[a]))) for a, b, c in tris
    )
    assert scalar > float(np.linalg.norm(_polygon_vector_area(pts, loop))) + 1e-6


def test_duplicate_triangle_is_rejected():
    pts = np.array([[0.0, 0, 0], [1, 0, 0], [1, 1, 0]])
    del pts
    loop, reason = _patch_boundary_loop([(0, 1, 2), (0, 1, 2)])
    assert loop is None
    assert reason == "repeated_directed_edge"


def test_closed_cell_volume_on_unit_cube():
    """Volume helper sanity: outward-oriented unit cube must give +1."""
    pts = np.array(
        [
            [0.0, 0, 0],
            [1, 0, 0],
            [1, 1, 0],
            [0, 1, 0],
            [0, 0, 1],
            [1, 0, 1],
            [1, 1, 1],
            [0, 1, 1],
        ]
    )
    faces = [
        [0, 3, 2, 1],  # z-
        [4, 5, 6, 7],  # z+
        [0, 1, 5, 4],  # y-
        [2, 3, 7, 6],  # y+
        [1, 2, 6, 5],  # x+
        [0, 4, 7, 3],  # x-
    ]
    assert _closed_cell_volume(pts, faces) == pytest.approx(1.0, abs=1e-12)


# ---------------------------------------------------------------------------
# Real-shape invariants (cube tet primal)
# ---------------------------------------------------------------------------


@pytest.fixture(scope="module")
def cube_primal():
    """One tet primal + one agglomeration, shared by every real-shape test."""
    if not CUBE.exists():
        pytest.skip("cube.stl missing: deterministic native-poly facegeom fixture precondition")
    from core.analyzer.readers.stl import read_stl
    from core.generator.native_poly.agglomeration_experiment import vertex_star_agglomerate
    from core.generator.native_tet import generate_native_tet

    import tempfile

    mesh = read_stl(CUBE)
    with tempfile.TemporaryDirectory() as td:
        res = generate_native_tet(
            mesh.vertices, mesh.faces, Path(td) / "tet", seed_density=10, target_cells=200
        )
    if not res.success or res.tets is None:
        pytest.skip(f"generate_native_tet failed: {res.message}")
    V = np.asarray(res.tet_points, dtype=np.float64)
    T = np.asarray(res.tets, dtype=np.int64)
    return V, T, vertex_star_agglomerate(V, T)


def _boundary_face_keys(cell_faces):
    """Keys appearing exactly once across the mesh = domain boundary faces."""
    from collections import Counter

    counts = Counter()
    for faces in cell_faces:
        for f in faces:
            counts[tuple(sorted(f))] += 1
    return {k for k, c in counts.items() if c == 1}


def test_merge_keeps_boundary_faces_bit_identical(cube_primal):
    """Surface preservation: no boundary facet may be merged, moved, or dropped."""
    from core.generator.native_poly.agglomeration_experiment import (
        build_agglomerated_cell_faces,
    )

    V, T, agg = cube_primal
    union = build_agglomerated_cell_faces(T, agg.block_of)
    merged, _ = build_merged_cell_faces(V, T, agg.block_of)
    assert _boundary_face_keys(union) == _boundary_face_keys(merged)


def test_merge_conserves_total_domain_volume(cube_primal):
    """Interior surface motion cancels between owner and neighbour."""
    from core.generator.native_poly.agglomeration_experiment import (
        build_agglomerated_cell_faces,
    )

    V, T, agg = cube_primal
    union = build_agglomerated_cell_faces(T, agg.block_of)
    merged, _ = build_merged_cell_faces(V, T, agg.block_of)

    v_union = sum(_closed_cell_volume(V, c) for c in union)
    v_merged = sum(_closed_cell_volume(V, c) for c in merged)
    assert v_merged == pytest.approx(v_union, rel=1e-9)


def test_merge_leaves_every_cell_positive_and_closed(cube_primal):
    """The transactional guards must hold on the emitted mesh, not just in intent."""
    V, T, agg = cube_primal
    merged, report = build_merged_cell_faces(V, T, agg.block_of)

    assert report.n_merged > 0, "nothing merged -- diagnostic would be vacuous"
    assert report.duplicate_face_keys == 0
    assert report.unfixable_blocks == 0

    for b, faces in enumerate(merged):
        assert len(faces) >= 4, f"block {b} has {len(faces)} faces"
        assert _closed_cell_volume(V, faces) > 0.0, f"block {b} non-positive volume"
        # closure: the vector areas of a cell's faces must cancel
        acc = np.zeros(3)
        for f in faces:
            acc = acc + _polygon_vector_area(V, f)
        assert float(np.linalg.norm(acc)) < 1e-9


def test_merge_reduces_internal_face_count(cube_primal):
    V, T, agg = cube_primal
    _, report = build_merged_cell_faces(V, T, agg.block_of)
    assert report.n_facets_after_merge < report.n_interface_facets
    assert report.interface_facet_reduction_pct > 50.0


def test_geometric_gate_only_removes_merges(cube_primal):
    """A stricter gate can never merge more than the ungated run."""
    V, T, agg = cube_primal
    _, ungated = build_merged_cell_faces(V, T, agg.block_of)
    _, gated = build_merged_cell_faces(
        V, T, agg.block_of, max_planar_deviation=0.05, max_facet_normal_deg=20.0
    )
    assert gated.n_merged <= ungated.n_merged
    assert gated.n_facets_after_merge >= ungated.n_facets_after_merge


def test_merge_is_deterministic(cube_primal):
    V, T, agg = cube_primal
    a, ra = build_merged_cell_faces(V, T, agg.block_of)
    b, rb = build_merged_cell_faces(V, T, agg.block_of)
    assert ra.n_merged == rb.n_merged
    assert [[list(f) for f in c] for c in a] == [[list(f) for f in c] for c in b]
