"""WILDMESH-LOOP regression tests (BETA2815)."""
from __future__ import annotations

import numpy as np
import pytest


def _gen_random_tet_mesh(n_pts: int = 80, seed: int = 42):
    """scipy Delaunay 로 random tet mesh."""
    pytest.importorskip("scipy")
    from scipy.spatial import Delaunay
    rng = np.random.RandomState(seed)
    pts = rng.rand(n_pts, 3).astype(np.float64)
    d = Delaunay(pts)
    return pts, d.simplices.astype(np.int64)


def test_wildmesh_inv_q_regular():
    """regular tet → inv_q ≈ 1."""
    from core.generator.native_tet.wildmesh_loop import _wildmesh_inv_q
    pts = np.array([
        [0, 0, 0], [1, 0, 0],
        [0.5, np.sqrt(3) / 2, 0],
        [0.5, np.sqrt(3) / 6, np.sqrt(2 / 3)],
    ], dtype=np.float64)
    tets = np.array([[0, 1, 2, 3]], dtype=np.int64)
    inv_q = _wildmesh_inv_q(pts, tets)
    # regular tet edge=1: sum_L=6, V=√2/12, (3V)^(2/3) = (√2/4)^(2/3) ≈ 0.515.
    # inv_q = 6 / (12 × 0.515) ≈ 0.97.
    assert 0.9 < float(inv_q[0]) < 1.1


def test_wildmesh_inv_q_sliver():
    """sliver tet → inv_q → ∞."""
    from core.generator.native_tet.wildmesh_loop import _wildmesh_inv_q
    pts = np.array(
        [[0, 0, 0], [1, 0, 0], [0, 1, 0], [0.001, 0.001, 0]], dtype=np.float64,
    )
    tets = np.array([[0, 1, 2, 3]], dtype=np.int64)
    inv_q = _wildmesh_inv_q(pts, tets)
    assert float(inv_q[0]) > 1000   # very high inv_q.


def test_wildmesh_inv_q_inverted():
    """inverted tet → inv_q = 1e6."""
    from core.generator.native_tet.wildmesh_loop import _wildmesh_inv_q
    pts = np.array(
        [[0, 0, 0], [1, 0, 0], [0, 1, 0], [0, 0, 1]], dtype=np.float64,
    )
    tets = np.array([[0, 1, 3, 2]], dtype=np.int64)  # swap → inverted.
    inv_q = _wildmesh_inv_q(pts, tets)
    assert float(inv_q[0]) >= 1e6 - 1


def test_wildmesh_loop_too_small():
    from core.generator.native_tet.wildmesh_loop import wildmesh_improvement_loop
    pts = np.array(
        [[0, 0, 0], [1, 0, 0], [0, 1, 0], [0, 0, 1]], dtype=np.float64,
    )
    tets = np.array([[0, 1, 2, 3]], dtype=np.int64)
    new_pts, new_tets, r = wildmesh_improvement_loop(pts, tets, max_its=2)
    assert r.early_exit_reason == "too_small"
    assert new_tets.shape == tets.shape


def test_wildmesh_loop_stage_zero_noop():
    """stage=0 → 입력 그대로 반환."""
    from core.generator.native_tet.wildmesh_loop import wildmesh_improvement_loop
    pts, tets = _gen_random_tet_mesh(n_pts=80)
    if tets.shape[0] < 50:
        pytest.skip("not enough tets")
    new_pts, new_tets, r = wildmesh_improvement_loop(
        pts, tets, stage=0, max_its=5,
    )
    assert r.early_exit_reason == "no_op"
    assert new_tets.shape == tets.shape


def test_wildmesh_loop_real_mesh_monotone():
    """실 mesh: 회전 후 monotone guard 통과."""
    from core.generator.native_tet.wildmesh_loop import wildmesh_improvement_loop
    pts, tets = _gen_random_tet_mesh(n_pts=80, seed=1)
    if tets.shape[0] < 50:
        pytest.skip("not enough tets")
    new_pts, new_tets, r = wildmesh_improvement_loop(
        pts, tets, stop_quality=10.0, max_its=5,
        edge_length_r=0.1, stage=2,
    )
    # monotone: post_mean_q ≥ pre_mean_q (or 원본 복귀).
    assert r.post_mean_q >= r.pre_mean_q - 1e-6
    assert r.post_min_q >= r.pre_min_q - 0.030


def test_wildmesh_loop_stop_quality_progression():
    """stop_quality=5 (loose) → 빨리 converge / stop_quality=2 (strict) → 더 많이 반복."""
    from core.generator.native_tet.wildmesh_loop import wildmesh_improvement_loop
    pts, tets = _gen_random_tet_mesh(n_pts=100, seed=2)
    if tets.shape[0] < 50:
        pytest.skip("not enough tets")

    _, _, r_loose = wildmesh_improvement_loop(
        pts, tets, stop_quality=100.0, max_its=2,
    )
    _, _, r_strict = wildmesh_improvement_loop(
        pts, tets, stop_quality=1.0, max_its=2,
    )
    # loose 는 즉시 stop_quality_reached 가능 / strict 는 max_its 도달.
    assert r_loose.n_iters_used <= r_strict.n_iters_used + 1


def test_wildmesh_parity_with_pytetwild():
    """pytetwild (libccmio fTetWild Python wrapper) 와 결과 비교."""
    pytest.importorskip("scipy")
    pt = pytest.importorskip("pytetwild")
    from core.generator.native_tet.wildmesh_loop import parity_check_with_wildmeshing

    # unit cube surface (12 tris).
    V = np.array([
        [0, 0, 0], [1, 0, 0], [1, 1, 0], [0, 1, 0],
        [0, 0, 1], [1, 0, 1], [1, 1, 1], [0, 1, 1],
    ], dtype=np.float64)
    F = np.array([
        [0, 2, 1], [0, 3, 2], [4, 5, 6], [4, 6, 7],
        [0, 1, 5], [0, 5, 4], [2, 3, 7], [2, 7, 6],
        [1, 2, 6], [1, 6, 5], [3, 0, 4], [3, 4, 7],
    ], dtype=np.int64)
    # cube vertices 만으로는 Delaunay 구성 불충분 → interior 추가.
    rng = np.random.RandomState(0)
    interior = rng.rand(20, 3).astype(np.float64) * 0.8 + 0.1
    pts = np.vstack([V, interior])

    res = parity_check_with_wildmeshing(
        pts, F,
        stop_quality=10.0, edge_length_r=0.1, epsilon=0.005, max_its=20,
    )
    assert "ours" in res and "lib" in res
    # lib 가 unavailable 이면 skip (CI 환경).
    if res["lib"].get("error"):
        pytest.skip(f"pytetwild error: {res['lib']['error']}")
    # 구조 검사: ours / lib 둘 다 mesh 생성.
    assert res["ours"].get("n_tets", 0) > 0
    assert res["lib"].get("n_tets", 0) > 0
    # mean_q 절대 차이 < 0.5 (수치적으로 다른 path 라 정확 일치는 안 됨).
    assert "match" in res
    assert res["match"]["mean_q_diff"] < 0.5
