"""C++23 parity and fail-closed contracts for the frozen-state flip filter."""

from __future__ import annotations

import hashlib
from pathlib import Path
from types import SimpleNamespace
from typing import Any
from unittest.mock import patch

import numpy as np
import pytest

from core.analyzer.readers import read_stl
from core.preprocessor.native_tri.operator_loop import OperatorTransaction


def _native_flip_filter() -> Any:
    from core.utils.native_extensions import load_native_metrics

    native = load_native_metrics()
    if native is None or not hasattr(native, "triangle_flip_candidate_mask"):
        pytest.skip("native_metrics.triangle_flip_candidate_mask is not built")
    return native


def _fixture(name: str) -> tuple[np.ndarray, np.ndarray, float]:
    root = Path(__file__).resolve().parent
    mesh = read_stl(str(root / "benchmarks" / name))
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


def _sha256(values: np.ndarray) -> str:
    return hashlib.sha256(values.tobytes()).hexdigest()


def _signature(
    transaction: OperatorTransaction,
    reports: tuple[Any, ...],
) -> tuple[Any, ...]:
    return (
        tuple(
            (report.operator, report.accepted, report.reason, report.vertex_index)
            for report in reports
        ),
        _sha256(transaction.state.vertices),
        _sha256(transaction.state.faces),
    )


class _WithoutFlipFilter:
    def __init__(self, native: Any) -> None:
        self._native = native

    def __getattr__(self, name: str) -> Any:
        if name == "triangle_flip_candidate_mask":
            raise AttributeError(name)
        return getattr(self._native, name)


@pytest.mark.parametrize("name", ["cube.stl", "sphere.stl", "cylinder.stl"])
def test_native_flip_mask_matches_scalar_oracle_on_frozen_state(name: str) -> None:
    native = _native_flip_filter()
    vertices, faces, _ = _fixture(name)
    transaction = OperatorTransaction(vertices, faces)
    edges = transaction._unique_edges()
    expected = np.fromiter(
        (transaction.should_flip_edge(edge) for edge in edges),
        dtype=np.bool_,
        count=len(edges),
    )

    with patch("core.utils.native_extensions.load_native_metrics", return_value=native):
        actual = transaction._flip_candidate_mask(edges)

    np.testing.assert_array_equal(actual, expected)
    np.testing.assert_array_equal(transaction.state.vertices, vertices)
    np.testing.assert_array_equal(transaction.state.faces, faces)


def test_native_filter_does_not_build_per_edge_mesh_copies() -> None:
    native = _native_flip_filter()
    vertices, faces, _ = _fixture("cylinder.stl")
    transaction = OperatorTransaction(vertices, faces)
    edges = transaction._unique_edges()

    with (
        patch("core.utils.native_extensions.load_native_metrics", return_value=native),
        patch.object(
            transaction,
            "_build_flip_candidate",
            side_effect=AssertionError("per-edge full-mesh candidate allocation"),
        ),
    ):
        mask = transaction._flip_candidate_mask(edges)

    assert mask.shape == (len(edges),)


def test_existing_diagonal_remains_rejected_by_transaction_gate() -> None:
    native = _native_flip_filter()
    vertices = np.array(
        [
            [0.0012301533574825742, 0.2987455375084699, 0.0],
            [-0.2741378553622176, -0.8905918387572742, 0.0],
            [-0.45467078517172255, -0.9916465549964624, 0.0],
            [0.060143602597438485, 1.3402152455545335, 0.0],
            [-0.49220651855132963, -0.6204748998199404, 0.0],
        ],
        dtype=np.float64,
    )
    faces = np.array([[0, 1, 2], [1, 0, 3], [2, 3, 4]], dtype=np.int64)
    transaction = OperatorTransaction(vertices, faces)
    assert transaction.should_flip_edge((0, 1))

    with patch("core.utils.native_extensions.load_native_metrics", return_value=native):
        mask = transaction._flip_candidate_mask(((0, 1),))

    assert mask.tolist() == [True]
    report = transaction.flip_edge((0, 1))
    assert not report.accepted
    assert report.reason == "link_condition_failed"
    np.testing.assert_array_equal(transaction.state.vertices, vertices)
    np.testing.assert_array_equal(transaction.state.faces, faces)


def test_native_flip_filter_rejects_malformed_input_abi() -> None:
    native = _native_flip_filter()
    vertices, faces, _ = _fixture("cube.stl")
    edges = np.array([[0, 1]], dtype=np.int64)

    with pytest.raises((TypeError, ValueError)):
        native.triangle_flip_candidate_mask(
            vertices.astype(np.float32),
            faces,
            edges,
        )
    with pytest.raises((TypeError, ValueError)):
        native.triangle_flip_candidate_mask(vertices, faces[:, ::-1], edges)
    with pytest.raises((TypeError, ValueError)):
        native.triangle_flip_candidate_mask(vertices, faces, edges.astype(np.int32))


def test_python_wrapper_rejects_malformed_native_output() -> None:
    vertices, faces, _ = _fixture("cube.stl")
    transaction = OperatorTransaction(vertices, faces)
    edges = transaction._unique_edges()
    malformed = SimpleNamespace(
        triangle_flip_candidate_mask=lambda *_: np.ones((len(edges), 1), dtype=np.bool_),
    )

    with (
        patch(
            "core.utils.native_extensions.load_native_metrics",
            return_value=malformed,
        ),
        pytest.raises(RuntimeError, match="invalid mask"),
    ):
        transaction._flip_candidate_mask(edges)


@pytest.mark.parametrize("name", ["cube.stl", "sphere.stl", "cylinder.stl"])
def test_native_flip_filter_preserves_full_round_signature(name: str) -> None:
    native = _native_flip_filter()
    vertices, faces, target = _fixture(name)
    signatures: list[tuple[Any, ...]] = []
    for module in (_WithoutFlipFilter(native), native, native, native):
        with patch(
            "core.utils.native_extensions.load_native_metrics",
            return_value=module,
        ):
            transaction = OperatorTransaction(
                vertices,
                faces,
                target_edge_length=target,
            )
            reports = transaction.run_one_round(
                target_edge_length=target,
                smooth=False,
            )
        signatures.append(_signature(transaction, reports))

    assert signatures[1:] == [signatures[0]] * 3
