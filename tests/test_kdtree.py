"""NumpyKDTree 회귀 테스트 (v0.4.0-beta28) — scipy parity."""
from __future__ import annotations

import numpy as np
import pytest

from core.utils.kdtree import NumpyKDTree


try:
    from scipy.spatial import cKDTree as _cKDTree  # type: ignore
    _HAS_SCIPY = True
except Exception:  # pragma: no cover
    _HAS_SCIPY = False


def test_empty_points_returns_inf() -> None:
    """빈 reference set 은 dist=inf, idx=0 반환."""
    tree = NumpyKDTree(np.zeros((0, 3)))
    q = np.array([[1.0, 2.0, 3.0]])
    dists, idx = tree.query(q, k=1)
    assert np.isinf(dists[0])


def test_single_query_k1_returns_scalar_like() -> None:
    """1D query + k=1 → scalar 형태 반환."""
    P = np.array([[0, 0, 0], [1, 0, 0], [0, 1, 0]], dtype=np.float64)
    tree = NumpyKDTree(P)
    q = np.array([0.6, 0.0, 0.0])  # (1,0,0) 이 가장 가까움 (거리 0.4)
    dists, idx = tree.query(q, k=1)
    # scalar
    assert np.isscalar(dists) or np.ndim(dists) == 0
    assert int(idx) == 1


def test_brute_force_small_set_matches_manual() -> None:
    """소형 reference set 의 brute-force 경로 결과 검증."""
    P = np.array([[0, 0, 0], [1, 0, 0], [0, 1, 0], [0, 0, 1]], dtype=np.float64)
    tree = NumpyKDTree(P)
    q = np.array([[0.1, 0.0, 0.0], [0.0, 0.9, 0.0]])
    dists, idx = tree.query(q, k=1)
    np.testing.assert_array_equal(idx, [0, 2])
    np.testing.assert_allclose(dists, [0.1, 0.1], atol=1e-12)


def test_k_greater_than_one_brute() -> None:
    """k=2 반환값이 올바른 순서 + 거리."""
    P = np.array([[0, 0, 0], [1, 0, 0], [2, 0, 0], [3, 0, 0]], dtype=np.float64)
    tree = NumpyKDTree(P)
    q = np.array([[0.4, 0.0, 0.0]])
    dists, idx = tree.query(q, k=2)
    assert idx.shape == (1, 2)
    # 가장 가까운 2 개: idx 0 (dist 0.4), idx 1 (dist 0.6)
    np.testing.assert_array_equal(idx[0], [0, 1])
    np.testing.assert_allclose(dists[0], [0.4, 0.6], atol=1e-12)


def test_distance_upper_bound_filters() -> None:
    """ub 를 넘는 점은 dist=inf, idx=n."""
    P = np.array([[0, 0, 0], [5, 0, 0]], dtype=np.float64)
    tree = NumpyKDTree(P)
    q = np.array([[10.0, 0.0, 0.0]])
    dists, idx = tree.query(q, k=1, distance_upper_bound=3.0)
    assert np.isinf(dists[0])
    assert int(idx[0]) == 2  # n=2


@pytest.mark.skipif(not _HAS_SCIPY, reason="scipy not available")
def test_parity_with_scipy_small() -> None:
    """소형 (N=500) 에서 scipy.cKDTree 와 k=3 결과가 인덱스/거리 일치."""
    rng = np.random.default_rng(42)
    P = rng.uniform(-1, 1, (500, 3))
    Q = rng.uniform(-1, 1, (50, 3))
    np_tree = NumpyKDTree(P)
    sp_tree = _cKDTree(P)
    np_d, np_i = np_tree.query(Q, k=3)
    sp_d, sp_i = sp_tree.query(Q, k=3)
    np.testing.assert_allclose(np_d, sp_d, atol=1e-9)
    np.testing.assert_array_equal(np_i, sp_i)


@pytest.mark.skipif(not _HAS_SCIPY, reason="scipy not available")
def test_parity_with_scipy_large_grid_path() -> None:
    """대형 (N=3000, grid bucket 경로) 에서 scipy.cKDTree 와 k=1 결과 일치."""
    rng = np.random.default_rng(7)
    P = rng.uniform(-1, 1, (3000, 3))
    Q = rng.uniform(-1, 1, (200, 3))
    np_tree = NumpyKDTree(P)
    sp_tree = _cKDTree(P)
    np_d, np_i = np_tree.query(Q, k=1)
    sp_d, sp_i = sp_tree.query(Q, k=1)
    # 거리는 정확히 일치
    np.testing.assert_allclose(np_d, sp_d, atol=1e-9)
    # 인덱스도 (동거리 tie 는 드물므로 대부분 일치 — 100% 요구)
    np.testing.assert_array_equal(np_i, sp_i)


@pytest.mark.skipif(not _HAS_SCIPY, reason="scipy not available")
def test_parity_with_scipy_distance_upper_bound() -> None:
    """distance_upper_bound 동작이 scipy 와 일치."""
    rng = np.random.default_rng(11)
    P = rng.uniform(-0.5, 0.5, (200, 3))
    Q = np.array([[2.0, 0.0, 0.0], [0.0, 0.0, 0.0]])
    ub = 0.3
    np_tree = NumpyKDTree(P)
    sp_tree = _cKDTree(P)
    np_d, np_i = np_tree.query(Q, k=1, distance_upper_bound=ub)
    sp_d, sp_i = sp_tree.query(Q, k=1, distance_upper_bound=ub)
    # scipy 는 dist=inf 일 때 idx=n (=len(P)). NumpyKDTree 도 동일.
    np.testing.assert_array_equal(np.isinf(np_d), np.isinf(sp_d))
    # 유효 query 만 비교
    valid = ~np.isinf(np_d)
    np.testing.assert_allclose(np_d[valid], sp_d[valid], atol=1e-9)
