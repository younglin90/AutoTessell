"""Scale-range contracts for the native quad similarity normalization."""

from __future__ import annotations

import hashlib
from collections.abc import Callable
from unittest.mock import patch

import numpy as np
import pytest

from core.preprocessor.native_remesh.quad_dominant import (
    QuadDominantConfig,
    QuadDominantResult,
    native_quad_dominant_remesh,
)

_SCALES = (1e-150, 1e-18, 1e-16, 1e-15, 1e-14, 1.0, 1e14, 1e150)


def _require_native_transaction() -> None:
    from core.utils.native_extensions import load_native_metrics

    native = load_native_metrics()
    if native is None or not hasattr(native, "quad_dominant_transaction"):
        pytest.skip("native_metrics.quad_dominant_transaction is not built")


def _signature(result: QuadDominantResult) -> tuple[str, str, str, dict[str, object]]:
    def digest(values: np.ndarray) -> str:
        return hashlib.sha256(values.tobytes()).hexdigest()

    return (
        digest(result.vertices),
        digest(result.triangles),
        digest(result.quads),
        result.diagnostics.model_dump(),
    )


def _oracle_call(
    vertices: np.ndarray,
    triangles: np.ndarray,
    *,
    config: QuadDominantConfig | None = None,
) -> QuadDominantResult:
    with patch("core.utils.native_extensions.load_native_metrics", return_value=None):
        return native_quad_dominant_remesh(vertices, triangles, config=config)


def test_similarity_normalization_is_exact_across_finite_scale_range() -> None:
    _require_native_transaction()
    base_vertices = np.array([[0.0, 0.0, 0.0], [1.0, 0.0, 0.0], [1.0, 1.0, 0.0], [0.0, 1.0, 0.0]])
    triangles = np.array([[0, 1, 2], [0, 2, 3]], dtype=np.int64)

    for scale in _SCALES:
        vertices = base_vertices * scale
        vertices_before = vertices.copy()
        triangles_before = triangles.copy()
        native_results = [native_quad_dominant_remesh(vertices, triangles) for _ in range(3)]
        oracle = _oracle_call(vertices, triangles)

        signatures = [_signature(result) for result in native_results]
        assert signatures == [signatures[0]] * 3
        assert signatures[0] == _signature(oracle)
        assert native_results[0].quads.shape == (1, 4)
        assert native_results[0].triangles.shape == (0, 3)
        np.testing.assert_array_equal(native_results[0].vertices, vertices_before)
        np.testing.assert_array_equal(vertices, vertices_before)
        np.testing.assert_array_equal(triangles, triangles_before)


@pytest.mark.parametrize("scale", (1e-150, 1.0, 1e150))
@pytest.mark.parametrize(
    ("vertices", "triangles", "message"),
    (
        (
            np.array([[0.0, 0.0, 0.0], [1.0, 0.0, 0.0], [2.0, 0.0, 0.0]]),
            np.array([[0, 1, 2]], dtype=np.int64),
            "zero-area triangle",
        ),
        (
            np.array([[0.0, 0.0, 0.0], [1.0, 0.0, 0.0], [0.0, 1.0, 0.0]]),
            np.array([[0, 1, 2], [2, 1, 0]], dtype=np.int64),
            "duplicate triangle",
        ),
        (
            np.array(
                [
                    [0.0, 0.0, 0.0],
                    [1.0, 0.0, 0.0],
                    [0.0, 1.0, 0.0],
                    [0.0, 0.0, 1.0],
                ]
            ),
            np.array([[0, 1, 2], [0, 1, 3]], dtype=np.int64),
            "inconsistent orientation",
        ),
        (
            np.array(
                [
                    [0.0, 0.0, 0.0],
                    [1.0, 0.0, 0.0],
                    [0.0, 1.0, 0.0],
                    [0.0, 0.0, 1.0],
                    [0.0, -1.0, 0.0],
                ]
            ),
            np.array([[0, 1, 2], [1, 0, 3], [0, 1, 4]], dtype=np.int64),
            "non-manifold edge",
        ),
    ),
)
def test_invalid_inputs_remain_fail_closed_at_adverse_scales(
    scale: float,
    vertices: np.ndarray,
    triangles: np.ndarray,
    message: str,
) -> None:
    _require_native_transaction()
    scaled = vertices * scale
    calls: tuple[Callable[[], QuadDominantResult], ...] = (
        lambda: native_quad_dominant_remesh(scaled, triangles),
        lambda: _oracle_call(scaled, triangles),
    )

    errors: list[str] = []
    for call in calls:
        with pytest.raises(ValueError, match=message) as caught:
            call()
        errors.append(str(caught.value))
    assert errors[0] == errors[1]


@pytest.mark.parametrize("scale", (1e-150, 1e150))
def test_feature_wall_and_warpage_gates_are_scale_invariant(scale: float) -> None:
    _require_native_transaction()
    planar = np.array([[0.0, 0.0, 0.0], [1.0, 0.0, 0.0], [1.0, 1.0, 0.0], [0.0, 1.0, 0.0]])
    triangles = np.array([[0, 1, 2], [0, 2, 3]], dtype=np.int64)
    wall_config = QuadDominantConfig(protected_wall_edges=[(0, 2)])
    warped = planar.copy()
    warped[2, 2] = 0.3
    concave = np.array([[0.0, 0.0, 0.0], [1.0, 0.0, 0.0], [0.2, 0.2, 0.0], [0.0, 1.0, 0.0]])
    folded = np.array([[0.0, 0.0, 0.0], [1.0, 0.0, 0.0], [0.0, 1.0, 0.0], [0.0, 0.0, 1.0]])
    folded_triangles = np.array([[0, 1, 2], [1, 0, 3]], dtype=np.int64)

    cases = (
        (planar * scale, triangles, wall_config, "protected_wall_edges", 1),
        (warped * scale, triangles, QuadDominantConfig(), "rejected_quality", 1),
        (concave * scale, triangles, QuadDominantConfig(), "rejected_quality", 1),
        (folded * scale, folded_triangles, QuadDominantConfig(), "protected_feature_edges", 1),
    )
    for vertices, faces, config, metric, expected in cases:
        native = native_quad_dominant_remesh(vertices, faces, config=config)
        oracle = _oracle_call(vertices, faces, config=config)
        assert _signature(native) == _signature(oracle)
        assert len(native.quads) == 0
        assert len(native.triangles) == 2
        assert getattr(native.diagnostics, metric) == expected
