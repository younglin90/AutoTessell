"""V-series (BETA2709-2714) unit tests.

V1: tet_qshape (Klingner-like Q).
V2: orient_check (winding consistency).
V3: hex_jacobian.
V4: feature_norm (z-score).
V5: bench_json_to_csv.
V6: mesh_diff.
"""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pytest


def test_v1_tet_qshape_regular_high():
    from core.evaluator.tet_qshape import tet_qshape
    pts = np.array(
        [[0, 0, 0], [1, 0, 0],
         [0.5, np.sqrt(3) / 2, 0],
         [0.5, np.sqrt(3) / 6, np.sqrt(2 / 3)]],
        dtype=np.float64,
    )
    tets = np.array([[0, 1, 2, 3]], dtype=np.int64)
    Q, r = tet_qshape(pts, tets)
    assert Q[0] > 0.9
    assert r.q_min > 0.9
    assert r.n_below_0p3 == 0


def test_v1_tet_qshape_sliver_zero():
    from core.evaluator.tet_qshape import tet_qshape
    pts = np.array(
        [[0, 0, 0], [1, 0, 0], [0, 1, 0], [0.001, 0.001, 0]],
        dtype=np.float64,
    )
    tets = np.array([[0, 1, 2, 3]], dtype=np.int64)
    Q, r = tet_qshape(pts, tets)
    assert Q[0] < 0.1
    assert r.n_below_0p1 == 1


def test_v1_tet_qshape_empty():
    from core.evaluator.tet_qshape import tet_qshape
    Q, r = tet_qshape(
        np.zeros((0, 3), dtype=np.float64),
        np.zeros((0, 4), dtype=np.int64),
    )
    assert r.n_tets == 0
    assert Q.shape == (0,)


def test_v2_orient_check_cube_consistent():
    from core.analyzer.orient_check import orient_check
    F = np.array([
        [0, 1, 2], [0, 2, 3], [4, 6, 5], [4, 7, 6],
        [0, 4, 5], [0, 5, 1], [2, 6, 7], [2, 7, 3],
        [0, 3, 7], [0, 7, 4], [1, 5, 6], [1, 6, 2],
    ], dtype=np.int64)
    r = orient_check(F)
    assert r.n_inconsistent_edges == 0
    assert r.consistency_ratio == 1.0


def test_v2_orient_check_inconsistent():
    from core.analyzer.orient_check import orient_check
    # both faces have edge (0,1) in forward direction.
    F = np.array([[0, 1, 2], [0, 1, 3]], dtype=np.int64)
    r = orient_check(F)
    assert r.n_inconsistent_edges == 1


def test_v2_orient_check_boundary():
    from core.analyzer.orient_check import orient_check
    F = np.array([[0, 1, 2]], dtype=np.int64)
    r = orient_check(F)
    assert r.n_boundary_edges == 3


def test_v3_hex_jacobian_unit_cube():
    from core.evaluator.hex_jacobian import hex_jacobian_stats
    pts = np.array([
        [0, 0, 0], [1, 0, 0], [1, 1, 0], [0, 1, 0],
        [0, 0, 1], [1, 0, 1], [1, 1, 1], [0, 1, 1],
    ], dtype=np.float64)
    hexes = np.array([[0, 1, 2, 3, 4, 5, 6, 7]], dtype=np.int64)
    r = hex_jacobian_stats(pts, hexes)
    assert r.n_inverted == 0
    assert abs(r.j_min - 1.0) < 1e-9
    assert abs(r.scaled_j_min - 1.0) < 1e-9


def test_v3_hex_jacobian_empty():
    from core.evaluator.hex_jacobian import hex_jacobian_stats
    r = hex_jacobian_stats(
        np.zeros((0, 3), dtype=np.float64),
        np.zeros((0, 8), dtype=np.int64),
    )
    assert r.n_hexes == 0


def test_v4_feature_norm_zscore():
    from core.generator.native_ai.feature_norm import FeatureScaler
    rng = np.random.RandomState(0)
    X = rng.randn(50, 4) * np.array([2, 0.1, 10, 1]) + np.array([1, -2, 5, 0])
    sc = FeatureScaler.fit(X)
    Xn = sc.transform(X)
    assert np.allclose(Xn.mean(axis=0), 0, atol=1e-9)
    assert np.allclose(Xn.std(axis=0), 1, atol=1e-9)


def test_v4_feature_norm_save_load(tmp_path):
    from core.generator.native_ai.feature_norm import FeatureScaler
    X = np.random.RandomState(1).randn(20, 3)
    sc = FeatureScaler.fit(X)
    p = tmp_path / "scaler.json"
    sc.save(p)
    sc2 = FeatureScaler.load(p)
    assert sc2.n_features == 3
    Xn = sc2.transform(X)
    assert np.allclose(Xn.mean(axis=0), 0, atol=1e-9)


def test_v4_feature_norm_zero_std_safe():
    """constant column → std<eps → 1.0 substitute, no NaN."""
    from core.generator.native_ai.feature_norm import FeatureScaler
    X = np.array([[1.0, 5.0], [1.0, 6.0], [1.0, 7.0]])
    sc = FeatureScaler.fit(X)
    Xn = sc.transform(X)
    assert not np.any(np.isnan(Xn))


def test_v5_bench_json_to_csv(tmp_path):
    from scripts.bench_json_to_csv import collect_rows
    p = tmp_path / "x.json"
    p.write_text(json.dumps([
        {"engine": "a", "elapsed": 1.0},
        {"engine": "b", "elapsed": 2.0},
    ]))
    rows = collect_rows([p])
    assert len(rows) == 2
    assert rows[0]["_source_file"] == "x.json"


def test_v6_mesh_diff_identical():
    from core.utils.mesh_diff import mesh_diff
    V = np.array([[0, 0, 0], [1, 0, 0], [0, 1, 0], [0, 0, 1]], dtype=np.float64)
    T = np.array([[0, 1, 2, 3]], dtype=np.int64)
    r = mesh_diff(V, T, V, T)
    assert r.delta_vertices == 0
    assert r.delta_cells == 0
    assert r.total_volume_delta < 1e-9


def test_v6_mesh_diff_scaled():
    from core.utils.mesh_diff import mesh_diff
    V = np.array([[0, 0, 0], [1, 0, 0], [0, 1, 0], [0, 0, 1]], dtype=np.float64)
    T = np.array([[0, 1, 2, 3]], dtype=np.int64)
    r = mesh_diff(V, T, V * 2, T)
    assert r.total_volume_delta > 0.5
