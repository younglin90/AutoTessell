"""DD-series (BETA2785-2790) unit tests — low memory."""
from __future__ import annotations

import numpy as np
import pytest


def _regular_tet():
    pts = np.array(
        [[0, 0, 0], [1, 0, 0],
         [0.5, np.sqrt(3) / 2, 0],
         [0.5, np.sqrt(3) / 6, np.sqrt(2 / 3)]],
        dtype=np.float64,
    )
    tets = np.array([[0, 1, 2, 3]], dtype=np.int64)
    return pts, tets


def _sliver_tet():
    pts = np.array(
        [[0, 0, 0], [1, 0, 0], [0, 1, 0], [0.001, 0.001, 0]],
        dtype=np.float64,
    )
    tets = np.array([[0, 1, 2, 3]], dtype=np.int64)
    return pts, tets


def test_dd1_collapse_score_sliver():
    from core.analyzer.edge_collapse_score import edge_collapse_priority
    pts, tets = _sliver_tet()
    edges, scores, r = edge_collapse_priority(pts, tets, q_threshold=1.0)
    assert r.n_candidates >= 1
    assert scores[0] > 0


def test_dd1_collapse_score_empty():
    from core.analyzer.edge_collapse_score import edge_collapse_priority
    edges, scores, r = edge_collapse_priority(
        np.zeros((0, 3), dtype=np.float64),
        np.zeros((0, 4), dtype=np.int64),
    )
    assert r.n_candidates == 0


def test_dd2_sharp_corners_cube():
    from core.analyzer.sharp_corners import detect_sharp_corners
    V = np.array([
        [0, 0, 0], [1, 0, 0], [1, 1, 0], [0, 1, 0],
        [0, 0, 1], [1, 0, 1], [1, 1, 1], [0, 1, 1],
    ], dtype=np.float64)
    F = np.array([
        [0, 2, 1], [0, 3, 2], [4, 5, 6], [4, 6, 7],
        [0, 1, 5], [0, 5, 4], [2, 3, 7], [2, 7, 6],
        [1, 2, 6], [1, 6, 5], [3, 0, 4], [3, 4, 7],
    ], dtype=np.int64)
    is_corner, r = detect_sharp_corners(V, F, angle_threshold_deg=60.0)
    # cube: all 8 corners are sharp (90° edges).
    assert r.n_sharp_corners == 8


def test_dd2_sharp_corners_empty():
    from core.analyzer.sharp_corners import detect_sharp_corners
    is_corner, r = detect_sharp_corners(
        np.zeros((0, 3), dtype=np.float64),
        np.zeros((0, 3), dtype=np.int64),
    )
    assert r.n_vertices == 0


def test_dd3_model_size_estimator():
    pytest.importorskip("torch")
    import torch.nn as nn
    from core.generator.native_ai.model_size import estimate_model_size

    m = nn.Sequential(nn.Linear(8, 16), nn.ReLU(), nn.Linear(16, 1))
    r = estimate_model_size(m)
    # 8*16+16 + 16*1+1 = 144 + 17 = 161.
    assert r.n_parameters == 161
    assert r.n_layers == 2
    # FLOPs: 2*(8*16) + 2*(16*1) = 288.
    assert r.flops_per_sample == 288


def test_dd4_bench_worst_runs(tmp_path):
    """smoke: script runs."""
    import json
    import subprocess
    import sys
    p = tmp_path / "x.json"
    p.write_text(json.dumps([
        {"file_id": 1, "engine": "tet", "tier": "easy", "grade": "A", "mq": 0.4},
        {"file_id": 2, "engine": "tet", "tier": "easy", "grade": "D", "mq": 0.05},
    ]))
    res = subprocess.run(
        [sys.executable, "scripts/bench_worst_mesh.py", str(p), "--top", "2"],
        capture_output=True, text=True, timeout=20,
    )
    assert res.returncode == 0
    assert "fid" in res.stdout


def test_dd5_hex_skew_simple_cube():
    from core.evaluator.hex_skew_simple import hex_skew_simple
    pts = np.array([
        [0, 0, 0], [1, 0, 0], [1, 1, 0], [0, 1, 0],
        [0, 0, 1], [1, 0, 1], [1, 1, 1], [0, 1, 1],
    ], dtype=np.float64)
    hexes = np.array([[0, 1, 2, 3, 4, 5, 6, 7]], dtype=np.int64)
    r = hex_skew_simple(pts, hexes)
    # cube: dist 0.5, sqrt(area)=1 → skew=0.5.
    assert abs(r.skew_max - 0.5) < 1e-9
    assert r.n_above_1 == 0


def test_dd5_hex_skew_simple_empty():
    from core.evaluator.hex_skew_simple import hex_skew_simple
    r = hex_skew_simple(
        np.zeros((0, 3), dtype=np.float64),
        np.zeros((0, 8), dtype=np.int64),
    )
    assert r.n_hexes == 0


def test_dd6_poly_aspect_cube():
    from core.evaluator.poly_aspect import poly_cell_aspect
    pts = np.array([
        [0, 0, 0], [1, 0, 0], [1, 1, 0], [0, 1, 0],
        [0, 0, 1], [1, 0, 1], [1, 1, 1], [0, 1, 1],
    ], dtype=np.float64)
    cells = [np.arange(8)]
    r = poly_cell_aspect(pts, cells)
    assert abs(r.aspect_max - 1.0) < 1e-9
    assert r.n_above_5 == 0


def test_dd6_poly_aspect_stretched():
    from core.evaluator.poly_aspect import poly_cell_aspect
    pts = np.array([
        [0, 0, 0], [10, 0, 0], [10, 1, 0], [0, 1, 0],
        [0, 0, 1], [10, 0, 1], [10, 1, 1], [0, 1, 1],
    ], dtype=np.float64)
    r = poly_cell_aspect(pts, [np.arange(8)])
    assert r.aspect_max == 10.0
    assert r.n_above_5 == 1
