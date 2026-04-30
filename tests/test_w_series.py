"""W-series (BETA2716-2721) unit tests."""
from __future__ import annotations

import numpy as np


def test_w1_poly_convex_cube():
    from core.evaluator.poly_convex import poly_cell_convex
    pts = np.array([
        [0, 0, 0], [1, 0, 0], [1, 1, 0], [0, 1, 0],
        [0, 0, 1], [1, 0, 1], [1, 1, 1], [0, 1, 1],
    ], dtype=np.float64)
    v_idx = np.arange(8)
    planes = np.array([
        [-1, 0, 0, 0], [1, 0, 0, -1],
        [0, -1, 0, 0], [0, 1, 0, -1],
        [0, 0, -1, 0], [0, 0, 1, -1],
    ], dtype=np.float64)
    r = poly_cell_convex(pts, [v_idx], [planes])
    assert r.n_convex == 1
    assert r.max_violation < 1e-9


def test_w1_poly_convex_violation():
    from core.evaluator.poly_convex import poly_cell_convex
    pts = np.array([
        [0, 0, 0], [1, 0, 0], [1, 1, 0], [0, 1, 0],
        [0, 0, 1], [1, 0, 1], [1.5, 1.5, 0.5], [0, 1, 1],
    ], dtype=np.float64)
    v_idx = np.arange(8)
    planes = np.array([
        [-1, 0, 0, 0], [1, 0, 0, -1],
        [0, -1, 0, 0], [0, 1, 0, -1],
        [0, 0, -1, 0], [0, 0, 1, -1],
    ], dtype=np.float64)
    r = poly_cell_convex(pts, [v_idx], [planes])
    assert r.n_non_convex == 1
    assert r.max_violation > 0.4


def test_w2_bl_quality_perfect():
    from core.evaluator.bl_quality import bl_prism_quality
    pts = np.array([
        [0, 0, 0], [1, 0, 0], [0.5, np.sqrt(3) / 2, 0],
        [0, 0, 0.5], [1, 0, 0.5], [0.5, np.sqrt(3) / 2, 0.5],
    ], dtype=np.float64)
    pr = np.array([[0, 1, 2, 3, 4, 5]], dtype=np.int64)
    r = bl_prism_quality(pts, pr)
    assert abs(r.aspect_mean - 0.5) < 1e-3
    assert r.thickness_uniformity_mean > 0.99
    assert r.n_inverted == 0


def test_w2_bl_quality_empty():
    from core.evaluator.bl_quality import bl_prism_quality
    r = bl_prism_quality(
        np.zeros((0, 3), dtype=np.float64),
        np.zeros((0, 6), dtype=np.int64),
    )
    assert r.n_prisms == 0


def test_w3_train_history_logger(tmp_path):
    from core.generator.native_ai.train_history import (
        TrainHistoryLogger,
        read_history,
    )
    p = tmp_path / "h.csv"
    log = TrainHistoryLogger(path=p)
    for ep in range(1, 4):
        log.append(epoch=ep, train_loss=0.5 / ep, val_loss=0.7 / ep)
    assert log.n_rows() == 3
    rows = read_history(p)
    assert len(rows) == 3
    assert rows[0]["epoch"] == 1
    assert rows[2]["epoch"] == 3


def test_w3_train_history_empty(tmp_path):
    from core.generator.native_ai.train_history import read_history
    rows = read_history(tmp_path / "missing.csv")
    assert rows == []


def test_w4_bench_trend_summarize():
    from scripts.bench_trend import _summarize
    rows = [
        {"engine": "x", "grade": "A", "success": True, "elapsed": 1.0},
        {"engine": "x", "grade": "B", "success": True, "elapsed": 2.0},
        {"engine": "y", "grade": "A", "success": True, "elapsed": 3.0},
    ]
    s = _summarize(rows)
    assert s["n"] == 3
    assert s["A"] == 2
    assert "x" in s["by_engine"]


def test_w5_dedup_vertices_basic():
    from core.utils.dedup_verts import dedup_vertices
    V = np.array([[0, 0, 0], [1, 0, 0], [1, 0, 1e-12], [0, 1, 0]], dtype=np.float64)
    F = np.array([[0, 1, 3], [2, 3, 0]], dtype=np.int64)
    V2, F2, r = dedup_vertices(V, F, tol=1e-9)
    assert r.n_in == 4
    assert r.n_out == 3
    assert r.n_merged == 1
    assert F2.shape == F.shape


def test_w5_dedup_vertices_no_dups():
    from core.utils.dedup_verts import dedup_vertices
    V = np.array([[0, 0, 0], [1, 0, 0], [0, 1, 0]], dtype=np.float64)
    V2, _, r = dedup_vertices(V, F=None, tol=1e-9)
    assert r.n_merged == 0
    assert r.n_out == 3


def test_w5_dedup_vertices_empty():
    from core.utils.dedup_verts import dedup_vertices
    V = np.zeros((0, 3), dtype=np.float64)
    V2, _, r = dedup_vertices(V)
    assert r.n_in == 0


def test_w6_progress_tracker_callback():
    from core.utils.progress_rich import ProgressTracker
    seen: list = []
    p = ProgressTracker(callback=lambda s, pct: seen.append((s, pct)))
    p.report("A", 50)
    p.report("B", 100)
    assert seen == [("A", 50.0), ("B", 100.0)]
    assert p.stage_count() == 2
    assert p.last() == ("B", 100.0)


def test_w6_progress_tracker_clamp():
    from core.utils.progress_rich import ProgressTracker
    seen: list = []
    p = ProgressTracker(callback=lambda s, pct: seen.append(pct))
    p.report("A", -10)
    p.report("B", 200)
    assert seen[0] == 0.0
    assert seen[1] == 100.0
