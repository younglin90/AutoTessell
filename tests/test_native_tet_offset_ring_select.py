"""CYLSKEW3 — select_offset_ring_variant 결정을 실측 3케이스로 재현."""
from __future__ import annotations

import numpy as np
import pytest

from core.generator.native_tet import mesher
from core.generator.native_tet.mesher import _offset_ring_mode, _raw_proxy_metrics
from core.generator.native_tet.offset_ring import select_offset_ring_variant


def test_clean_proxy_cylinder_keep() -> None:
    seeds = np.ones((3, 3))
    off = {"skew": 69.47, "nonortho": 88.80}
    on = {"skew": 69.47, "nonortho": 88.80}
    result, info = select_offset_ring_variant(seeds, off, on)
    assert info["decision"] == "keep"
    assert result.shape == seeds.shape


def test_clean_proxy_cube_revert() -> None:
    seeds = np.ones((5, 3))
    off = {"skew": 2.38, "nonortho": 61.87}
    on = {"skew": 8.23, "nonortho": 80.94}
    result, info = select_offset_ring_variant(seeds, off, on)
    assert info["decision"] == "revert"
    assert result.shape == (0, 3)


def test_sphere_proxy_worsening_reverts() -> None:
    seeds = np.ones((7, 3))
    off = {"skew": 1.46, "nonortho": 10.6}
    on = {"skew": 2.44, "nonortho": 79.7}
    result, info = select_offset_ring_variant(seeds, off, on)
    assert info["decision"] == "revert"
    assert result.shape == (0, 3)


def test_missing_metric_reverts() -> None:
    seeds = np.ones((2, 3))
    off = {"skew": 1.0, "nonortho": 5.0}
    on = {"skew": float("nan"), "nonortho": 5.0}
    result, info = select_offset_ring_variant(seeds, off, on)
    assert info["decision"] == "revert"
    assert result.shape == (0, 3)


def test_raw_proxy_excludes_zero_volume_tets() -> None:
    pts = np.array([
        [0.0, 0.0, 0.0],
        [1.0, 0.0, 0.0],
        [0.0, 1.0, 0.0],
        [0.0, 0.0, 1.0],
        [0.25, 0.25, 0.0],
    ])
    tets = np.array([[0, 1, 2, 3], [0, 1, 2, 4]])

    metrics, raw_count, valid_count = _raw_proxy_metrics(pts, tets)
    clean_metrics, _, _ = _raw_proxy_metrics(pts, tets[:1])

    assert (raw_count, valid_count) == (2, 1)
    assert metrics == clean_metrics


def test_raw_proxy_no_valid_tets_fail_safe_revert() -> None:
    pts = np.array([
        [0.0, 0.0, 0.0],
        [1.0, 0.0, 0.0],
        [0.0, 1.0, 0.0],
        [0.25, 0.25, 0.0],
    ])
    metrics, raw_count, valid_count = _raw_proxy_metrics(
        pts, np.array([[0, 1, 2, 3]]),
    )
    result, info = select_offset_ring_variant(
        np.ones((2, 3)), {"skew": 1.0, "nonortho": 1.0}, metrics,
    )

    assert metrics == {}
    assert (raw_count, valid_count) == (1, 0)
    assert info["decision"] == "revert"
    assert result.shape == (0, 3)


def test_raw_proxy_nonfinite_metric_returns_empty(monkeypatch: pytest.MonkeyPatch) -> None:
    pts = np.array([
        [0.0, 0.0, 0.0],
        [1.0, 0.0, 0.0],
        [0.0, 1.0, 0.0],
        [0.0, 0.0, 1.0],
    ])
    monkeypatch.setattr(mesher, "_skew_proxy", lambda _pts, _tets: float("nan"))

    metrics, raw_count, valid_count = _raw_proxy_metrics(
        pts, np.array([[0, 1, 2, 3]]),
    )

    assert metrics == {}
    assert (raw_count, valid_count) == (1, 1)


@pytest.mark.parametrize("value", ["0", "off", "false"])
def test_offset_ring_explicit_off(value: str) -> None:
    assert _offset_ring_mode(value, 10, 10) == ("off", False)


@pytest.mark.parametrize("value", ["1", "on", "true"])
def test_offset_ring_explicit_on_ignores_size(value: str) -> None:
    assert _offset_ring_mode(value, 1001, 2001) == ("on", True)


def test_offset_ring_unset_is_off() -> None:
    assert _offset_ring_mode(None, 10, 10) == ("off", False)


def test_offset_ring_explicit_auto_uses_inclusive_caps() -> None:
    assert _offset_ring_mode("auto", 1000, 2000) == ("auto", True)
    assert _offset_ring_mode("auto", 1001, 2000) == ("auto", False)
    assert _offset_ring_mode("auto", 1000, 2001) == ("auto", False)
