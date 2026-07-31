"""C++23 parity and fail-closed contracts for the fused quad transaction."""

from __future__ import annotations

import hashlib
from types import SimpleNamespace
from typing import Any
from unittest.mock import patch

import numpy as np
import pytest

from core.preprocessor.native_remesh.quad_dominant import (
    _prepare_quad_pairs_python,
    _select_quad_pairs_python,
    native_quad_dominant_remesh,
)


def _native_transaction() -> Any:
    from core.utils.native_extensions import load_native_metrics

    native = load_native_metrics()
    if native is None or not hasattr(native, "quad_dominant_transaction"):
        pytest.skip("native_metrics.quad_dominant_transaction is not built")
    return native


def _grid(size: int) -> tuple[np.ndarray, np.ndarray]:
    x, y = np.meshgrid(
        np.arange(size + 1, dtype=np.float64),
        np.arange(size + 1, dtype=np.float64),
    )
    vertices = np.ascontiguousarray(np.column_stack((x.ravel(), y.ravel(), np.zeros(x.size))))
    row = np.arange(size, dtype=np.int64)[:, None]
    column = np.arange(size, dtype=np.int64)[None, :]
    lower_left = row * (size + 1) + column
    triangles = np.empty((2 * size * size, 3), dtype=np.int64)
    triangles[0::2] = np.stack(
        (
            lower_left.ravel(),
            (lower_left + 1).ravel(),
            (lower_left + size + 2).ravel(),
        ),
        axis=1,
    )
    triangles[1::2] = np.stack(
        (
            lower_left.ravel(),
            (lower_left + size + 2).ravel(),
            (lower_left + size + 1).ravel(),
        ),
        axis=1,
    )
    return vertices, triangles


def _sha256(values: np.ndarray) -> str:
    return hashlib.sha256(values.tobytes()).hexdigest()


def _direct(
    native: Any,
    vertices: np.ndarray,
    triangles: np.ndarray,
) -> dict[str, Any]:
    return native.quad_dominant_transaction(
        vertices,
        triangles,
        np.empty((0, 2), dtype=np.int64),
        45.0,
        0.2,
        4.0,
        0.05,
    )


def test_native_quad_transaction_matches_independent_python_oracle() -> None:
    native = _native_transaction()
    vertices, triangles = _grid(6)
    face_pairs, preparation = _prepare_quad_pairs_python(vertices, triangles, [], 45.0)
    accepted, quads, quality, rejected = _select_quad_pairs_python(
        vertices,
        triangles,
        face_pairs,
        min_scaled_jacobian=0.2,
        max_aspect_ratio=4.0,
        max_warpage=0.05,
    )
    consumed = np.zeros(len(triangles), dtype=bool)
    consumed[accepted.reshape(-1)] = True

    actual = _direct(native, vertices, triangles)

    np.testing.assert_array_equal(actual["candidate_face_pairs"], face_pairs)
    np.testing.assert_array_equal(actual["preparation_diagnostics"], preparation)
    np.testing.assert_array_equal(actual["accepted_face_pairs"], accepted)
    np.testing.assert_array_equal(actual["remaining_triangles"], triangles[~consumed])
    np.testing.assert_array_equal(actual["quads"], quads)
    np.testing.assert_allclose(actual["quality"], quality, rtol=0.0, atol=1e-14)
    assert actual["rejected_quality"] == rejected


def test_fused_public_route_preserves_sources_and_is_deterministic() -> None:
    _native_transaction()
    vertices, triangles = _grid(12)
    vertex_hash = _sha256(vertices)
    triangle_hash = _sha256(triangles)

    results = [native_quad_dominant_remesh(vertices, triangles) for _ in range(3)]

    signatures = [
        (
            _sha256(result.vertices),
            _sha256(result.triangles),
            _sha256(result.quads),
            result.diagnostics.model_dump(),
        )
        for result in results
    ]
    assert signatures == [signatures[0]] * 3
    assert _sha256(vertices) == vertex_hash
    assert _sha256(triangles) == triangle_hash
    assert results[0].diagnostics.output_quads == 144
    assert results[0].diagnostics.output_triangles == 0


def test_fused_public_route_matches_extension_absent_oracle() -> None:
    _native_transaction()
    vertices, triangles = _grid(5)
    native_result = native_quad_dominant_remesh(vertices, triangles)

    with patch("core.utils.native_extensions.load_native_metrics", return_value=None):
        oracle = native_quad_dominant_remesh(vertices, triangles)

    np.testing.assert_array_equal(native_result.vertices, oracle.vertices)
    np.testing.assert_array_equal(native_result.triangles, oracle.triangles)
    np.testing.assert_array_equal(native_result.quads, oracle.quads)
    np.testing.assert_array_equal(native_result.accepted_face_pairs, oracle.accepted_face_pairs)
    np.testing.assert_array_equal(
        native_result.remaining_triangle_source_indices,
        oracle.remaining_triangle_source_indices,
    )
    native_diagnostics = native_result.diagnostics.model_dump()
    oracle_diagnostics = oracle.diagnostics.model_dump()
    for metric in (
        "min_quad_scaled_jacobian",
        "max_quad_aspect_ratio",
        "max_quad_warpage",
    ):
        assert native_diagnostics.pop(metric) == pytest.approx(
            oracle_diagnostics.pop(metric), abs=1e-14
        )
    assert native_diagnostics == oracle_diagnostics


def test_native_quad_transaction_direct_abi_is_strict() -> None:
    native = _native_transaction()
    vertices, triangles = _grid(1)
    walls = np.empty((0, 2), dtype=np.int64)

    with pytest.raises((TypeError, ValueError)):
        native.quad_dominant_transaction(
            vertices.astype(np.float32), triangles, walls, 45.0, 0.2, 4.0, 0.05
        )
    with pytest.raises((TypeError, ValueError)):
        native.quad_dominant_transaction(
            vertices, triangles.astype(np.int32), walls, 45.0, 0.2, 4.0, 0.05
        )
    with pytest.raises((TypeError, ValueError)):
        native.quad_dominant_transaction(vertices, triangles[:, ::-1], walls, 45.0, 0.2, 4.0, 0.05)


def test_fused_wrapper_rejects_malformed_provenance_without_fallback() -> None:
    native = _native_transaction()
    vertices, triangles = _grid(2)
    baseline = _direct(native, vertices, triangles)

    def copied() -> dict[str, Any]:
        return {
            name: value.copy() if isinstance(value, np.ndarray) else value
            for name, value in baseline.items()
        }

    malformed: list[dict[str, Any]] = []
    wrong_remaining = copied()
    wrong_remaining["remaining_triangles"] = triangles.copy()
    malformed.append(wrong_remaining)
    wrong_quad = copied()
    wrong_quad["quads"][0] = np.roll(wrong_quad["quads"][0], 1)
    malformed.append(wrong_quad)
    wrong_candidate = copied()
    wrong_candidate["candidate_face_pairs"][0] = (0, 0)
    malformed.append(wrong_candidate)
    wrong_quality = copied()
    wrong_quality["quality"][0, 0] = np.nan
    malformed.append(wrong_quality)
    wrong_diagnostics = copied()
    wrong_diagnostics["preparation_diagnostics"] = np.zeros(4, dtype=np.int64)
    malformed.append(wrong_diagnostics)

    for payload in malformed:
        backend = SimpleNamespace(quad_dominant_transaction=lambda *_args, value=payload: value)
        with patch("core.utils.native_extensions.load_native_metrics", return_value=backend):
            with pytest.raises(RuntimeError, match="native"):
                native_quad_dominant_remesh(vertices, triangles)


def test_non_int64_valid_input_keeps_exact_decoder_contract() -> None:
    _native_transaction()
    vertices, triangles = _grid(2)

    int32_result = native_quad_dominant_remesh(vertices, triangles.astype(np.int32))
    object_result = native_quad_dominant_remesh(vertices, triangles.astype(object))

    np.testing.assert_array_equal(int32_result.triangles, object_result.triangles)
    np.testing.assert_array_equal(int32_result.quads, object_result.quads)
    with pytest.raises(ValueError, match="exact finite signed int64"):
        native_quad_dominant_remesh(vertices, triangles.astype(np.float64))


def test_noncontiguous_int64_input_is_copied_into_strict_native_abi() -> None:
    _native_transaction()
    vertices, triangles = _grid(3)
    storage = np.empty((len(triangles), 6), dtype=np.int64)
    storage[:, ::2] = triangles
    noncontiguous = storage[:, ::2]
    assert not noncontiguous.flags.c_contiguous

    actual = native_quad_dominant_remesh(vertices, noncontiguous)
    expected = native_quad_dominant_remesh(vertices, triangles)

    np.testing.assert_array_equal(actual.triangles, expected.triangles)
    np.testing.assert_array_equal(actual.quads, expected.quads)
    np.testing.assert_array_equal(actual.accepted_face_pairs, expected.accepted_face_pairs)
    np.testing.assert_array_equal(
        actual.remaining_triangle_source_indices,
        expected.remaining_triangle_source_indices,
    )
    assert actual.diagnostics == expected.diagnostics
