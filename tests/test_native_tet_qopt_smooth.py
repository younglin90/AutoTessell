"""QOPT guarded smoothing tests."""
from __future__ import annotations

import numpy as np

from core.generator.native_tet.smooth import smooth_interior


def test_qopt_quality_guard_rejects_global_laplacian_quality_drop() -> None:
    points = np.array(
        [
            [0.0, 0.0, 0.0],
            [1.0, 0.0, 0.0],
            [0.0, 1.0, 0.0],
            [0.0, 0.0, 1.0],
        ],
        dtype=np.float64,
    )
    tets = np.array([[0, 1, 2, 3]], dtype=np.int64)
    locked = np.array([0, 1, 2], dtype=np.int64)

    guarded = points.copy()
    result = smooth_interior(
        guarded, tets, locked_vertex_ids=locked, n_iter=1, relax=0.9,
        quality_guard=True,
    )

    assert result.n_interior_moved == 0
    assert result.max_displacement == 0.0
    assert result.qopt_attempted == 1
    assert result.qopt_accepted == 0
    assert result.qopt_rejected_quality == 1
    assert np.array_equal(guarded, points)


def test_unchecked_laplacian_still_moves_when_guard_disabled() -> None:
    points = np.array(
        [
            [0.0, 0.0, 0.0],
            [1.0, 0.0, 0.0],
            [0.0, 1.0, 0.0],
            [0.0, 0.0, 1.0],
        ],
        dtype=np.float64,
    )
    tets = np.array([[0, 1, 2, 3]], dtype=np.int64)
    locked = np.array([0, 1, 2], dtype=np.int64)

    unchecked = points.copy()
    result = smooth_interior(
        unchecked, tets, locked_vertex_ids=locked, n_iter=1, relax=0.9,
        quality_guard=False,
    )

    assert result.n_interior_moved == 1
    assert result.max_displacement > 0.0
    assert result.qopt_attempted == 0
    assert result.qopt_accepted == 0
    assert not np.array_equal(unchecked, points)


def test_qopt_smooth_benchmark_smoke() -> None:
    from argparse import Namespace

    from scripts.benchmark_native_tet_qopt_smooth import benchmark

    result = benchmark(
        Namespace(grid=4, iters=1, relax=0.25, perturb=0.08, repeat=1, out=None)
    )
    assert result["points"] == 64
    assert result["tets"] > 0
    assert result["guarded_mean_elapsed_s"] >= 0.0
    assert result["unguarded_mean_elapsed_s"] >= 0.0
    guarded_rows = [row for row in result["rows"] if row["guarded"]]
    assert guarded_rows[0]["qopt_attempted"] > 0
