"""Exact vertex-identity contract for the native quad public boundary."""

from __future__ import annotations

import hashlib
from collections.abc import Callable
from pathlib import Path
from typing import Literal
from unittest.mock import patch

import numpy as np
import pytest

from core.preprocessor.native_remesh.quad_dominant import native_quad_dominant_remesh


def _triangles() -> np.ndarray:
    return np.array([[0, 1, 2], [0, 2, 3]], dtype=np.int64)


def _lossy_int64_vertices() -> np.ndarray:
    base = 2**53
    return np.array(
        [
            [base + 1, 0, 0],
            [base + 3, 0, 0],
            [base + 3, 2, 0],
            [base + 1, 2, 0],
        ],
        dtype=np.int64,
    )


def _lossy_uint64_vertices() -> np.ndarray:
    maximum = np.iinfo(np.uint64).max
    return np.array(
        [
            [maximum, 0, 0],
            [maximum - 2, 0, 0],
            [maximum - 2, 2, 0],
            [maximum, 2, 0],
        ],
        dtype=np.uint64,
    )


def _lossy_longdouble_vertices() -> np.ndarray:
    one = np.longdouble(1.0)
    next_value = np.nextafter(one, np.longdouble(2.0))
    if next_value == np.longdouble(float(next_value)):
        pytest.skip("longdouble has no precision beyond float64 on this platform")
    vertices = np.array(
        [[0, 0, 0], [1, 0, 0], [1, 1, 0], [0, 1, 0]],
        dtype=np.longdouble,
    )
    vertices[1, 0] = next_value
    return vertices


@pytest.mark.parametrize(
    "vertices_factory",
    [_lossy_int64_vertices, _lossy_uint64_vertices, _lossy_longdouble_vertices],
)
def test_lossy_vertex_coordinates_fail_before_native_dispatch(
    vertices_factory: Callable[[], np.ndarray],
    tmp_path: Path,
) -> None:
    vertices = vertices_factory()
    triangles = _triangles()
    vertex_bytes = vertices.tobytes()
    triangle_bytes = triangles.tobytes()
    native_calls = 0

    def forbidden_native_load() -> None:
        nonlocal native_calls
        native_calls += 1
        raise AssertionError("lossy coordinates reached the native backend")

    with patch(
        "core.utils.native_extensions.load_native_metrics",
        side_effect=forbidden_native_load,
    ):
        with pytest.raises(ValueError, match="exactly representable as float64"):
            native_quad_dominant_remesh(vertices, triangles)

    assert native_calls == 0
    assert vertices.tobytes() == vertex_bytes
    assert triangles.tobytes() == triangle_bytes
    assert list(tmp_path.iterdir()) == []


@pytest.mark.parametrize(
    "vertices",
    [
        [
            [2**53 + 1, 0.0, 0.0],
            [2**53 + 3, 0.0, 0.0],
            [2**53 + 3, 2.0, 0.0],
            [2**53 + 1, 2.0, 0.0],
        ],
        [
            [2**64 - 1, 0.0, 0.0],
            [2**64 - 3, 0.0, 0.0],
            [2**64 - 3, 2.0, 0.0],
            [2**64 - 1, 2.0, 0.0],
        ],
    ],
)
def test_lossy_mixed_python_lists_fail_before_native_dispatch(vertices: object) -> None:
    with patch("core.utils.native_extensions.load_native_metrics") as native_load:
        with pytest.raises(ValueError, match="exactly representable as float64"):
            native_quad_dominant_remesh(vertices, _triangles())
    native_load.assert_not_called()


@pytest.mark.parametrize(
    "vertices",
    [
        [[False, 0.0, 0.0], [1, 0.0, 0.0], [1, 1.0, 0.0], [0, 1.0, 0.0]],
        [[0j, 0.0, 0.0], [1, 0.0, 0.0], [1, 1.0, 0.0], [0, 1.0, 0.0]],
    ],
)
def test_ambiguous_mixed_python_lists_fail_before_native_dispatch(vertices: object) -> None:
    with patch("core.utils.native_extensions.load_native_metrics") as native_load:
        with pytest.raises(ValueError, match="real numeric array"):
            native_quad_dominant_remesh(vertices, _triangles())
    native_load.assert_not_called()


def test_exact_mixed_python_list_preserves_geometry_and_hashes() -> None:
    vertices = [[0, 0.0, 0], [1.0, 0, 0.0], [1, 1.0, 0], [0.0, 1, 0.0]]

    result = native_quad_dominant_remesh(vertices, _triangles())

    assert hashlib.sha256(result.vertices.tobytes()).hexdigest() == (
        "dbc3917f0b890feff0f06cfc14b37405f5c9a97349d99036d1e782a7a2058a81"
    )
    assert hashlib.sha256(result.triangles.tobytes()).hexdigest() == (
        "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855"
    )
    assert hashlib.sha256(result.quads.tobytes()).hexdigest() == (
        "7eaad883b75863afc7d1028d04846b9d3b0de09f79e0fbc355edde84c8e0b279"
    )


@pytest.mark.parametrize(
    "vertices",
    [
        np.zeros((4, 3), dtype=np.bool_),
        np.full((4, 3), "1.0", dtype="U3"),
        np.ones((4, 3), dtype=np.complex128),
        np.full((4, 3), 1.0, dtype=object),
    ],
)
def test_non_real_or_ambiguous_vertex_payloads_fail_closed(vertices: np.ndarray) -> None:
    with patch("core.utils.native_extensions.load_native_metrics") as native_load:
        with pytest.raises(ValueError, match="real numeric array"):
            native_quad_dominant_remesh(vertices, _triangles())
    native_load.assert_not_called()


@pytest.mark.parametrize(
    "vertices",
    [
        np.array(
            [[0, 0, 0], [2, 0, 0], [2, 2, 0], [0, 2, 0]],
            dtype=np.int32,
        ),
        np.array(
            [
                [2**53, 0, 0],
                [2**53 + 2, 0, 0],
                [2**53 + 2, 2, 0],
                [2**53, 2, 0],
            ],
            dtype=np.int64,
        ),
        np.array(
            [[0, 0, 0], [1, 0, 0], [1, 1, 0], [0, 1, 0]],
            dtype=np.float32,
        ),
    ],
)
def test_exactly_representable_vertex_payloads_preserve_geometry(
    vertices: np.ndarray,
) -> None:
    before = vertices.copy()
    result = native_quad_dominant_remesh(vertices, _triangles())

    np.testing.assert_array_equal(result.vertices, before.astype(np.float64))
    np.testing.assert_array_equal(vertices, before)
    np.testing.assert_array_equal(result.quads, np.array([[1, 2, 3, 0]]))
    assert result.diagnostics.output_quads == 1
    assert result.diagnostics.output_triangles == 0


@pytest.mark.parametrize("order", ["C", "F"])
def test_float64_result_storage_is_isolated_from_input(order: Literal["C", "F"]) -> None:
    vertices = np.array(
        [[0.0, 0.0, 0.0], [1.0, 0.0, 0.0], [1.0, 1.0, 0.0], [0.0, 1.0, 0.0]],
        dtype=np.float64,
        order=order,
    )
    before = vertices.copy()

    result = native_quad_dominant_remesh(vertices, _triangles())
    result.vertices[0, 0] = 42.0

    np.testing.assert_array_equal(vertices, before)
    assert result.vertices.flags.c_contiguous


def test_float64_valid_path_retains_permanent_hashes() -> None:
    vertices = np.array(
        [[0.0, 0.0, 0.0], [1.0, 0.0, 0.0], [1.0, 1.0, 0.0], [0.0, 1.0, 0.0]],
        dtype=np.float64,
    )
    result = native_quad_dominant_remesh(vertices, _triangles())

    assert hashlib.sha256(result.vertices.tobytes()).hexdigest() == (
        "dbc3917f0b890feff0f06cfc14b37405f5c9a97349d99036d1e782a7a2058a81"
    )
    assert hashlib.sha256(result.triangles.tobytes()).hexdigest() == (
        "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855"
    )
    assert hashlib.sha256(result.quads.tobytes()).hexdigest() == (
        "7eaad883b75863afc7d1028d04846b9d3b0de09f79e0fbc355edde84c8e0b279"
    )
    assert result.diagnostics.model_dump() == {
        "input_triangles": 2,
        "output_quads": 1,
        "output_triangles": 0,
        "protected_boundary_edges": 4,
        "protected_feature_edges": 0,
        "protected_wall_edges": 0,
        "candidate_pairs": 1,
        "accepted_pairs": 1,
        "rejected_protected": 0,
        "rejected_quality": 0,
        "min_quad_scaled_jacobian": 1.0,
        "max_quad_aspect_ratio": 1.0,
        "max_quad_warpage": 0.0,
        "route": "native_quad_dominant",
        "contract": "native_quad",
        "fallback_reason": None,
    }
