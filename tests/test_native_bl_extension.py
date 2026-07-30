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


def test_indexed_wall_collision_matches_dense_incident_oracle() -> None:
    module = _native_bl_or_skip()
    if not hasattr(module, "indexed_wall_collision_distances"):
        pytest.skip("indexed native wall-collision kernel is not built")

    rng = np.random.default_rng(20260730)
    points = rng.uniform(-2.0, 2.0, size=(256, 3))
    ray_ids = rng.choice(256, size=64, replace=False).astype(np.int64)
    triangle_ids = np.vstack(
        [rng.choice(256, size=3, replace=False) for _ in range(400)]
    ).astype(np.int64)
    triangle_ids[:64, 0] = ray_ids
    directions = rng.normal(size=(64, 3))
    directions /= np.linalg.norm(directions, axis=1)[:, None]
    exclude = np.any(
        ray_ids[:, None, None] == triangle_ids[None, :, :], axis=2
    )
    expected = np.asarray(
        module.ray_triangle_min_distance(
            points[ray_ids], directions, points[triangle_ids], exclude, 1e-12
        ),
        dtype=np.float64,
    )

    for search in (np.inf, 0.25, 1.0):
        wanted = (
            expected
            if np.isinf(search)
            else np.where(expected <= search, expected, np.inf)
        )
        actual = np.asarray(
            module.indexed_wall_collision_distances(
                points, ray_ids, directions, triangle_ids, search, 1e-12
            ),
            dtype=np.float64,
        )
        np.testing.assert_array_equal(np.isfinite(actual), np.isfinite(wanted))
        np.testing.assert_allclose(actual, wanted, rtol=1e-13, atol=1e-14)
        repeated = np.asarray(
            module.indexed_wall_collision_distances(
                points, ray_ids, directions, triangle_ids, search, 1e-12
            ),
            dtype=np.float64,
        )
        np.testing.assert_array_equal(actual.view(np.uint64), repeated.view(np.uint64))


def test_indexed_wall_collision_conservative_pruning_and_search_cap() -> None:
    module = _native_bl_or_skip()
    if not hasattr(module, "indexed_wall_collision_distances"):
        pytest.skip("indexed native wall-collision kernel is not built")

    points = np.asarray(
        (
            (0.0, 0.0, 1.0),
            (-1.0, -1.0, 0.0),
            (1.0, -1.0, 0.0),
            (10.0, 10.0, 0.0),
            (100.0, 0.0, 0.0),
            (101.0, 0.0, 0.0),
            (100.0, 1.0, 0.0),
        ),
        dtype=np.float64,
    )
    ray_ids = np.asarray((0,), dtype=np.int64)
    directions = np.asarray(((0.0, 0.0, -1.0),), dtype=np.float64)
    triangle_ids = np.vstack(
        (
            np.tile(np.asarray((4, 5, 6), dtype=np.int64), (1024, 1)),
            np.asarray(((1, 2, 3),), dtype=np.int64),
        )
    )
    at_cap = np.asarray(
        module.indexed_wall_collision_distances(
            points, ray_ids, directions, triangle_ids, 1.0, 1e-12
        )
    )
    np.testing.assert_array_equal(at_cap, np.asarray((1.0,)))

    translated = points + np.asarray((-10.25, -20.75, -30.5))
    translated_hit = np.asarray(
        module.indexed_wall_collision_distances(
            translated, ray_ids, directions, triangle_ids, 1.0, 1e-12
        )
    )
    np.testing.assert_array_equal(translated_hit, at_cap)
    below_cap = np.asarray(
        module.indexed_wall_collision_distances(
            points, ray_ids, directions, triangle_ids, 0.999, 1e-12
        )
    )
    assert np.isinf(below_cap[0])


def test_indexed_wall_collision_rejects_incident_face_and_bad_abi() -> None:
    module = _native_bl_or_skip()
    if not hasattr(module, "indexed_wall_collision_distances"):
        pytest.skip("indexed native wall-collision kernel is not built")
    points = np.asarray(
        ((0.25, 0.25, 1.0), (0.0, 0.0, 0.0),
         (1.0, 0.0, 0.0), (0.0, 1.0, 0.0)),
        dtype=np.float64,
    )
    ray_ids = np.asarray((0,), dtype=np.int64)
    directions = np.asarray(((0.0, 0.0, -1.0),), dtype=np.float64)
    triangle_ids = np.asarray(((0, 2, 3),), dtype=np.int64)
    result = np.asarray(
        module.indexed_wall_collision_distances(
            points, ray_ids, directions, triangle_ids, np.inf, 1e-12
        )
    )
    assert np.isinf(result[0])

    with pytest.raises(ValueError, match="ray vertex index"):
        module.indexed_wall_collision_distances(
            points, np.asarray((99,)), directions, triangle_ids
        )
    with pytest.raises(ValueError, match="triangle vertex index"):
        module.indexed_wall_collision_distances(
            points, ray_ids, directions, np.asarray(((1, 2, 99),))
        )
    with pytest.raises(ValueError, match="max_distance"):
        module.indexed_wall_collision_distances(
            points, ray_ids, directions, triangle_ids, 0.0
        )

    empty = np.asarray(
        module.indexed_wall_collision_distances(
            points,
            np.empty((0,), dtype=np.int64),
            np.empty((0, 3)),
            triangle_ids,
        )
    )
    assert empty.shape == (0,)


def test_compute_collision_distance_no_longer_skips_over_twenty_thousand_faces() -> None:
    from core.layers.native_bl import _compute_collision_distance

    module = _native_bl_or_skip()
    if not hasattr(module, "indexed_wall_collision_distances"):
        pytest.skip("indexed native wall-collision kernel is not built")
    points = np.asarray(
        (
            (100.0, 0.0, 0.0),
            (101.0, 0.0, 0.0),
            (100.0, 1.0, 0.0),
            (0.0, 0.0, 0.0),
            (1.0, 0.0, 0.0),
            (0.0, 1.0, 0.0),
            (0.25, 0.25, 1.0),
        ),
        dtype=np.float64,
    )
    faces = [[0, 1, 2] for _ in range(20_000)] + [[3, 4, 5]]
    result = _compute_collision_distance(
        points,
        faces,
        list(range(20_001)),
        [6],
        {6: np.asarray((0.0, 0.0, 1.0))},
        max_tris=20_000,
        max_search_distance=1.0,
    )
    assert result == {6: pytest.approx(1.0)}


def test_compute_collision_distance_applies_search_limit_at_small_size() -> None:
    from core.layers.native_bl import _compute_collision_distance

    points = np.asarray(
        (
            (0.0, 0.0, 0.0),
            (1.0, 0.0, 0.0),
            (0.0, 1.0, 0.0),
            (0.25, 0.25, 2.0),
        ),
        dtype=np.float64,
    )
    arguments = (
        points,
        [[0, 1, 2]],
        [0],
        [3],
        {3: np.asarray((0.0, 0.0, 1.0))},
    )

    assert _compute_collision_distance(
        *arguments, max_search_distance=1.0
    ) == {}
    assert _compute_collision_distance(
        *arguments, max_search_distance=None
    ) == {3: pytest.approx(2.0)}


def test_compute_collision_distance_python_fallback_batches_incident_masks(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from core.layers import native_bl as native_bl_module

    far_triangle = np.asarray(
        ((100.0, 0.0, 0.0), (101.0, 0.0, 0.0), (100.0, 1.0, 0.0))
    )
    hit_triangle = np.asarray(
        ((0.0, 0.0, 0.0), (1.0, 0.0, 0.0), (0.0, 1.0, 0.0))
    )
    origins = np.tile(np.asarray((0.25, 0.25, 1.0)), (300, 1))
    points = np.vstack((far_triangle, hit_triangle, origins))
    faces = [[0, 1, 2] for _ in range(1000)] + [[3, 4, 5]]
    wall_vertices = list(range(6, 306))
    normals = {
        vertex: np.asarray((0.0, 0.0, 1.0)) for vertex in wall_vertices
    }

    original = native_bl_module._ray_triangle_min_distance
    observed_shapes: list[tuple[int, int]] = []

    def _recording_oracle(
        ray_origins: np.ndarray,
        ray_directions: np.ndarray,
        triangles: np.ndarray,
        exclude_mask: np.ndarray | None = None,
        *,
        chunk_size: int = 512,
    ) -> np.ndarray:
        assert exclude_mask is not None
        observed_shapes.append(exclude_mask.shape)
        return original(
            ray_origins,
            ray_directions,
            triangles,
            exclude_mask,
            chunk_size=chunk_size,
        )

    monkeypatch.setattr(native_bl_module, "load_native_bl", lambda: None)
    monkeypatch.setattr(
        native_bl_module, "_ray_triangle_min_distance", _recording_oracle
    )
    result = native_bl_module._compute_collision_distance(
        points,
        faces,
        list(range(1001)),
        wall_vertices,
        normals,
        max_search_distance=1.0,
    )

    assert len(result) == 300
    assert all(distance == pytest.approx(1.0) for distance in result.values())
    assert len(observed_shapes) > 1
    assert max(rows for rows, _ in observed_shapes) <= 128
    assert {columns for _, columns in observed_shapes} == {1001}
