"""U-series (BETA2702-2707) unit tests.

U1: tet_edge_stats.
U3: feature_report.
U4: inference_warmup.
U5: validate_bench_json.
U6: degenerate_detector.
"""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pytest


def _unit_cube_mesh():
    V = np.array([
        [0, 0, 0], [1, 0, 0], [1, 1, 0], [0, 1, 0],
        [0, 0, 1], [1, 0, 1], [1, 1, 1], [0, 1, 1],
    ], dtype=np.float64)
    F = np.array([
        [0, 1, 2], [0, 2, 3], [4, 6, 5], [4, 7, 6],
        [0, 4, 5], [0, 5, 1], [2, 6, 7], [2, 7, 3],
        [0, 3, 7], [0, 7, 4], [1, 5, 6], [1, 6, 2],
    ], dtype=np.int64)
    return V, F


def _regular_tet_mesh():
    pts = np.array([[0, 0, 0], [1, 0, 0], [0, 1, 0], [0, 0, 1]], dtype=np.float64)
    tets = np.array([[0, 1, 2, 3]], dtype=np.int64)
    return pts, tets


def test_u1_tet_edge_stats_unit():
    from core.analyzer.tet_edge_stats import tet_edge_stats
    pts, tets = _regular_tet_mesh()
    r = tet_edge_stats(pts, tets)
    assert r.n_tets == 1
    assert abs(r.edge_min - 1.0) < 1e-9
    assert abs(r.edge_max - np.sqrt(2)) < 1e-9
    assert r.n_sliver == 0


def test_u1_tet_edge_stats_sliver():
    """very thin tet → high aniso ratio."""
    from core.analyzer.tet_edge_stats import tet_edge_stats
    pts = np.array(
        [[0, 0, 0], [1, 0, 0], [0, 1, 0], [0, 0, 0.001]], dtype=np.float64
    )
    tets = np.array([[0, 1, 2, 3]], dtype=np.int64)
    r = tet_edge_stats(pts, tets, sliver_aniso=10.0)
    assert r.aniso_max > 100.0
    assert r.n_sliver == 1


def test_u1_tet_edge_stats_empty():
    from core.analyzer.tet_edge_stats import tet_edge_stats
    r = tet_edge_stats(
        np.zeros((0, 3), dtype=np.float64),
        np.zeros((0, 4), dtype=np.int64),
    )
    assert r.n_tets == 0


def test_u3_feature_report_cube():
    from core.analyzer.feature_report import feature_report
    V, F = _unit_cube_mesh()
    r = feature_report(V, F, sharp_angle_deg=30.0)
    assert r.n_vertices == 8
    assert r.n_triangles == 12
    assert r.n_sharp_edges > 0  # cube has sharp edges
    assert 0.0 <= r.complexity_score <= 1.0


def test_u3_feature_report_empty():
    from core.analyzer.feature_report import feature_report
    r = feature_report(
        np.zeros((0, 3), dtype=np.float64),
        np.zeros((0, 3), dtype=np.int64),
    )
    assert r.n_vertices == 0
    assert r.n_triangles == 0


def test_u4_warmup_model_basic():
    pytest.importorskip("torch")
    import torch
    from core.generator.native_ai.inference_warmup import warmup_model

    class Net(torch.nn.Module):
        def __init__(self):
            super().__init__()
            self.fc = torch.nn.Linear(8, 1)

        def forward(self, x):
            return self.fc(x)

    r = warmup_model(Net(), input_dim=8, n_iter=2, batch=3)
    assert r["warm_iters"] == 2
    assert r["dummy_out_shape"] == (3, 1)


def test_u4_cache_clear():
    from core.generator.native_ai.inference_warmup import (
        cache_clear,
        cache_size,
    )
    cache_clear()
    assert cache_size() == 0


def test_u5_validate_bench_json_clean(tmp_path):
    from scripts.validate_bench_json import validate_file

    p = tmp_path / "ok.json"
    p.write_text(json.dumps([
        {"engine": "x", "elapsed": 1.0, "success": True, "grade": "A"},
        {"engine": "y", "elapsed": 2.5, "success": False, "grade": "D"},
    ]))
    n_rows, n_err, _ = validate_file(p)
    assert n_rows == 2
    assert n_err == 0


def test_u5_validate_bench_json_errors(tmp_path):
    from scripts.validate_bench_json import validate_file

    p = tmp_path / "bad.json"
    p.write_text(json.dumps([
        {"engine": 123, "elapsed": -1.0, "grade": "ZZ"},
    ]))
    n_rows, n_err, errs = validate_file(p)
    assert n_rows == 1
    assert n_err >= 3  # type, range, range


def test_u5_validate_bench_json_parse_error(tmp_path):
    from scripts.validate_bench_json import validate_file

    p = tmp_path / "broken.json"
    p.write_text("{ not valid json")
    n_rows, n_err, errs = validate_file(p)
    assert n_err == 1


def test_u6_degenerate_detector_regular():
    from core.evaluator.degenerate_detector import detect_degenerate_tets
    pts, tets = _regular_tet_mesh()
    r = detect_degenerate_tets(pts, tets)
    assert r.n_tets == 1
    assert r.n_inverted == 0
    assert r.n_zero_vol == 0
    assert r.n_ok == 1


def test_u6_degenerate_detector_inverted():
    from core.evaluator.degenerate_detector import detect_degenerate_tets
    pts = np.array([[0, 0, 0], [1, 0, 0], [0, 1, 0], [0, 0, 1]], dtype=np.float64)
    # swap two indices to invert.
    tets = np.array([[0, 1, 3, 2]], dtype=np.int64)
    r = detect_degenerate_tets(pts, tets)
    assert r.n_inverted == 1


def test_u6_degenerate_detector_empty():
    from core.evaluator.degenerate_detector import detect_degenerate_tets
    r = detect_degenerate_tets(
        np.zeros((0, 3), dtype=np.float64),
        np.zeros((0, 4), dtype=np.int64),
    )
    assert r.n_tets == 0
