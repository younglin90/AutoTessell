"""Y-series (BETA2730-2735) unit tests."""
from __future__ import annotations

import numpy as np
import pytest


def test_y1_tet_valence_fan():
    from core.analyzer.tet_valence import tet_vertex_valence
    tets = np.array([
        [0, 1, 2, 4], [1, 2, 3, 4], [2, 3, 0, 4], [3, 0, 1, 4],
    ], dtype=np.int64)
    val, r = tet_vertex_valence(5, tets)
    assert r.valence_max == 4
    assert r.valence_min == 3
    assert r.n_used == 5


def test_y1_tet_valence_isolated():
    from core.analyzer.tet_valence import tet_vertex_valence
    tets = np.array([[0, 1, 2, 3]], dtype=np.int64)
    val, r = tet_vertex_valence(6, tets)
    assert r.n_isolated == 2
    assert r.valence_min == 1


def test_y1_tet_valence_empty():
    from core.analyzer.tet_valence import tet_vertex_valence
    val, r = tet_vertex_valence(0, np.zeros((0, 4), dtype=np.int64))
    assert r.n_vertices == 0


def test_y2_mean_curvature_cube_corners():
    from core.analyzer.mean_curvature import vertex_mean_curvature
    V = np.array([
        [0, 0, 0], [1, 0, 0], [1, 1, 0], [0, 1, 0],
        [0, 0, 1], [1, 0, 1], [1, 1, 1], [0, 1, 1],
    ], dtype=np.float64)
    F = np.array([
        [0, 2, 1], [0, 3, 2], [4, 5, 6], [4, 6, 7],
        [0, 1, 5], [0, 5, 4], [2, 3, 7], [2, 7, 6],
        [1, 2, 6], [1, 6, 5], [3, 0, 4], [3, 4, 7],
    ], dtype=np.int64)
    H, r = vertex_mean_curvature(V, F)
    assert H.shape == (8, 3)
    assert r.h_norm_max > 0


def test_y2_mean_curvature_empty():
    from core.analyzer.mean_curvature import vertex_mean_curvature
    H, r = vertex_mean_curvature(
        np.zeros((0, 3), dtype=np.float64),
        np.zeros((0, 3), dtype=np.int64),
    )
    assert r.n_vertices == 0


def test_y3_predict_batch_basic():
    pytest.importorskip("torch")
    import torch.nn as nn
    from core.generator.native_ai.eval_batch import predict_batch

    class M(nn.Module):
        def __init__(self):
            super().__init__()
            self.fc = nn.Linear(4, 1)

        def forward(self, x):
            return self.fc(x)

    X = np.random.randn(100, 4).astype(np.float32)
    preds, r = predict_batch(M(), X, batch_size=32)
    assert preds.shape == (100, 1)
    assert r.n_samples == 100
    assert r.n_batches == 4  # 32+32+32+4 = 100.


def test_y3_predict_batch_empty():
    pytest.importorskip("torch")
    import torch.nn as nn
    from core.generator.native_ai.eval_batch import predict_batch

    class M(nn.Module):
        def __init__(self):
            super().__init__()
            self.fc = nn.Linear(4, 1)

        def forward(self, x):
            return self.fc(x)

    X = np.zeros((0, 4), dtype=np.float32)
    preds, r = predict_batch(M(), X)
    assert preds.shape == (0, 1)
    assert r.n_samples == 0


def test_y4_bench_html_basic(tmp_path):
    import json
    import subprocess
    import sys
    p = tmp_path / "x.json"
    p.write_text(json.dumps([
        {"engine": "a", "stl": "x.stl", "grade": "A", "success": True, "elapsed": 1.0},
    ]))
    out = tmp_path / "x.html"
    res = subprocess.run(
        [sys.executable, "scripts/bench_html.py", str(p), "-o", str(out)],
        capture_output=True, text=True, timeout=20,
    )
    assert res.returncode == 0
    assert out.exists()
    content = out.read_text()
    assert "<table" in content
    assert "x.stl" in content


def test_y5_refine_diff_add_center():
    from core.analyzer.refine_diff import detect_refinement
    V_a = np.array(
        [[0, 0, 0], [1, 0, 0], [0, 1, 0], [0, 0, 1]], dtype=np.float64
    )
    T_a = np.array([[0, 1, 2, 3]], dtype=np.int64)
    V_b = np.vstack([V_a, [[0.25, 0.25, 0.25]]])
    T_b = np.array([
        [0, 1, 2, 4], [0, 1, 3, 4], [0, 2, 3, 4], [1, 2, 3, 4],
    ], dtype=np.int64)
    new_idx, r = detect_refinement(V_a, T_a, V_b, T_b)
    assert r.n_v_new == 1
    assert r.n_t_new == 3
    assert new_idx[0] == 4


def test_y5_refine_diff_no_change():
    from core.analyzer.refine_diff import detect_refinement
    V = np.array([[0, 0, 0], [1, 0, 0], [0, 1, 0], [0, 0, 1]], dtype=np.float64)
    T = np.array([[0, 1, 2, 3]], dtype=np.int64)
    new_idx, r = detect_refinement(V, T, V, T)
    assert r.n_v_new == 0
    assert r.n_t_new == 0


def test_y6_hex_face_area_unit_cube():
    from core.evaluator.hex_face_area import hex_face_area_stats
    pts = np.array([
        [0, 0, 0], [1, 0, 0], [1, 1, 0], [0, 1, 0],
        [0, 0, 1], [1, 0, 1], [1, 1, 1], [0, 1, 1],
    ], dtype=np.float64)
    hexes = np.array([[0, 1, 2, 3, 4, 5, 6, 7]], dtype=np.int64)
    r = hex_face_area_stats(pts, hexes)
    assert abs(r.area_mean - 1.0) < 1e-9
    assert abs(r.ratio_max - 1.0) < 1e-9
    assert r.n_stretched == 0


def test_y6_hex_face_area_stretched():
    from core.evaluator.hex_face_area import hex_face_area_stats
    pts = np.array([
        [0, 0, 0], [1, 0, 0], [1, 1, 0], [0, 1, 0],
        [0, 0, 10], [1, 0, 10], [1, 1, 10], [0, 1, 10],
    ], dtype=np.float64)
    hexes = np.array([[0, 1, 2, 3, 4, 5, 6, 7]], dtype=np.int64)
    r = hex_face_area_stats(pts, hexes)
    assert r.ratio_max > 5.0
    assert r.n_stretched == 1


def test_y6_hex_face_area_empty():
    from core.evaluator.hex_face_area import hex_face_area_stats
    r = hex_face_area_stats(
        np.zeros((0, 3), dtype=np.float64),
        np.zeros((0, 8), dtype=np.int64),
    )
    assert r.n_hexes == 0
