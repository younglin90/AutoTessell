"""Parity and contract tests for the optional native_bl C++23 kernels."""

from __future__ import annotations

from typing import Any

import numpy as np
import pytest

from core.utils.native_extensions import load_native_bl


def _native_bl_or_skip() -> Any:
    module = load_native_bl()
    if module is None:
        pytest.skip("native_bl extension is not built")
    return module


def test_spatial_hash_matches_dense_opposing_front_oracle() -> None:
    module = _native_bl_or_skip()
    rng = np.random.default_rng(20260730)
    points = rng.uniform(-1.0, 1.0, size=(512, 3))
    normals = rng.normal(size=(512, 3))
    normals /= np.linalg.norm(normals, axis=1, keepdims=True)
    radius = 0.25
    threshold = -0.2

    dot = normals @ normals.T
    delta = points[:, None, :] - points[None, :, :]
    distance_squared = np.einsum("ijk,ijk->ij", delta, delta)
    np.fill_diagonal(distance_squared, np.inf)
    expected = (
        (dot < threshold) & (distance_squared <= radius * radius)
    ).any(axis=1)
    actual = np.asarray(
        module.nearby_opposite_front_mask(normals, points, radius, threshold),
        dtype=bool,
    )

    np.testing.assert_array_equal(actual, expected)


def test_spatial_hash_rejects_nonpositive_radius() -> None:
    module = _native_bl_or_skip()
    points = np.zeros((2, 3), dtype=np.float64)
    normals = np.zeros((2, 3), dtype=np.float64)

    with pytest.raises(ValueError, match="search_radius"):
        module.nearby_opposite_front_mask(normals, points, 0.0)
