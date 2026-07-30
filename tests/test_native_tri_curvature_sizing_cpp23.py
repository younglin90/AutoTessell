"""C++23 parity and fail-closed contracts for native-tri curvature sizing."""

from __future__ import annotations

import hashlib
from pathlib import Path
from types import SimpleNamespace
from typing import Any
from unittest.mock import patch

import numpy as np
import pytest
import trimesh

from core.preprocessor.native_tri.operator_loop import (
    OperatorTransaction,
    _estimate_curvature_sizing_python,
    estimate_curvature_sizing,
)


def _native_curvature_kernel() -> Any:
    from core.utils.native_extensions import load_native_metrics

    native = load_native_metrics()
    if native is None or not hasattr(native, "estimate_triangle_curvature_sizing"):
        pytest.skip("native_metrics.estimate_triangle_curvature_sizing is not built")
    return native


def _sha256(values: np.ndarray) -> str:
    return hashlib.sha256(values.tobytes()).hexdigest()


@pytest.mark.parametrize(
    ("vertices", "faces"),
    [
        (
            np.array(
                [
                    [0.0, 0.0, 0.0],
                    [1.0, 0.0, 0.0],
                    [0.0, 2.0, 0.0],
                    [4.0, 0.0, 0.0],
                    [6.0, 0.0, 0.0],
                    [4.0, 3.0, 0.0],
                ],
                dtype=np.float64,
            ),
            np.array([[0, 1, 2], [3, 4, 5]], dtype=np.int64),
        ),
        (
            np.array(
                [
                    [0.0, 0.0, 0.0],
                    [1.0, 0.0, 0.0],
                    [0.0, 1.0, 0.0],
                    [0.0, 0.0, 1.0],
                    [0.0, -1.0, 0.0],
                ],
                dtype=np.float64,
            ),
            # Three incident faces freeze existing non-manifold-edge semantics:
            # use the maximum pairwise turning angle; do not silently repair.
            np.array([[0, 1, 2], [1, 0, 3], [0, 1, 4]], dtype=np.int64),
        ),
        (
            np.array(
                [[0.0, 0.0, 0.0], [1.0, 0.0, 0.0], [2.0, 0.0, 0.0]],
                dtype=np.float64,
            ),
            # Positive edges but zero face area must keep the flat upper fallback.
            np.array([[0, 1, 2]], dtype=np.int64),
        ),
        (
            np.array(
                [[0.0, 0.0, 0.0], [1.0, 0.0, 0.0], [0.0, 1.0, 0.0]],
                dtype=np.float64,
            ),
            # Duplicate faces are preserved by this report-only sizing kernel.
            np.array([[0, 1, 2], [0, 1, 2]], dtype=np.int64),
        ),
    ],
)
def test_native_curvature_matches_python_branch_semantics(
    vertices: np.ndarray,
    faces: np.ndarray,
) -> None:
    _native_curvature_kernel()
    keyword_arguments = {"min_length": 0.05, "max_length": 4.0}

    expected = _estimate_curvature_sizing_python(vertices, faces, 0.01, **keyword_arguments)
    actual = estimate_curvature_sizing(vertices, faces, 0.01, **keyword_arguments)

    np.testing.assert_allclose(actual, expected, rtol=2e-14, atol=2e-14)
    np.testing.assert_array_equal(actual == 0.05, expected == 0.05)
    np.testing.assert_array_equal(actual == 4.0, expected == 4.0)


def test_native_curvature_is_deterministic_and_does_not_mutate_sources(
    tmp_path: Path,
) -> None:
    _native_curvature_kernel()
    mesh = trimesh.creation.icosphere(subdivisions=2)
    vertices = np.ascontiguousarray(mesh.vertices, dtype=np.float64)
    faces = np.ascontiguousarray(mesh.faces, dtype=np.int64)
    vertex_hash = _sha256(vertices)
    face_hash = _sha256(faces)

    outputs = [estimate_curvature_sizing(vertices, faces, 0.001) for _ in range(3)]

    assert len({_sha256(output) for output in outputs}) == 1
    assert _sha256(vertices) == vertex_hash
    assert _sha256(faces) == face_hash
    assert not list(tmp_path.iterdir())


def test_native_curvature_direct_abi_is_strict_and_fail_closed() -> None:
    native = _native_curvature_kernel()
    vertices = np.array(
        [[0.0, 0.0, 0.0], [1.0, 0.0, 0.0], [0.0, 1.0, 0.0]],
        dtype=np.float64,
    )
    faces = np.array([[0, 1, 2]], dtype=np.int64)

    with pytest.raises(ValueError, match="C-contiguous float64"):
        native.estimate_triangle_curvature_sizing(
            vertices.astype(np.float32), faces, 0.01, None, None
        )
    with pytest.raises(ValueError, match="C-contiguous int64"):
        native.estimate_triangle_curvature_sizing(
            vertices, faces.astype(np.int32), 0.01, None, None
        )
    with pytest.raises((TypeError, ValueError)):
        native.estimate_triangle_curvature_sizing(vertices[:, ::-1], faces, 0.01, None, None)
    with pytest.raises(ValueError, match="invalid vertex index"):
        native.estimate_triangle_curvature_sizing(
            vertices, np.array([[0, 1, 3]], dtype=np.int64), 0.01, None, None
        )
    with pytest.raises(ValueError, match="no positive-length edge"):
        native.estimate_triangle_curvature_sizing(
            vertices[:1], np.array([[0, 0, 0]], dtype=np.int64), 0.01, None, None
        )


def test_curvature_wrapper_rejects_malformed_native_output() -> None:
    vertices = np.array(
        [[0.0, 0.0, 0.0], [1.0, 0.0, 0.0], [0.0, 1.0, 0.0]],
        dtype=np.float64,
    )
    faces = np.array([[0, 1, 2]], dtype=np.int64)

    malformed = SimpleNamespace(
        estimate_triangle_curvature_sizing=lambda *_args: {
            "lengths": np.full(3, np.nan),
            "reference_length": 1.0,
            "minimum_length": 0.25,
            "maximum_length": 2.0,
        }
    )
    with patch("core.utils.native_extensions.load_native_metrics", return_value=malformed):
        with pytest.raises(RuntimeError, match="invalid lengths"):
            estimate_curvature_sizing(vertices, faces, 0.01)


def test_curvature_extension_absent_fallback_is_exact() -> None:
    vertices = np.array(
        [[0.0, 0.0, 0.0], [1.0, 0.0, 0.0], [0.0, 1.0, 0.2]],
        dtype=np.float64,
    )
    faces = np.array([[0, 1, 2]], dtype=np.int64)
    expected = _estimate_curvature_sizing_python(vertices, faces, 0.01)

    with patch("core.utils.native_extensions.load_native_metrics", return_value=None):
        actual = estimate_curvature_sizing(vertices, faces, 0.01)

    np.testing.assert_array_equal(actual, expected)


def test_curvature_native_path_preserves_frozen_cube_transaction_hashes() -> None:
    _native_curvature_kernel()
    mesh = trimesh.creation.box()
    vertices = np.ascontiguousarray(mesh.vertices, dtype=np.float64)
    faces = np.ascontiguousarray(mesh.faces, dtype=np.int64)

    with patch("core.utils.native_extensions.load_native_metrics", return_value=None):
        reference = OperatorTransaction(vertices, faces, curvature_epsilon=0.02)
        reference_reports = reference.run_one_round(smooth=False)
    native = OperatorTransaction(vertices, faces, curvature_epsilon=0.02)
    native_reports = native.run_one_round(smooth=False)

    native_signature = tuple(
        (report.operator, report.accepted, report.reason, report.vertex_index)
        for report in native_reports
    )
    reference_signature = tuple(
        (report.operator, report.accepted, report.reason, report.vertex_index)
        for report in reference_reports
    )
    assert native_signature == reference_signature
    np.testing.assert_array_equal(native.state.vertices, reference.state.vertices)
    np.testing.assert_array_equal(native.state.faces, reference.state.faces)
    assert _sha256(native.state.vertices) == (
        "95d76c3638af9a972ba7fe272745aa6b108735c913d9f32800daefd0e06b4036"
    )
    assert _sha256(native.state.faces) == (
        "35f0279bb703ab37558344968699fde685c59e016d8d8614b4166d5cf3159c2f"
    )
    assert _sha256(vertices) == ("6040f86a7df7863ef75c589fa6f4f6dc2696f9a8634d001b85dbd62103cc6e1f")
    assert _sha256(faces) == ("45b42c3653d916570ed16014f8a91f585c5fc9a93c1467f279657354544c0aa7")
