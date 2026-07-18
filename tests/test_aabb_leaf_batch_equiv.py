"""BETA2831 — closest_points_all_shared 의 batched-leaf 갱신이 legacy per-point
loop 과 (cp, d, ti) bit-exact 동일함을 보장하는 회귀 테스트.
"""
from __future__ import annotations

import numpy as np
import pytest

from core.utils.aabb import TriangleBVH


def _random_triangle_soup(n_tri: int, seed: int) -> tuple[np.ndarray, np.ndarray]:
    rng = np.random.default_rng(seed)
    V = rng.uniform(-1.0, 1.0, size=(n_tri * 3, 3))
    F = np.arange(n_tri * 3, dtype=np.int64).reshape(n_tri, 3)
    return V, F


@pytest.mark.parametrize("seed", [0, 1, 2, 3, 4])
def test_closest_points_all_shared_matches_legacy_random(seed: int) -> None:
    V, F = _random_triangle_soup(n_tri=137, seed=seed)
    bvh = TriangleBVH.build(V, F, leaf_size=8)

    rng = np.random.default_rng(seed + 1000)
    P = rng.uniform(-2.0, 2.0, size=(200, 3))

    cp_new, d_new, ti_new = bvh.closest_points_all_shared(P)
    cp_leg, d_leg, ti_leg = bvh._closest_points_batch_legacy(P)

    assert np.array_equal(d_new, d_leg)
    assert np.array_equal(ti_new, ti_leg)
    assert np.array_equal(cp_new, cp_leg)


def test_closest_points_all_shared_matches_legacy_axis_aligned() -> None:
    # 축상 근접점(꼭짓점/변/면 위 정확히 놓이는) 케이스 포함.
    V = np.array(
        [
            [0.0, 0.0, 0.0],
            [1.0, 0.0, 0.0],
            [0.0, 1.0, 0.0],
            [1.0, 0.0, 0.0],
            [2.0, 0.0, 0.0],
            [1.0, 1.0, 0.0],
            [0.0, 0.0, 1.0],
            [1.0, 0.0, 1.0],
            [0.0, 1.0, 1.0],
        ],
        dtype=np.float64,
    )
    F = np.array([[0, 1, 2], [3, 4, 5], [6, 7, 8]], dtype=np.int64)
    bvh = TriangleBVH.build(V, F, leaf_size=2)

    P = np.array(
        [
            [0.0, 0.0, 0.0],       # vertex
            [0.5, 0.0, 0.0],       # edge midpoint
            [0.25, 0.25, 0.0],     # interior
            [0.0, 0.0, 5.0],       # far above
            [1.0, 1.0, 0.0],       # shared vertex
            [1.5, 0.5, 0.0],       # near second tri
            [0.3, 0.3, 1.0],       # near third tri
        ],
        dtype=np.float64,
    )

    cp_new, d_new, ti_new = bvh.closest_points_all_shared(P)
    cp_leg, d_leg, ti_leg = bvh._closest_points_batch_legacy(P)

    assert np.array_equal(d_new, d_leg)
    assert np.array_equal(ti_new, ti_leg)
    assert np.array_equal(cp_new, cp_leg)


def test_closest_points_all_shared_matches_legacy_larger() -> None:
    V, F = _random_triangle_soup(n_tri=800, seed=42)
    bvh = TriangleBVH.build(V, F, leaf_size=8)

    rng = np.random.default_rng(4242)
    P = rng.uniform(-3.0, 3.0, size=(500, 3))

    cp_new, d_new, ti_new = bvh.closest_points_all_shared(P)
    cp_leg, d_leg, ti_leg = bvh._closest_points_batch_legacy(P)

    assert np.array_equal(d_new, d_leg)
    assert np.array_equal(ti_new, ti_leg)
    assert np.array_equal(cp_new, cp_leg)
