from __future__ import annotations

import numpy as np


def _accepted_midpoint_fixture() -> tuple[np.ndarray, np.ndarray]:
    pts = np.array(
        [
            [0.0, 0.0, 0.0],
            [1.41420370, -0.35516368, 0.55812771],
            [0.67489156, 0.73023753, 0.69388156],
            [-0.89930215, 0.04422907, 0.55197371],
        ],
        dtype=np.float64,
    )
    tets = np.array([[0, 1, 2, 3]], dtype=np.int64)
    return pts, tets


def test_stellar_edge_midpoint_cleanup_accepts_qopt_improvement() -> None:
    from core.generator.native_tet import qopt
    from core.generator.native_tet.stellar import (
        _tet_quality_batch,
        insert_edge_midpoint_qopt_cleanup,
    )

    pts, tets = _accepted_midpoint_fixture()
    out_pts, out_tets, stats = insert_edge_midpoint_qopt_cleanup(
        pts,
        tets,
        candidate_edges=[(1, 3)],
        max_edges=1,
        min_quality_improvement=1e-6,
        allow_boundary_edges=True,
    )

    assert stats.attempted == 1
    assert stats.accepted == 1
    assert out_pts.shape == (5, 3)
    assert out_tets.shape == (2, 4)
    assert qopt.quality_vector_accepts(
        _tet_quality_batch(pts, tets),
        _tet_quality_batch(out_pts, out_tets),
        eps=1e-6,
    )


def test_stellar_edge_midpoint_cleanup_rejects_quality_loss() -> None:
    from core.generator.native_tet.stellar import insert_edge_midpoint_qopt_cleanup

    pts = np.array(
        [[0, 0, 0], [10, 0, 0], [0, 1, 0], [0, 0, 1]], dtype=np.float64,
    )
    tets = np.array([[0, 1, 2, 3]], dtype=np.int64)

    out_pts, out_tets, stats = insert_edge_midpoint_qopt_cleanup(
        pts,
        tets,
        candidate_edges=[(0, 1)],
        max_edges=1,
        min_quality_improvement=1e-6,
        allow_boundary_edges=True,
    )

    assert stats.attempted == 1
    assert stats.accepted == 0
    assert stats.rejected_quality == 1
    assert np.array_equal(out_pts, pts)
    assert np.array_equal(out_tets, tets)


def test_stellar_edge_midpoint_cleanup_respects_protected_edges() -> None:
    from core.generator.native_tet.stellar import insert_edge_midpoint_qopt_cleanup

    pts, tets = _accepted_midpoint_fixture()
    out_pts, out_tets, stats = insert_edge_midpoint_qopt_cleanup(
        pts,
        tets,
        candidate_edges=[(3, 1)],
        protected_edges={(1, 3)},
        max_edges=1,
        min_quality_improvement=1e-6,
        allow_boundary_edges=True,
    )

    assert stats.attempted == 0
    assert stats.accepted == 0
    assert stats.skipped_protected == 1
    assert np.array_equal(out_pts, pts)
    assert np.array_equal(out_tets, tets)
