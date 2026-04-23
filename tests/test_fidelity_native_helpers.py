"""beta36 — fidelity native helpers (_native_sample_surface / _native_kdist_chunked).

beta11 에서 trimesh.sample + scipy.cKDTree 대체로 추가됐으나 dedicated 단위
테스트 부재. Hausdorff 통합 경로에서만 cover 되었음.
"""
from __future__ import annotations

import numpy as np
import pytest

from core.evaluator.fidelity import (
    _native_kdist_chunked,
    _native_sample_surface,
)


def _unit_square_mesh():
    """단위 사각형 (x-y 평면, z=0) — 2 삼각형."""
    V = np.array([
        [0, 0, 0], [1, 0, 0], [1, 1, 0], [0, 1, 0],
    ], dtype=np.float64)
    F = np.array([[0, 1, 2], [0, 2, 3]], dtype=np.int64)
    return V, F


# ---------------------------------------------------------------------------
# _native_sample_surface
# ---------------------------------------------------------------------------


def test_sample_surface_empty_mesh_returns_empty() -> None:
    """빈 mesh → 빈 샘플 array."""
    V = np.zeros((0, 3))
    F = np.zeros((0, 3), dtype=np.int64)
    out = _native_sample_surface(V, F, n_samples=100)
    assert out.shape == (0, 3)


def test_sample_surface_zero_samples_returns_empty() -> None:
    V, F = _unit_square_mesh()
    out = _native_sample_surface(V, F, n_samples=0)
    assert out.shape == (0, 3)


def test_sample_surface_negative_samples_returns_empty() -> None:
    V, F = _unit_square_mesh()
    out = _native_sample_surface(V, F, n_samples=-5)
    assert out.shape == (0, 3)


def test_sample_surface_points_lie_on_surface() -> None:
    """단위 사각형 (z=0) 에서 샘플된 모든 점은 z≈0."""
    V, F = _unit_square_mesh()
    samples = _native_sample_surface(V, F, n_samples=2000)
    assert samples.shape == (2000, 3)
    np.testing.assert_allclose(samples[:, 2], 0.0, atol=1e-10)
    # x, y ∈ [0, 1]
    assert (samples[:, 0] >= 0).all()
    assert (samples[:, 0] <= 1).all()
    assert (samples[:, 1] >= 0).all()
    assert (samples[:, 1] <= 1).all()


def test_sample_surface_deterministic_seed() -> None:
    """같은 seed 는 같은 샘플 반환."""
    V, F = _unit_square_mesh()
    s1 = _native_sample_surface(V, F, n_samples=500, seed=42)
    s2 = _native_sample_surface(V, F, n_samples=500, seed=42)
    np.testing.assert_array_equal(s1, s2)


def test_sample_surface_different_seeds_differ() -> None:
    V, F = _unit_square_mesh()
    s1 = _native_sample_surface(V, F, n_samples=500, seed=0)
    s2 = _native_sample_surface(V, F, n_samples=500, seed=1)
    assert not np.array_equal(s1, s2)


def test_sample_surface_area_weighted_distribution() -> None:
    """두 삼각형의 면적이 10:1 이면 샘플도 대략 10:1 로 분포."""
    # triangle A (큰) + triangle B (작은)
    V = np.array([
        [0, 0, 0], [10, 0, 0], [0, 10, 0],   # big: area=50
        [100, 100, 0], [101, 100, 0], [100, 101, 0],  # small: area=0.5
    ], dtype=np.float64)
    F = np.array([[0, 1, 2], [3, 4, 5]], dtype=np.int64)
    samples = _native_sample_surface(V, F, n_samples=10000, seed=0)
    # 큰 삼각형 영역 ( x≤10 , y≤10 ) 에 속하는 비율
    in_big = (samples[:, 0] <= 10.0) & (samples[:, 1] <= 10.0)
    ratio = in_big.sum() / len(samples)
    # 50/(50+0.5) ≈ 0.9901
    assert 0.97 < ratio < 1.0


def test_sample_surface_degenerate_zero_area_returns_empty() -> None:
    """모든 삼각형 면적 0 (collinear) → 빈 샘플."""
    V = np.array([[0, 0, 0], [1, 0, 0], [2, 0, 0]], dtype=np.float64)
    F = np.array([[0, 1, 2]], dtype=np.int64)
    out = _native_sample_surface(V, F, n_samples=100)
    assert out.shape == (0, 3)


# ---------------------------------------------------------------------------
# _native_kdist_chunked
# ---------------------------------------------------------------------------


def test_kdist_identical_sets_is_zero() -> None:
    """동일 set 에서 최근접 거리 max = 0."""
    P = np.random.default_rng(7).uniform(-1, 1, (100, 3))
    d = _native_kdist_chunked(P, P)
    assert d == pytest.approx(0.0)


def test_kdist_empty_returns_zero() -> None:
    assert _native_kdist_chunked(np.zeros((0, 3)), np.ones((10, 3))) == 0.0
    assert _native_kdist_chunked(np.ones((10, 3)), np.zeros((0, 3))) == 0.0


def test_kdist_symmetric_on_small_sets() -> None:
    """A→B vs B→A 의 max min distance 는 일반적으로 서로 다르지만 shift-only
    설정에서는 값이 유사."""
    rng = np.random.default_rng(11)
    A = rng.uniform(-1, 1, (50, 3))
    B = A + np.array([2.0, 0.0, 0.0])
    d_ab = _native_kdist_chunked(A, B)
    d_ba = _native_kdist_chunked(B, A)
    # 평행이동이라 두 방향 최대 거리는 같음
    np.testing.assert_allclose(d_ab, d_ba, atol=1e-9)


def test_kdist_chunked_result_invariant_to_pair_limit() -> None:
    """pair_limit 이 작아 chunked 경로를 강제해도 결과 일치."""
    rng = np.random.default_rng(13)
    A = rng.uniform(-5, 5, (200, 3))
    B = rng.uniform(-5, 5, (200, 3))
    d_big = _native_kdist_chunked(A, B, pair_limit=10_000_000)
    d_small = _native_kdist_chunked(A, B, pair_limit=1000)  # chunk 강제
    np.testing.assert_allclose(d_big, d_small, atol=1e-12)


def test_kdist_known_offset_distance() -> None:
    """query = reference + (dx, 0, 0) → max distance = dx."""
    rng = np.random.default_rng(17)
    ref = rng.uniform(-1, 1, (30, 3))
    q = ref + np.array([0.7, 0.0, 0.0])
    d = _native_kdist_chunked(q, ref)
    # q[i] 의 nearest in ref 는 q[i] - (0.7,0,0) = ref[i] 이므로 거리 정확 0.7
    np.testing.assert_allclose(d, 0.7, atol=1e-10)
