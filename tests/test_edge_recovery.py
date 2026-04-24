"""Round 50 — edge recovery proposal tests."""
from __future__ import annotations

import numpy as np
import pytest


def test_propose_edge_midpoints_empty() -> None:
    from core.generator.native_tet.edge_recovery import propose_edge_midpoints

    V = np.zeros((0, 3), dtype=np.float64)
    r = propose_edge_midpoints(V, [])
    assert r.n_missing_before == 0
    assert r.new_points.shape == (0, 3)


def test_propose_edge_midpoints_basic() -> None:
    from core.generator.native_tet.edge_recovery import propose_edge_midpoints

    V = np.array([[0, 0, 0], [2, 0, 0], [0, 2, 0]], dtype=np.float64)
    missing = [(0, 1), (1, 2)]
    r = propose_edge_midpoints(V, missing)
    assert r.n_missing_before == 2
    assert r.new_points.shape == (2, 3)
    # (0,1) 중점 = (1,0,0), (1,2) 중점 = (1,1,0).
    assert np.allclose(r.new_points[0], [1, 0, 0])
    assert np.allclose(r.new_points[1], [1, 1, 0])


def test_propose_edge_midpoints_cap() -> None:
    from core.generator.native_tet.edge_recovery import propose_edge_midpoints

    V = np.random.default_rng(0).random((20, 3))
    edges = [(i, i + 1) for i in range(19)]
    r = propose_edge_midpoints(V, edges, max_points=5)
    assert r.new_points.shape[0] == 5
