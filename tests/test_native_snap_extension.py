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


def _feature_edges_with_backend(
    monkeypatch: pytest.MonkeyPatch,
    backend: Any | None,
    vertices: np.ndarray,
    faces: np.ndarray,
    angle: float,
) -> tuple[np.ndarray, np.ndarray]:
    monkeypatch.setattr(snap, "_NATIVE_SNAP", backend)
    monkeypatch.setattr(snap, "_NATIVE_SNAP_IMPORT_ATTEMPTED", True)
    segments = snap._extract_feature_edge_segments(vertices, faces, angle)
    weights = np.asarray(getattr(segments, "_seg_weight"), dtype=np.float64)
    return np.asarray(segments), weights


def test_native_feature_edges_cube_exact_fallback_parity_and_determinism(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    native = _native_or_skip()
    assert hasattr(native, "extract_feature_edges")
    _, _, surface, faces = _feature_snap_case()

    expected_segments, expected_weights = _feature_edges_with_backend(
        monkeypatch, None, surface, faces, 30.0
    )
    assert expected_segments.shape == (12, 2, 3)
    np.testing.assert_array_equal(expected_weights, np.full(12, 2.0))

    repeats = [
        _feature_edges_with_backend(monkeypatch, native, surface, faces, 30.0) for _ in range(3)
    ]
    for actual_segments, actual_weights in repeats:
        np.testing.assert_array_equal(actual_segments, expected_segments)
        np.testing.assert_array_equal(actual_weights, expected_weights)
    assert repeats[0][0].tobytes() == repeats[1][0].tobytes() == repeats[2][0].tobytes()
    assert repeats[0][1].tobytes() == repeats[1][1].tobytes() == repeats[2][1].tobytes()


def test_native_feature_edges_threshold_boundary_and_empty_parity(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    native = _native_or_skip()
    vertices = np.array(
        [[0, 0, 0], [1, 0, 0], [0, 1, 0], [0, 0.5, np.sqrt(3.0) / 2.0]],
        dtype=np.float64,
    )
    faces = np.array([[0, 1, 2], [0, 1, 3]], dtype=np.int64)

    for angle in (59.9, 60.1):
        expected = _feature_edges_with_backend(monkeypatch, None, vertices, faces, angle)
        actual = _feature_edges_with_backend(monkeypatch, native, vertices, faces, angle)
        np.testing.assert_array_equal(actual[0], expected[0])
        np.testing.assert_allclose(actual[1], expected[1], rtol=0.0, atol=2e-16)

    reversed_faces = faces.copy()
    reversed_faces[1] = reversed_faces[1, ::-1]
    expected = _feature_edges_with_backend(monkeypatch, None, vertices, reversed_faces, 90.0)
    actual = _feature_edges_with_backend(monkeypatch, native, vertices, reversed_faces, 90.0)
    np.testing.assert_array_equal(actual[0], expected[0])
    np.testing.assert_array_equal(actual[1], expected[1])

    disconnected_vertices = np.vstack((vertices[:3], vertices[:3] + [3.0, 0.0, 0.0]))
    disconnected_faces = np.array([[0, 1, 2], [3, 4, 5]], dtype=np.int64)
    expected = _feature_edges_with_backend(
        monkeypatch, None, disconnected_vertices, disconnected_faces, 30.0
    )
    actual = _feature_edges_with_backend(
        monkeypatch, native, disconnected_vertices, disconnected_faces, 30.0
    )
    np.testing.assert_array_equal(actual[0], expected[0])
    np.testing.assert_array_equal(actual[1], expected[1])

    empty_vertices = np.empty((0, 3), dtype=np.float64)
    empty_faces = np.empty((0, 3), dtype=np.int64)
    segments, weights = native.extract_feature_edges(empty_vertices, empty_faces, 30.0)
    assert segments.shape == (0, 2, 3)
    assert weights.shape == (0,)


def test_native_feature_edges_preserves_zero_area_and_nonmanifold_policy(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    native = _native_or_skip()

    zero_area_vertices = np.array([[0, 0, 0], [1, 0, 0], [2, 0, 0]], dtype=np.float64)
    zero_area_faces = np.array([[0, 1, 2]], dtype=np.int64)
    expected = _feature_edges_with_backend(
        monkeypatch, None, zero_area_vertices, zero_area_faces, 30.0
    )
    actual = _feature_edges_with_backend(
        monkeypatch, native, zero_area_vertices, zero_area_faces, 30.0
    )
    np.testing.assert_array_equal(actual[0], expected[0])
    np.testing.assert_array_equal(actual[1], expected[1])

    duplicate_faces = np.repeat(zero_area_faces, 2, axis=0)
    expected = _feature_edges_with_backend(
        monkeypatch, None, zero_area_vertices, duplicate_faces, 30.0
    )
    actual = _feature_edges_with_backend(
        monkeypatch, native, zero_area_vertices, duplicate_faces, 30.0
    )
    np.testing.assert_array_equal(actual[0], expected[0])
    np.testing.assert_array_equal(actual[1], expected[1])

    nonmanifold_vertices = np.array(
        [[0, 0, 0], [1, 0, 0], [0, 1, 0], [0, -1, 0], [0, 0, 1]],
        dtype=np.float64,
    )
    nonmanifold_faces = np.array([[0, 1, 2], [1, 0, 3], [0, 1, 4]], dtype=np.int64)
    expected = _feature_edges_with_backend(
        monkeypatch, None, nonmanifold_vertices, nonmanifold_faces, 30.0
    )
    actual = _feature_edges_with_backend(
        monkeypatch, native, nonmanifold_vertices, nonmanifold_faces, 30.0
    )
    np.testing.assert_array_equal(actual[0], expected[0])
    np.testing.assert_array_equal(actual[1], expected[1])
    shared_edge = nonmanifold_vertices[[0, 1]]
    assert not np.any(np.all(actual[0] == shared_edge, axis=(1, 2)))


def test_native_feature_edges_strict_abi_rejects_invalid_input() -> None:
    native = _native_or_skip()
    assert hasattr(native, "extract_feature_edges")
    vertices = np.array([[0, 0, 0], [1, 0, 0], [0, 1, 0]], dtype=np.float64)
    faces = np.array([[0, 1, 2]], dtype=np.int64)

    with pytest.raises(TypeError):
        native.extract_feature_edges(vertices.astype(np.float32), faces, 30.0)
    with pytest.raises(TypeError):
        native.extract_feature_edges(vertices, faces.astype(np.int32), 30.0)
    with pytest.raises(TypeError):
        native.extract_feature_edges(vertices[:, ::-1], faces, 30.0)
    with pytest.raises(TypeError):
        strided_faces = np.array([[0, 9, 1, 9, 2, 9]], dtype=np.int64)[:, ::2]
        native.extract_feature_edges(vertices, strided_faces, 30.0)
    with pytest.raises(ValueError, match="finite"):
        invalid_vertices = vertices.copy()
        invalid_vertices[0, 0] = np.nan
        native.extract_feature_edges(invalid_vertices, faces, 30.0)
    with pytest.raises(ValueError, match="finite"):
        native.extract_feature_edges(vertices, faces, np.inf)
    with pytest.raises(IndexError):
        native.extract_feature_edges(vertices, np.array([[-1, 1, 2]], dtype=np.int64), 30.0)
    with pytest.raises(IndexError):
        native.extract_feature_edges(vertices, np.array([[0, 1, 3]], dtype=np.int64), 30.0)


def test_feature_edge_wrapper_propagates_native_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    vertices = np.array([[0, 0, 0], [1, 0, 0], [0, 1, 0]], dtype=np.float64)
    faces = np.array([[0, 1, 2]], dtype=np.int64)

    class RaisingNative:
        @staticmethod
        def extract_feature_edges(*_args: Any) -> None:
            raise RuntimeError("forced feature-edge failure")

    monkeypatch.setattr(snap, "_NATIVE_SNAP", RaisingNative())
    monkeypatch.setattr(snap, "_NATIVE_SNAP_IMPORT_ATTEMPTED", True)
    with pytest.raises(RuntimeError, match="forced feature-edge failure"):
        snap._extract_feature_edge_segments(vertices, faces, 30.0)


def test_feature_edge_wrapper_rejects_malformed_native_output(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    vertices = np.array([[0, 0, 0], [1, 0, 0], [0, 1, 0]], dtype=np.float64)
    faces = np.array([[0, 1, 2]], dtype=np.int64)

    class MalformedNative:
        @staticmethod
        def extract_feature_edges(*_args: Any) -> tuple[np.ndarray, np.ndarray]:
            return np.zeros((1, 3), dtype=np.float64), np.zeros(1, dtype=np.float64)

    monkeypatch.setattr(snap, "_NATIVE_SNAP", MalformedNative())
    monkeypatch.setattr(snap, "_NATIVE_SNAP_IMPORT_ATTEMPTED", True)
    with pytest.raises(ValueError, match="invalid segments"):
        snap._extract_feature_edge_segments(vertices, faces, 30.0)


@pytest.mark.parametrize(
    ("segments", "weights", "error", "match"),
    [
        ([[[0.0, 0.0, 0.0], [1.0, 0.0, 0.0]]], np.ones(1), TypeError, "NumPy"),
        (np.zeros((1, 2, 3), dtype=np.float32), np.ones(1), TypeError, "float64"),
        (
            np.zeros((1, 3, 2), dtype=np.float64).transpose(0, 2, 1),
            np.ones(1),
            TypeError,
            "C-contiguous",
        ),
        (
            np.full((1, 2, 3), np.nan, dtype=np.float64),
            np.ones(1),
            ValueError,
            "non-finite",
        ),
        (np.zeros((1, 2, 3)), [1.0], TypeError, "NumPy"),
        (np.zeros((1, 2, 3)), np.ones(1, dtype=np.float32), TypeError, "float64"),
        (
            np.zeros((2, 2, 3)),
            np.ones(4, dtype=np.float64)[::2],
            TypeError,
            "C-contiguous",
        ),
        (
            np.zeros((1, 2, 3)),
            np.array([np.inf], dtype=np.float64),
            ValueError,
            "non-finite",
        ),
    ],
    ids=(
        "segments-list",
        "segments-dtype",
        "segments-layout",
        "segments-finite",
        "weights-list",
        "weights-dtype",
        "weights-layout",
        "weights-finite",
    ),
)
def test_feature_edge_wrapper_strict_output_abi(
    monkeypatch: pytest.MonkeyPatch,
    segments: Any,
    weights: Any,
    error: type[Exception],
    match: str,
) -> None:
    vertices = np.array([[0, 0, 0], [1, 0, 0], [0, 1, 0]], dtype=np.float64)
    faces = np.array([[0, 1, 2]], dtype=np.int64)

    class FakeNative:
        @staticmethod
        def extract_feature_edges(*_args: Any) -> tuple[Any, Any]:
            return segments, weights

    monkeypatch.setattr(snap, "_NATIVE_SNAP", FakeNative())
    monkeypatch.setattr(snap, "_NATIVE_SNAP_IMPORT_ATTEMPTED", True)
    with pytest.raises(error, match=match):
        snap._extract_feature_edge_segments(vertices, faces, 30.0)
