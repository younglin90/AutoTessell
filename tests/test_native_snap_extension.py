"""Parity tests for the optional native surface-snap kernels."""

from __future__ import annotations

from typing import Any

import numpy as np
import pytest

from core.generator.native_hex import snap


def _native_or_skip() -> Any:
    module = snap._load_native_snap()
    if module is None or not hasattr(module, "closest_triangle_candidates"):
        pytest.skip("native_snap extension is not built")
    return module


def _triangles() -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    first = np.array([[0, 0, 0], [0, 0, 1]], dtype=np.float64)
    second = np.array([[1, 0, 0], [1, 0, 1]], dtype=np.float64)
    third = np.array([[0, 1, 0], [0, 1, 1]], dtype=np.float64)
    return first, second, third


def test_native_triangle_candidates_regions_ties_and_sentinels() -> None:
    native = _native_or_skip()
    first, second, third = _triangles()
    points = np.array(
        [
            [0.2, 0.2, 0.3],
            [0.2, 0.2, 0.5],
            [-1.0, -1.0, 0.1],
            [2.0, -0.5, 0.9],
            [0.2, 0.2, 0.4],
        ],
        dtype=np.float64,
    )
    candidates = np.array([[0, 1], [1, 0], [0, 2], [0, 1], [2, 2]], dtype=np.int64)

    best, distances2, valid = native.closest_triangle_candidates(
        points, first, second, third, candidates
    )

    np.testing.assert_allclose(best[0], [0.2, 0.2, 0.0], atol=1e-15)
    np.testing.assert_allclose(best[1], [0.2, 0.2, 1.0], atol=1e-15)
    np.testing.assert_allclose(best[2], [0.0, 0.0, 0.0], atol=1e-15)
    np.testing.assert_allclose(best[3], [1.0, 0.0, 1.0], atol=1e-15)
    np.testing.assert_allclose(distances2[:2], [0.09, 0.25], atol=1e-15)
    np.testing.assert_array_equal(valid, [True, True, True, True, False])
    assert np.isinf(distances2[4])


def test_native_triangle_candidates_negative_index_and_nan_semantics() -> None:
    native = _native_or_skip()
    first, second, third = _triangles()
    points = np.array([[0.2, 0.2, 0.8], [np.nan, 0.0, 0.0]])

    best, distances2, valid = native.closest_triangle_candidates(
        points,
        first,
        second,
        third,
        np.array([[-1], [0]], dtype=np.int64),
    )

    np.testing.assert_allclose(best[0], [0.2, 0.2, 1.0], atol=1e-15)
    assert bool(valid[0]) is True
    assert bool(valid[1]) is False
    assert np.isinf(distances2[1])
    assert np.isnan(best[1, 0])

    with pytest.raises(IndexError):
        native.closest_triangle_candidates(
            points[:1], first, second, third, np.array([[-3]], dtype=np.int64)
        )


def _surface_case() -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    vertices = np.array([[0, 0, 0], [2, 0, 0], [0, 2, 0], [2, 2, 0]], dtype=np.float64)
    faces = np.array([[0, 1, 2], [1, 3, 2]], dtype=np.int64)
    points = np.array(
        [[0.2, 0.2, 0.05], [1.7, 1.7, 0.1], [10, 10, 10]],
        dtype=np.float64,
    )
    return points, vertices, faces


def test_snap_wrapper_native_matches_python_fallback(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    native = _native_or_skip()
    points, vertices, faces = _surface_case()

    monkeypatch.setattr(snap, "_NATIVE_SNAP", native)
    monkeypatch.setattr(snap, "_NATIVE_SNAP_IMPORT_ATTEMPTED", True)
    native_result = snap.snap_hex_boundary_to_surface(points, vertices, faces, target_edge=0.5)

    monkeypatch.setattr(snap, "_NATIVE_SNAP", None)
    python_result = snap.snap_hex_boundary_to_surface(points, vertices, faces, target_edge=0.5)

    np.testing.assert_allclose(native_result[0], python_result[0], atol=1e-14)
    assert native_result[1] == python_result[1]


def test_snap_native_failure_uses_python_fallback(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    points, vertices, faces = _surface_case()

    class FailingNative:
        @staticmethod
        def closest_triangle_candidates(*_args: Any) -> None:
            raise RuntimeError("forced native snap failure")

    monkeypatch.setattr(snap, "_NATIVE_SNAP", FailingNative())
    monkeypatch.setattr(snap, "_NATIVE_SNAP_IMPORT_ATTEMPTED", True)
    failed_result = snap.snap_hex_boundary_to_surface(points, vertices, faces, target_edge=0.5)

    monkeypatch.setattr(snap, "_NATIVE_SNAP", None)
    python_result = snap.snap_hex_boundary_to_surface(points, vertices, faces, target_edge=0.5)

    np.testing.assert_allclose(failed_result[0], python_result[0], atol=0.0)
    assert failed_result[1] == python_result[1]


def test_iterative_snap_native_matches_python_fallback(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    native = _native_or_skip()
    points, vertices, faces = _surface_case()

    monkeypatch.setattr(snap, "_NATIVE_SNAP", native)
    monkeypatch.setattr(snap, "_NATIVE_SNAP_IMPORT_ATTEMPTED", True)
    native_result = snap.snap_to_surface_iterative(
        points,
        vertices,
        faces,
        target_edge=0.5,
        n_iter=3,
        relax=0.5,
        smooth_after_snap=False,
    )

    monkeypatch.setattr(snap, "_NATIVE_SNAP", None)
    python_result = snap.snap_to_surface_iterative(
        points,
        vertices,
        faces,
        target_edge=0.5,
        n_iter=3,
        relax=0.5,
        smooth_after_snap=False,
    )

    np.testing.assert_allclose(native_result[0], python_result[0], atol=1e-14)
    assert native_result[1] == python_result[1]


def test_native_segment_candidates_regions_ties_and_sentinels() -> None:
    native = _native_or_skip()
    first = np.array([[0, 0, 0], [0, 0, 1], [2, 2, 2]], dtype=np.float64)
    second = np.array([[1, 0, 0], [0, 1, 1], [2, 2, 2]], dtype=np.float64)
    points = np.array(
        [
            [0.25, 0.5, 0.0],
            [0.0, 0.5, 0.5],
            [3.0, 2.0, 2.0],
            [0.0, 0.0, 0.0],
            [2.1, 2.0, 2.0],
            [np.nan, 0.0, 0.0],
        ],
        dtype=np.float64,
    )
    candidates = np.array(
        [[0, 1], [1, 0], [2, 3], [3, 3], [-1, 3], [0, 1]],
        dtype=np.int64,
    )

    best, distances, indices, valid = native.closest_segment_candidates(
        points, first, second, candidates
    )

    np.testing.assert_allclose(best[0], [0.25, 0.0, 0.0], atol=1e-15)
    np.testing.assert_allclose(best[1], [0.0, 0.5, 1.0], atol=1e-15)
    np.testing.assert_allclose(best[2], [2.0, 2.0, 2.0], atol=1e-15)
    np.testing.assert_allclose(best[4], [2.0, 2.0, 2.0], atol=1e-15)
    np.testing.assert_allclose(distances[[0, 1, 2, 4]], [0.5, 0.5, 1.0, 0.1])
    np.testing.assert_array_equal(indices, [0, 1, 2, -1, 2, -1])
    np.testing.assert_array_equal(valid, [True, True, True, False, True, False])

    with pytest.raises(IndexError):
        native.closest_segment_candidates(
            points[:1], first, second, np.array([[-4]], dtype=np.int64)
        )


def _feature_snap_case() -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    axis = np.linspace(0.04, 0.96, 5)
    grid = np.stack(np.meshgrid(axis, axis, axis, indexing="ij"), axis=-1)
    points = grid.reshape(-1, 3)
    ids = np.arange(points.shape[0], dtype=np.int64).reshape(5, 5, 5)
    cells: list[list[int]] = []
    for i in range(4):
        for j in range(4):
            for k in range(4):
                cells.append(
                    [
                        ids[i, j, k],
                        ids[i + 1, j, k],
                        ids[i + 1, j + 1, k],
                        ids[i, j + 1, k],
                        ids[i, j, k + 1],
                        ids[i + 1, j, k + 1],
                        ids[i + 1, j + 1, k + 1],
                        ids[i, j + 1, k + 1],
                    ]
                )
    surface = np.array(
        [
            [0, 0, 0],
            [1, 0, 0],
            [1, 1, 0],
            [0, 1, 0],
            [0, 0, 1],
            [1, 0, 1],
            [1, 1, 1],
            [0, 1, 1],
        ],
        dtype=np.float64,
    )
    faces = np.array(
        [
            [0, 1, 2],
            [0, 2, 3],
            [4, 6, 5],
            [4, 7, 6],
            [0, 4, 5],
            [0, 5, 1],
            [3, 2, 6],
            [3, 6, 7],
            [0, 3, 7],
            [0, 7, 4],
            [1, 5, 6],
            [1, 6, 2],
        ],
        dtype=np.int64,
    )
    return points, np.asarray(cells, dtype=np.int64), surface, faces


def test_feature_segment_snap_native_matches_python_fallback(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    native = _native_or_skip()
    assert hasattr(native, "closest_segment_candidates")
    points, cells, surface, faces = _feature_snap_case()
    monkeypatch.delenv("AUTO_TESSELL_WWW7_OFF", raising=False)

    monkeypatch.setattr(snap, "_NATIVE_SNAP", native)
    monkeypatch.setattr(snap, "_NATIVE_SNAP_IMPORT_ATTEMPTED", True)
    native_result = snap.snap_to_feature_edges(
        points, cells, surface, faces, max_dist=0.2, top_k=200
    )

    monkeypatch.setattr(snap, "_NATIVE_SNAP", None)
    python_result = snap.snap_to_feature_edges(
        points, cells, surface, faces, max_dist=0.2, top_k=200
    )

    np.testing.assert_allclose(native_result[0], python_result[0], atol=1e-14)
    assert native_result[1] == python_result[1]
