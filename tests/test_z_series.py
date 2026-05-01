"""Z-series (BETA2737-2742) unit tests."""
from __future__ import annotations

import numpy as np
import pytest


def test_z1_swap_candidates_basic():
    from core.analyzer.swap_candidates import screen_swap_candidates
    pts = np.array(
        [[0, 0, 0], [1, 0, 0], [0, 1, 0], [0.5, 0.5, 1], [0.5, 0.5, -1]],
        dtype=np.float64,
    )
    tets = np.array([[0, 1, 2, 3], [0, 1, 2, 4]], dtype=np.int64)
    edges, q, r = screen_swap_candidates(pts, tets, q_threshold=1.0)
    assert r.n_internal_edges >= 1


def test_z1_swap_candidates_empty():
    from core.analyzer.swap_candidates import screen_swap_candidates
    edges, q, r = screen_swap_candidates(
        np.zeros((0, 3), dtype=np.float64),
        np.zeros((0, 4), dtype=np.int64),
    )
    assert r.n_internal_edges == 0


def test_z2_manifold_check_cube():
    from core.analyzer.manifold_check import check_manifold
    F = np.array([
        [0, 2, 1], [0, 3, 2], [4, 5, 6], [4, 6, 7],
        [0, 1, 5], [0, 5, 4], [2, 3, 7], [2, 7, 6],
        [1, 2, 6], [1, 6, 5], [3, 0, 4], [3, 4, 7],
    ], dtype=np.int64)
    r = check_manifold(F, n_vertices=8)
    assert r.is_edge_manifold
    assert r.is_vertex_manifold
    assert r.n_boundary_edges == 0


def test_z2_manifold_check_nonmanifold():
    from core.analyzer.manifold_check import check_manifold
    F = np.array([[0, 1, 2], [0, 1, 3], [0, 1, 4]], dtype=np.int64)
    r = check_manifold(F)
    assert not r.is_edge_manifold
    assert r.n_nonmanifold_edges == 1
    assert r.n_nonmanifold_vertices >= 1


def test_z2_manifold_check_open():
    from core.analyzer.manifold_check import check_manifold
    F = np.array([[0, 1, 2]], dtype=np.int64)
    r = check_manifold(F)
    assert r.is_edge_manifold
    assert r.n_boundary_edges == 3


def test_z3_model_version_parse():
    from core.generator.native_ai.model_version import ModelVersion
    v = ModelVersion.parse("1.2.3")
    assert v.major == 1
    assert v.minor == 2
    assert v.patch == 3
    assert str(v) == "1.2.3"


def test_z3_model_version_compat():
    from core.generator.native_ai.model_version import ModelVersion
    a = ModelVersion(1, 0, 0)
    b = ModelVersion(1, 5, 2)
    c = ModelVersion(2, 0, 0)
    assert a.is_compatible_with(b)
    assert not a.is_compatible_with(c)
    assert b.is_newer_than(a)


def test_z3_model_version_stamp(tmp_path):
    pytest.importorskip("torch")
    import torch
    from core.generator.native_ai.model_version import (
        stamp_version, check_model_version, ModelVersion,
    )
    p = tmp_path / "m.pt"
    ckpt = stamp_version({"model_state_dict": {}}, ModelVersion(1, 5, 0))
    torch.save(ckpt, p)
    v, ok, msg = check_model_version(p)
    assert ok
    assert v.major == 1
    assert v.minor == 5


def test_z4_bench_timing_breakdown_runs(tmp_path):
    """smoke: script runs without error on a sample input."""
    import json
    import subprocess
    import sys

    p = tmp_path / "bench.json"
    p.write_text(json.dumps([
        {"engine": "x", "elapsed": 1.0, "generator_s": 0.5},
    ]))
    res = subprocess.run(
        [sys.executable, "scripts/bench_timing_breakdown.py", str(p)],
        capture_output=True, text=True, timeout=20,
    )
    assert res.returncode == 0
    assert "generator_s" in res.stdout


def test_z5_octant_assign_8_corners():
    from core.utils.octant_split import octant_assign
    V = np.array([
        [0, 0, 0], [1, 0, 0], [0, 1, 0], [1, 1, 0],
        [0, 0, 1], [1, 0, 1], [0, 1, 1], [1, 1, 1],
    ], dtype=np.float64)
    oct_, r = octant_assign(V)
    assert r.n_points == 8
    # 8 distinct octants.
    assert len(set(oct_.tolist())) == 8
    assert all(c == 1 for c in r.counts)


def test_z5_octant_assign_empty():
    from core.utils.octant_split import octant_assign
    oct_, r = octant_assign(np.zeros((0, 3), dtype=np.float64))
    assert r.n_points == 0


def test_z6_hex_stretch_unit_cube():
    from core.evaluator.hex_stretch import hex_stretch_stats
    pts = np.array([
        [0, 0, 0], [1, 0, 0], [1, 1, 0], [0, 1, 0],
        [0, 0, 1], [1, 0, 1], [1, 1, 1], [0, 1, 1],
    ], dtype=np.float64)
    hexes = np.array([[0, 1, 2, 3, 4, 5, 6, 7]], dtype=np.int64)
    r = hex_stretch_stats(pts, hexes)
    assert abs(r.stretch_mean - 1.0) < 1e-9
    assert r.n_below_0p1 == 0


def test_z6_hex_stretch_thin():
    from core.evaluator.hex_stretch import hex_stretch_stats
    pts = np.array([
        [0, 0, 0], [0.01, 0, 0], [0.01, 1, 0], [0, 1, 0],
        [0, 0, 1], [0.01, 0, 1], [0.01, 1, 1], [0, 1, 1],
    ], dtype=np.float64)
    hexes = np.array([[0, 1, 2, 3, 4, 5, 6, 7]], dtype=np.int64)
    r = hex_stretch_stats(pts, hexes)
    assert r.stretch_mean < 0.1
    assert r.n_below_0p1 == 1


def test_z6_hex_stretch_empty():
    from core.evaluator.hex_stretch import hex_stretch_stats
    r = hex_stretch_stats(
        np.zeros((0, 3), dtype=np.float64),
        np.zeros((0, 8), dtype=np.int64),
    )
    assert r.n_hexes == 0
