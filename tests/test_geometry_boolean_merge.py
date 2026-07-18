"""CARD BOOLMERGE1 — core/utils/geometry.inside_union_winding_number 단위 테스트.

fTetWild §3.6 방식(per-input surface 별 GWN 독립 계산 후 boolean 결합)의 union
경로만 검증한다. intersection/difference 는 후속 카드 범위.
"""
from __future__ import annotations

import numpy as np

from core.utils.geometry import (
    inside_generalized_winding_number,
    inside_union_winding_number,
)


def _unit_cube_mesh():
    """[0,1]^3 축-정렬 cube 의 표면 (8 verts + 12 triangles)."""
    V = np.array([
        [0, 0, 0], [1, 0, 0], [1, 1, 0], [0, 1, 0],
        [0, 0, 1], [1, 0, 1], [1, 1, 1], [0, 1, 1],
    ], dtype=np.float64)
    F = np.array([
        [0, 2, 1], [0, 3, 2],   # bottom (z=0)
        [4, 5, 6], [4, 6, 7],   # top (z=1)
        [0, 1, 5], [0, 5, 4],   # front (y=0)
        [2, 3, 7], [2, 7, 6],   # back  (y=1)
        [1, 2, 6], [1, 6, 5],   # right (x=1)
        [0, 4, 7], [0, 7, 3],   # left  (x=0)
    ], dtype=np.int64)
    return V, F


def _cube_mesh(lo: float, hi: float):
    """[lo, hi]^3 축-정렬 cube — _unit_cube_mesh 를 스케일/평행이동."""
    V, F = _unit_cube_mesh()
    return V * (hi - lo) + lo, F


def test_overlapping_cubes_union_volume_within_3pct() -> None:
    """A=[0,1]^3, B=[0.5,1.5]^3 — 해석적 union 부피=1.875, ±3% 이내 Monte-Carlo."""
    V_a, F_a = _cube_mesh(0.0, 1.0)
    V_b, F_b = _cube_mesh(0.5, 1.5)
    surfaces = [(V_a, F_a), (V_b, F_b)]

    rng = np.random.default_rng(42)
    n_samples = 60_000
    # sampling bbox covers both cubes with margin.
    lo, hi = -0.2, 1.7
    pts = rng.uniform(lo, hi, size=(n_samples, 3))
    box_volume = (hi - lo) ** 3

    mask = inside_union_winding_number(pts, surfaces)
    estimated_volume = box_volume * mask.mean()

    analytic_union = 1.875
    rel_err = abs(estimated_volume - analytic_union) / analytic_union
    assert rel_err <= 0.03, (
        f"estimated union volume {estimated_volume:.4f} vs analytic "
        f"{analytic_union} (rel_err={rel_err:.4f})"
    )


def test_disjoint_cubes_bodies_stay_separate() -> None:
    """A=[0,1]^3, B=[10,11]^3 — 각 내부는 inside, 사이 점은 outside."""
    V_a, F_a = _cube_mesh(0.0, 1.0)
    V_b, F_b = _cube_mesh(10.0, 11.0)
    surfaces = [(V_a, F_a), (V_b, F_b)]

    pts = np.array([
        [0.5, 0.5, 0.5],
        [10.5, 10.5, 10.5],
        [5.0, 5.0, 5.0],
    ], dtype=np.float64)
    mask = inside_union_winding_number(pts, surfaces)
    assert list(mask) == [True, True, False]


def test_single_surface_identity() -> None:
    """surfaces=[(V,F)] 하나일 때 inside_generalized_winding_number 와 정확히 일치."""
    V, F = _unit_cube_mesh()
    q = np.array([
        [0.11, 0.13, 0.17],
        [0.31, 0.42, 0.63],
        [2.0, 2.0, 2.0],
        [-1.0, 0.5, 0.5],
    ], dtype=np.float64)

    expected = inside_generalized_winding_number(q, V, F)
    actual = inside_union_winding_number(q, [(V, F)])

    assert list(actual) == list(expected)


def test_empty_surfaces_returns_all_false() -> None:
    """빈 리스트 → 전부 False."""
    q = np.array([[0.5, 0.5, 0.5], [10.0, 10.0, 10.0]], dtype=np.float64)
    mask = inside_union_winding_number(q, [])
    assert mask.shape == (2,)
    assert mask.dtype == bool
    assert not mask.any()
