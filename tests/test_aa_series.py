"""AA-series (BETA2744-2749) unit tests."""
from __future__ import annotations

import numpy as np


def test_aa1_sliver_collapse_thin():
    from core.analyzer.sliver_collapse import detect_sliver_collapse_edges
    pts = np.array(
        [[0, 0, 0], [1, 0, 0], [0, 1, 0], [0.001, 0.001, 0]],
        dtype=np.float64,
    )
    tets = np.array([[0, 1, 2, 3]], dtype=np.int64)
    edges, r = detect_sliver_collapse_edges(pts, tets)
    assert r.n_sliver_tets == 1
    assert r.n_collapse_candidates == 1


def test_aa1_sliver_collapse_no_sliver():
    from core.analyzer.sliver_collapse import detect_sliver_collapse_edges
    pts = np.array(
        [[0, 0, 0], [1, 0, 0],
         [0.5, np.sqrt(3) / 2, 0],
         [0.5, np.sqrt(3) / 6, np.sqrt(2 / 3)]],
        dtype=np.float64,
    )
    tets = np.array([[0, 1, 2, 3]], dtype=np.int64)
    edges, r = detect_sliver_collapse_edges(pts, tets)
    assert r.n_sliver_tets == 0


def test_aa1_sliver_collapse_empty():
    from core.analyzer.sliver_collapse import detect_sliver_collapse_edges
    edges, r = detect_sliver_collapse_edges(
        np.zeros((0, 3), dtype=np.float64),
        np.zeros((0, 4), dtype=np.int64),
    )
    assert r.n_sliver_tets == 0


def test_aa2_dihedral_hist_cube():
    from core.analyzer.dihedral_hist import dihedral_histogram
    V = np.array([
        [0, 0, 0], [1, 0, 0], [1, 1, 0], [0, 1, 0],
        [0, 0, 1], [1, 0, 1], [1, 1, 1], [0, 1, 1],
    ], dtype=np.float64)
    F = np.array([
        [0, 2, 1], [0, 3, 2], [4, 5, 6], [4, 6, 7],
        [0, 1, 5], [0, 5, 4], [2, 3, 7], [2, 7, 6],
        [1, 2, 6], [1, 6, 5], [3, 0, 4], [3, 4, 7],
    ], dtype=np.int64)
    r = dihedral_histogram(V, F)
    assert r.n_edges > 0
    assert r.angle_min_deg <= r.angle_mean_deg <= r.angle_max_deg
    assert sum(r.counts) == r.n_edges


def test_aa2_dihedral_hist_empty():
    from core.analyzer.dihedral_hist import dihedral_histogram
    r = dihedral_histogram(
        np.zeros((0, 3), dtype=np.float64),
        np.zeros((0, 3), dtype=np.int64),
    )
    assert r.n_edges == 0


def test_aa3_ensemble_equal_weights():
    from core.generator.native_ai.ensemble import ensemble_predictions
    preds = [
        np.array([[1.0]]), np.array([[2.0]]), np.array([[3.0]]),
    ]
    r = ensemble_predictions(preds)
    assert r.n_models == 3
    assert abs(r.mean[0, 0] - 2.0) < 1e-9


def test_aa3_ensemble_val_loss_weighted():
    from core.generator.native_ai.ensemble import ensemble_predictions
    preds = [np.array([[1.0]]), np.array([[2.0]])]
    r = ensemble_predictions(preds, val_losses=[0.01, 1.0])
    # model 0 has much lower val_loss → much higher weight.
    assert r.weights[0] > 0.9


def test_aa3_ensemble_shape_mismatch():
    from core.generator.native_ai.ensemble import ensemble_predictions
    import pytest
    with pytest.raises(ValueError):
        ensemble_predictions([np.zeros((3, 1)), np.zeros((4, 1))])


def test_aa4_bench_diff_csv_runs(tmp_path):
    import json
    import subprocess
    import sys
    a = tmp_path / "a.json"
    b = tmp_path / "b.json"
    a.write_text(json.dumps([{"engine": "x", "stl": "s.stl", "grade": "A"}]))
    b.write_text(json.dumps([{"engine": "x", "stl": "s.stl", "grade": "B"}]))
    out = tmp_path / "diff.csv"
    res = subprocess.run(
        [sys.executable, "scripts/bench_diff_csv.py",
         str(a), str(b), "-o", str(out)],
        capture_output=True, text=True, timeout=20,
    )
    assert res.returncode == 0
    assert out.exists()
    content = out.read_text()
    assert "grade_delta" in content


def test_aa5_flip_candidates_pair():
    from core.analyzer.flip_candidates import screen_flip_candidates
    pts = np.array(
        [[0, 0, 0], [1, 0, 0], [0, 1, 0], [0, 0, 1], [1, 1, 1]],
        dtype=np.float64,
    )
    tets = np.array([[0, 1, 2, 3], [1, 2, 3, 4]], dtype=np.int64)
    pairs, q, r = screen_flip_candidates(pts, tets, q_threshold=2.0)
    assert r.n_internal_faces == 1


def test_aa5_flip_candidates_empty():
    from core.analyzer.flip_candidates import screen_flip_candidates
    pairs, q, r = screen_flip_candidates(
        np.zeros((0, 3), dtype=np.float64),
        np.zeros((0, 4), dtype=np.int64),
    )
    assert r.n_internal_faces == 0


def test_aa6_hex_ortho_unit_cube():
    from core.evaluator.hex_ortho import hex_ortho_stats
    pts = np.array([
        [0, 0, 0], [1, 0, 0], [1, 1, 0], [0, 1, 0],
        [0, 0, 1], [1, 0, 1], [1, 1, 1], [0, 1, 1],
    ], dtype=np.float64)
    hexes = np.array([[0, 1, 2, 3, 4, 5, 6, 7]], dtype=np.int64)
    r = hex_ortho_stats(pts, hexes)
    assert r.ortho_max_deg < 1.0
    assert r.n_above_30deg == 0


def test_aa6_hex_ortho_skewed():
    from core.evaluator.hex_ortho import hex_ortho_stats
    pts = np.array([
        [0, 0, 0], [1, 0, 0], [1, 1, 0], [0, 1, 0],
        [0, 0, 1], [1, 0, 1], [1.5, 1.5, 0.5], [0, 1, 1],
    ], dtype=np.float64)
    hexes = np.array([[0, 1, 2, 3, 4, 5, 6, 7]], dtype=np.int64)
    r = hex_ortho_stats(pts, hexes)
    assert r.ortho_max_deg > 5.0


def test_aa6_hex_ortho_empty():
    from core.evaluator.hex_ortho import hex_ortho_stats
    r = hex_ortho_stats(
        np.zeros((0, 3), dtype=np.float64),
        np.zeros((0, 8), dtype=np.int64),
    )
    assert r.n_hexes == 0
