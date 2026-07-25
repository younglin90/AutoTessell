"""FSL Wave 1 -- Dassi lazy compound flips + Ni/Shewchuk multi-face removal
diagnostic (``core/generator/native_tet/fsl_wave1.py``)."""
from __future__ import annotations

import numpy as np

from core.generator.native_tet.fsl_wave1 import (
    diagnose_wedge,
    find_core_unflippable_wedges,
    general_edge_removal,
    run_wave1_diagnostic,
)
from core.generator.native_tet.validate import flat_allsurf_sliver_candidates


def _vol6_sum(pts: np.ndarray, tets: np.ndarray) -> float:
    v = pts[tets]
    return float(np.abs(
        np.einsum("ij,ij->i", v[:, 1] - v[:, 0], np.cross(v[:, 2] - v[:, 0], v[:, 3] - v[:, 0]))
    ).sum())


def _octahedron(thin_axis: float = 3.0):
    """Octahedron split into 4 thin kite tets around a long A-B diagonal.

    A shorter equatorial diagonal (e.g. C-E) tiles the same bipyramid with
    much better-shaped tets -- a genuine, non-degenerate improving
    retriangulation for ``general_edge_removal`` to find.
    """
    a = np.array([0.0, 0.0, thin_axis])
    b = np.array([0.0, 0.0, -thin_axis])
    c = np.array([1.0, 0.0, 0.0])
    d = np.array([0.0, 1.0, 0.0])
    e = np.array([-1.0, 0.0, 0.0])
    f = np.array([0.0, -1.0, 0.0])
    pts = np.array([a, b, c, d, e, f])
    tets = np.array(
        [[0, 1, 2, 3], [0, 1, 3, 4], [0, 1, 4, 5], [0, 1, 5, 2]], dtype=np.int64,
    )
    return pts, tets


def test_general_edge_removal_octahedron_improves_and_tiles_exactly() -> None:
    pts, tets = _octahedron()
    vol_before = _vol6_sum(pts, tets)

    new_tets, info = general_edge_removal(pts, tets, 0, 1, exhaustive=True)
    assert new_tets is not None, info
    assert info["reason"] == "applied"
    assert info["q_new"] > info["q_old"]  # thin diagonal -> fatter alternative
    assert _vol6_sum(pts, new_tets) == vol_before  # exact tiling identity
    # (a, b) edge must be gone.
    for t in new_tets:
        assert not (0 in t and 1 in t)


def test_general_edge_removal_lazy_matches_exhaustive_on_octahedron() -> None:
    pts, tets = _octahedron()
    lazy_tets, lazy_info = general_edge_removal(pts, tets, 0, 1, exhaustive=False)
    assert lazy_tets is not None
    assert lazy_info["q_new"] > lazy_info["q_old"]


def test_general_edge_removal_rejects_ring_too_small() -> None:
    pts, tets = _octahedron()
    # C-D (index 2-3) only borders 2 tets -- not a valid edge-removal ring.
    new_tets, info = general_edge_removal(pts, tets, 2, 3, exhaustive=True)
    assert new_tets is None
    assert info["reason"] == "ring_too_small"


def test_find_core_unflippable_wedges_matches_fsl1_count() -> None:
    """Same fixture as
    ``test_native_tet_flat_sliver_detect.test_two_boundary_face_wedge_is_core_unflippable``
    -- Wave 1's independent classifier must reproduce FSL1's count exactly."""
    eps = 1e-6
    p0 = np.array([0.0, 0.0, 0.0])
    p1 = np.array([1.0, 0.0, 0.0])
    p2 = np.array([0.0, 1.0, 0.0])
    p3 = np.array([0.3, 0.3, eps])
    p4 = np.array([0.3, 0.3, -1.0])
    p5 = np.array([0.1, 0.4, -1.0])
    pts = np.array([p0, p1, p2, p3, p4, p5])
    tets = np.array([[0, 1, 2, 3], [1, 2, 3, 4], [0, 2, 3, 5]], dtype=np.int64)

    r = flat_allsurf_sliver_candidates(pts, tets, n_surface_vertices=6)
    assert r["n_core_unflippable"] == 1

    wedges = find_core_unflippable_wedges(pts, tets, n_surface_vertices=6)
    assert len(wedges) == 1
    w = wedges[0]
    assert w["tet_index"] == 0
    assert set(w["ridge_edge"]) == {0, 1}
    assert set(w["far_edge"]) == {2, 3}


def test_diagnose_wedge_tiny_mesh_is_structurally_blocked_no_mutation() -> None:
    """The minimal 3-tet fixture has no surrounding mesh for a compound flip
    to draw on (every candidate edge's ring is either the boundary itself or
    too small) -- Wave 1 must report ``structurally_blocked`` and leave the
    mesh byte-for-byte unchanged (never partially apply)."""
    eps = 1e-6
    p0 = np.array([0.0, 0.0, 0.0])
    p1 = np.array([1.0, 0.0, 0.0])
    p2 = np.array([0.0, 1.0, 0.0])
    p3 = np.array([0.3, 0.3, eps])
    p4 = np.array([0.3, 0.3, -1.0])
    p5 = np.array([0.1, 0.4, -1.0])
    pts = np.array([p0, p1, p2, p3, p4, p5])
    tets = np.array([[0, 1, 2, 3], [1, 2, 3, 4], [0, 2, 3, 5]], dtype=np.int64)

    wedges = find_core_unflippable_wedges(pts, tets, n_surface_vertices=6)
    out_tets, diag = diagnose_wedge(pts, tets, wedges[0], max_depth=2)
    assert diag.classification == "structurally_blocked"
    assert np.array_equal(out_tets, tets)

    final_tets, report = run_wave1_diagnostic(pts, tets, n_surface_vertices=6)
    assert report["n_wedges"] == 1
    assert report["n_structurally_blocked"] == 1
    assert report["n_combinatorially_unlocked"] == 0
    assert np.array_equal(final_tets, tets)


def test_run_wave1_diagnostic_no_wedges_is_noop() -> None:
    p0 = np.array([0.0, 0.0, 0.0])
    p1 = np.array([1.0, 0.0, 0.0])
    p2 = np.array([0.5, np.sqrt(3) / 2, 0.0])
    p3 = np.array([0.5, np.sqrt(3) / 6, np.sqrt(2.0 / 3.0)])
    pts = np.array([p0, p1, p2, p3])
    tets = np.array([[0, 1, 2, 3]], dtype=np.int64)
    final_tets, report = run_wave1_diagnostic(pts, tets, n_surface_vertices=4)
    assert report["n_wedges"] == 0
    assert np.array_equal(final_tets, tets)
