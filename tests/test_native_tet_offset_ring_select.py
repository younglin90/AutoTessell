"""CYLSKEW3 — select_offset_ring_variant 결정을 실측 3케이스로 재현."""
from __future__ import annotations

import numpy as np

from core.generator.native_tet.offset_ring import select_offset_ring_variant


def test_cylinder_keep() -> None:
    seeds = np.ones((3, 3))
    off = {"skew": 44.9, "nonortho": 89.2}
    on = {"skew": 40.8, "nonortho": 88.7}
    result, info = select_offset_ring_variant(seeds, off, on)
    assert info["decision"] == "keep"
    assert result.shape == seeds.shape


def test_sphere_n500_revert() -> None:
    seeds = np.ones((5, 3))
    off = {"skew": 1.46, "nonortho": 10.6}
    on = {"skew": 2.44, "nonortho": 79.7}
    result, info = select_offset_ring_variant(seeds, off, on)
    assert info["decision"] == "revert"
    assert result.shape == (0, 3)


def test_sphere_n1000_keep() -> None:
    seeds = np.ones((7, 3))
    off = {"skew": 2.60, "nonortho": 87.1}
    on = {"skew": 2.25, "nonortho": 83.3}
    result, info = select_offset_ring_variant(seeds, off, on)
    assert info["decision"] == "keep"
    assert result.shape == seeds.shape


def test_missing_metric_reverts() -> None:
    seeds = np.ones((2, 3))
    off = {"skew": 1.0, "nonortho": 5.0}
    on = {"skew": float("nan"), "nonortho": 5.0}
    result, info = select_offset_ring_variant(seeds, off, on)
    assert info["decision"] == "revert"
    assert result.shape == (0, 3)
