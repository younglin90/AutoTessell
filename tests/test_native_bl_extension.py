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


def test_native_ray_triangle_distance_matches_python_fallback(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from core.layers import native_bl as native_bl_module

    module = _native_bl_or_skip()
    if not hasattr(module, "ray_triangle_min_distance"):
        pytest.skip("native ray-triangle kernel is not built")
    origins = np.asarray(
        ((0.25, 0.25, 3.0), (0.75, 0.75, 3.0), (0.25, 0.25, 3.0)),
        dtype=np.float64,
    )
    directions = np.asarray(((0.0, 0.0, -1.0),) * 3, dtype=np.float64)
    triangles = np.asarray(
        (
            ((0.0, 0.0, 0.0), (1.0, 0.0, 0.0), (0.0, 1.0, 0.0)),
            ((0.0, 0.0, 1.0), (1.0, 0.0, 1.0), (0.0, 1.0, 1.0)),
        ),
        dtype=np.float64,
    )
    exclude = np.asarray(((False, False), (False, False), (False, True)))

    monkeypatch.setattr(native_bl_module, "load_native_bl", lambda: None)
    expected = native_bl_module._ray_triangle_min_distance(
        origins, directions, triangles, exclude, chunk_size=1
    )
    actual = np.asarray(
        module.ray_triangle_min_distance(
            origins, directions, triangles, exclude, 1e-12
        ),
        dtype=np.float64,
    )

    np.testing.assert_array_equal(np.isfinite(actual), np.isfinite(expected))
    np.testing.assert_allclose(actual, expected, rtol=1e-13, atol=1e-14)

    rng = np.random.default_rng(20260730)
    random_origins = rng.normal(size=(32, 3))
    random_directions = rng.normal(size=(32, 3))
    random_directions /= np.linalg.norm(random_directions, axis=1)[:, None]
    random_triangles = rng.normal(size=(64, 3, 3))
    random_exclude = rng.random((32, 64)) < 0.05
    random_expected = native_bl_module._ray_triangle_min_distance(
        random_origins,
        random_directions,
        random_triangles,
        random_exclude,
        chunk_size=7,
    )
    random_actual = np.asarray(
        module.ray_triangle_min_distance(
            random_origins,
            random_directions,
            random_triangles,
            random_exclude,
            1e-12,
        ),
        dtype=np.float64,
    )
    np.testing.assert_array_equal(
        np.isfinite(random_actual), np.isfinite(random_expected)
    )
    np.testing.assert_allclose(
        random_actual, random_expected, rtol=1e-13, atol=1e-14
    )

    empty = np.asarray(
        module.ray_triangle_min_distance(
            np.empty((0, 3)),
            np.empty((0, 3)),
            random_triangles,
            np.empty((0, 64), dtype=bool),
            1e-12,
        ),
        dtype=np.float64,
    )
    assert empty.shape == (0,)


def test_native_ray_triangle_distance_rejects_invalid_inputs() -> None:
    module = _native_bl_or_skip()
    if not hasattr(module, "ray_triangle_min_distance"):
        pytest.skip("native ray-triangle kernel is not built")
    origins = np.zeros((2, 3), dtype=np.float64)
    directions = np.ones((2, 3), dtype=np.float64)
    triangles = np.zeros((1, 3, 3), dtype=np.float64)

    with pytest.raises(ValueError, match="shape"):
        module.ray_triangle_min_distance(origins, directions[:1], triangles)
    with pytest.raises(ValueError, match="exclude_mask"):
        module.ray_triangle_min_distance(
            origins, directions, triangles, np.zeros((1, 1), dtype=bool)
        )
    bad_origins = origins.copy()
    bad_origins[0, 0] = np.nan
    with pytest.raises(ValueError, match="finite"):
        module.ray_triangle_min_distance(bad_origins, directions, triangles)
