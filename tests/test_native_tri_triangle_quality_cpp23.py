"""C++23 parity and fail-closed contracts for local triangle quality."""

from __future__ import annotations

import hashlib
from pathlib import Path
from types import SimpleNamespace
from typing import Any
from unittest.mock import patch

import numpy as np
import pytest

from core.analyzer.readers import read_stl
from core.preprocessor.native_tri.operator_loop import (
    OperatorTransaction,
    _triangle_quality_batch,
    _triangle_quality_batch_python,
)


def _native_quality_kernel() -> Any:
    from core.utils.native_extensions import load_native_metrics

    native = load_native_metrics()
    if native is None or not hasattr(native, "triangle_quality_batch"):
        pytest.skip("native_metrics.triangle_quality_batch is not built")
    return native


def _sha256(values: np.ndarray) -> str:
    return hashlib.sha256(values.tobytes()).hexdigest()


def _cylinder_input() -> tuple[np.ndarray, np.ndarray, float]:
    root = Path(__file__).resolve().parents[1]
    mesh = read_stl(str(root / "tests/benchmarks/cylinder.stl"))
    vertices = np.ascontiguousarray(mesh.vertices, dtype=np.float64)
    faces = np.ascontiguousarray(mesh.faces, dtype=np.int64)
    lengths = np.concatenate(
        [
            np.linalg.norm(
                vertices[faces[:, index]] - vertices[faces[:, (index + 1) % 3]],
                axis=1,
            )
            for index in range(3)
        ]
    )
    return vertices, faces, float(np.median(lengths[lengths > 0.0]))


def _report_signature(transaction: OperatorTransaction, reports: list[Any]) -> tuple[Any, ...]:
    return (
        tuple(
            (report.operator, report.accepted, report.reason, report.vertex_index)
            for report in reports
        ),
        _sha256(transaction.state.vertices),
        _sha256(transaction.state.faces),
    )


def test_native_triangle_quality_matches_scalar_oracle() -> None:
    _native_quality_kernel()
    triangles = np.array(
        [
            [[0.0, 0.0, 0.0], [1.0, 0.0, 0.0], [0.5, np.sqrt(0.75), 0.0]],
            [[0.0, 0.0, 0.0], [2.0, 0.0, 0.0], [0.0, 1.0, 0.0]],
            [[1.0, 2.0, 3.0], [1.0, 2.0, 3.0], [2.0, 2.0, 3.0]],
            [[1e40, 0.0, 0.0], [0.0, 1e40, 0.0], [0.0, 0.0, 1e40]],
        ],
        dtype=np.float64,
    )

    expected = _triangle_quality_batch_python(triangles)
    actual = _triangle_quality_batch(triangles)

    np.testing.assert_allclose(actual, expected, rtol=2e-15, atol=2e-15)
    assert actual[0] == pytest.approx(1.0, abs=2e-15)
    assert actual[2] == 0.0


def test_native_triangle_quality_direct_abi_is_strict_and_sources_are_immutable() -> None:
    native = _native_quality_kernel()
    triangles = np.array(
        [[[0.0, 0.0, 0.0], [1.0, 0.0, 0.0], [0.0, 1.0, 0.0]]],
        dtype=np.float64,
    )
    source_hash = _sha256(triangles)

    outputs = [native.triangle_quality_batch(triangles) for _ in range(3)]

    assert len({_sha256(output) for output in outputs}) == 1
    assert _sha256(triangles) == source_hash
    with pytest.raises((TypeError, ValueError), match="C-contiguous float64"):
        native.triangle_quality_batch(triangles.astype(np.float32))
    with pytest.raises((TypeError, ValueError)):
        native.triangle_quality_batch(triangles[:, :, ::-1])
    with pytest.raises((TypeError, ValueError), match="shape"):
        native.triangle_quality_batch(triangles.reshape(1, 9))


@pytest.mark.parametrize(
    "quality",
    [
        [0.5],
        np.array([0.5], dtype=np.float32),
        np.array([0.5, 0.4], dtype=np.float64),
        np.array([np.nan], dtype=np.float64),
        np.array([-0.1], dtype=np.float64),
        np.array([1.1], dtype=np.float64),
    ],
)
def test_triangle_quality_wrapper_rejects_malformed_native_output(quality: object) -> None:
    triangles = np.array(
        [[[0.0, 0.0, 0.0], [1.0, 0.0, 0.0], [0.0, 1.0, 0.0]]],
        dtype=np.float64,
    )
    malformed = SimpleNamespace(triangle_quality_batch=lambda _triangles: quality)

    with patch("core.utils.native_extensions.load_native_metrics", return_value=malformed):
        with pytest.raises(RuntimeError, match="invalid quality"):
            _triangle_quality_batch(triangles)


def test_triangle_quality_extension_absent_fallback_is_exact() -> None:
    triangles = np.array(
        [
            [[0.0, 0.0, 0.0], [1.0, 0.0, 0.0], [0.2, 0.9, 0.1]],
            [[0.0, 0.0, 0.0], [3.0, 0.0, 0.0], [0.0, 0.1, 0.0]],
        ],
        dtype=np.float64,
    )
    expected = _triangle_quality_batch_python(triangles)

    with patch("core.utils.native_extensions.load_native_metrics", return_value=None):
        actual = _triangle_quality_batch(triangles)

    np.testing.assert_array_equal(actual, expected)


def test_native_quality_preserves_cylinder_reports_and_hashes_three_times() -> None:
    _native_quality_kernel()
    vertices, faces, target = _cylinder_input()
    vertex_hash = _sha256(vertices)
    face_hash = _sha256(faces)

    with patch("core.utils.native_extensions.load_native_metrics", return_value=None):
        reference = OperatorTransaction(vertices, faces, target_edge_length=target)
        reference_reports = reference.run_one_round(target_edge_length=target, smooth=False)
    expected = _report_signature(reference, reference_reports)

    signatures: list[tuple[Any, ...]] = []
    for _ in range(3):
        transaction = OperatorTransaction(vertices, faces, target_edge_length=target)
        reports = transaction.run_one_round(target_edge_length=target, smooth=False)
        signatures.append(_report_signature(transaction, reports))

    assert signatures == [expected, expected, expected]
    assert len(reference_reports) == 222
    assert sum(report.accepted for report in reference_reports) == 204
    assert expected[1] == "3339268edf9671568a319d040aa2ea2fdd75d6ba6a7b24958cbf391f4f9df47c"
    assert expected[2] == "ac78dcf565f5596bab24065072dee990059155498d17e8e589eb2b3fe5cc9d37"
    assert _sha256(vertices) == vertex_hash
    assert _sha256(faces) == face_hash
