"""Focused contracts for native quad-dominant surface conversion."""

from __future__ import annotations

from collections.abc import Callable
from types import SimpleNamespace
from typing import Any

import numpy as np
import pytest
import trimesh

from core.preprocessor.native_remesh import (
    QuadDominantConfig,
    native_quad_dominant_remesh,
)
from core.preprocessor.native_remesh.quad_dominant import (
    _prepare_quad_pairs,
    _prepare_quad_pairs_python,
    _quad_quality,
    _select_quad_pairs,
    _select_quad_pairs_python,
)


def _native_quad_selector():
    from core.utils.native_extensions import load_native_metrics

    native = load_native_metrics()
    if native is None or not hasattr(native, "select_quad_pairs"):
        pytest.skip("native_metrics.select_quad_pairs is not built")
    return native


def _native_quad_preparer():
    native = _native_quad_selector()
    if not hasattr(native, "prepare_quad_pairs"):
        pytest.skip("native_metrics.prepare_quad_pairs is not built")
    return native


def _regular_grid(size: int) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    x, y = np.meshgrid(
        np.arange(size + 1, dtype=np.float64),
        np.arange(size + 1, dtype=np.float64),
    )
    vertices = np.column_stack((x.ravel(), y.ravel(), 0.01 * np.sin(x.ravel())))
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
    edges: dict[tuple[int, int], list[int]] = {}
    for face_index, triangle in enumerate(triangles):
        for local in range(3):
            first = int(triangle[local])
            second = int(triangle[(local + 1) % 3])
            edge = (min(first, second), max(first, second))
            edges.setdefault(edge, []).append(face_index)
    face_pairs = np.asarray(
        [sorted(incident) for incident in edges.values() if len(incident) == 2],
        dtype=np.int64,
    )
    return vertices, triangles, face_pairs


def test_cube_protects_sharp_feature_edges_and_emits_six_quads() -> None:
    """Only coplanar face diagonals merge; cube feature edges remain protected."""
    mesh = trimesh.creation.box()
    result = native_quad_dominant_remesh(mesh.vertices, mesh.faces)

    assert result.triangles.shape == (0, 3)
    assert result.quads.shape == (6, 4)
    assert result.diagnostics.output_quads == 6
    assert result.diagnostics.output_triangles == 0
    assert result.diagnostics.protected_feature_edges == 12
    assert result.diagnostics.rejected_protected == 12
    assert result.diagnostics.min_quad_scaled_jacobian == 1.0
    assert result.diagnostics.max_quad_aspect_ratio == 1.0
    assert result.diagnostics.max_quad_warpage == 0.0
    np.testing.assert_array_equal(result.vertices, mesh.vertices)


def test_planar_patch_merges_only_interior_diagonal_deterministically() -> None:
    vertices = np.array([[0.0, 0.0, 0.0], [1.0, 0.0, 0.0], [1.0, 1.0, 0.0], [0.0, 1.0, 0.0]])
    triangles = np.array([[0, 1, 2], [0, 2, 3]], dtype=np.int64)

    first = native_quad_dominant_remesh(vertices, triangles)
    second = native_quad_dominant_remesh(vertices, triangles)

    assert first.quads.shape == (1, 4)
    assert first.triangles.shape == (0, 3)
    assert first.diagnostics.protected_boundary_edges == 4
    assert first.diagnostics.protected_feature_edges == 0
    assert first.diagnostics.min_quad_scaled_jacobian == 1.0
    assert np.array_equal(first.quads, second.quads)
    np.testing.assert_array_equal(first.vertices, vertices)
    np.testing.assert_array_equal(second.vertices, vertices)
    assert first.diagnostics.model_dump() == second.diagnostics.model_dump()
    assert first.diagnostics.route == "native_quad_dominant"
    assert first.diagnostics.contract == "native_quad"
    assert first.diagnostics.fallback_reason is None


def test_warped_pair_fails_quality_gate_and_preserves_triangles() -> None:
    vertices = np.array([[0.0, 0.0, 0.0], [1.0, 0.0, 0.0], [1.0, 1.0, 0.3], [0.0, 1.0, 0.0]])
    triangles = np.array([[0, 1, 2], [0, 2, 3]], dtype=np.int64)
    result = native_quad_dominant_remesh(
        vertices, triangles, config=QuadDominantConfig(max_warpage=0.05)
    )

    assert result.quads.shape == (0, 4)
    assert np.array_equal(result.triangles, triangles)
    assert result.diagnostics.rejected_quality == 1
    assert result.diagnostics.output_triangles == 2
    assert result.diagnostics.route == "native_quad_dominant"
    assert result.diagnostics.contract == "native_quad"
    assert result.diagnostics.fallback_reason == "no_valid_pair_accepted"
    np.testing.assert_array_equal(result.vertices, vertices)


@pytest.mark.parametrize(
    ("triangles", "message"),
    [
        (
            np.array(((0, 1, 2.5), (0, 2, 3)), dtype=object),
            "triangles must contain exact finite signed int64 indices",
        ),
        (
            np.array(((False, 1, 2), (False, 2, 3)), dtype=object),
            "triangles must contain exact finite signed int64 indices",
        ),
        (
            np.array((("0", 1, 2), ("0", 2, 3)), dtype=object),
            "triangles must contain exact finite signed int64 indices",
        ),
        (
            np.array(((0, 1, float("inf")), (0, 2, 3)), dtype=object),
            "triangles must contain exact finite signed int64 indices",
        ),
        (
            np.array(((0, 1, 4), (0, 2, 3)), dtype=np.int64),
            "triangle indices are outside the input vertex range",
        ),
        (
            np.array(((0, 1, 2**63), (0, 2, 3)), dtype=object),
            "triangle indices exceed signed int64 range",
        ),
    ],
)
def test_invalid_triangle_indices_reject_without_lossy_cast(
    triangles: np.ndarray,
    message: str,
) -> None:
    vertices = np.array([[0.0, 0.0, 0.0], [1.0, 0.0, 0.0], [1.0, 1.0, 0.0], [0.0, 1.0, 0.0]])
    vertices_before = vertices.copy()
    triangles_before = triangles.copy()
    errors: list[str] = []

    for _ in range(2):
        with pytest.raises(ValueError) as caught:
            native_quad_dominant_remesh(vertices, triangles)
        errors.append(str(caught.value))

    assert errors == [message, message]
    np.testing.assert_equal(vertices, vertices_before)
    np.testing.assert_equal(triangles, triangles_before)


def test_explicit_real_wall_edge_is_canonicalized_and_blocks_pairing() -> None:
    vertices = np.array([[0.0, 0.0, 0.0], [1.0, 0.0, 0.0], [1.0, 1.0, 0.0], [0.0, 1.0, 0.0]])
    triangles = np.array([[0, 1, 2], [0, 2, 3]], dtype=np.int64)
    vertices_before = vertices.copy()
    triangles_before = triangles.copy()
    config = QuadDominantConfig(protected_wall_edges=[(np.int64(2), np.int64(0))])

    first = native_quad_dominant_remesh(vertices, triangles, config=config)
    second = native_quad_dominant_remesh(vertices, triangles, config=config)

    np.testing.assert_array_equal(first.triangles, triangles)
    assert first.quads.shape == (0, 4)
    assert first.diagnostics.protected_wall_edges == 1
    assert first.diagnostics.candidate_pairs == 1
    assert first.diagnostics.rejected_protected == 1
    np.testing.assert_array_equal(first.vertices, second.vertices)
    np.testing.assert_array_equal(first.triangles, second.triangles)
    np.testing.assert_array_equal(first.quads, second.quads)
    assert first.diagnostics.model_dump() == second.diagnostics.model_dump()
    np.testing.assert_equal(vertices, vertices_before)
    np.testing.assert_equal(triangles, triangles_before)


@pytest.mark.parametrize(
    ("protected_wall_edges", "message"),
    [
        ([(1, 3)], "protected wall edge (1, 3) is not an input surface edge"),
        ([(0, 0)], "protected wall edge must have distinct endpoints"),
    ],
)
def test_invalid_protected_wall_edge_fails_closed(
    protected_wall_edges: list[tuple[int, int]],
    message: str,
) -> None:
    vertices = np.array([[0.0, 0.0, 0.0], [1.0, 0.0, 0.0], [1.0, 1.0, 0.0], [0.0, 1.0, 0.0]])
    triangles = np.array([[0, 1, 2], [0, 2, 3]], dtype=np.int64)
    vertices_before = vertices.copy()
    triangles_before = triangles.copy()
    config = QuadDominantConfig(protected_wall_edges=protected_wall_edges)
    errors: list[str] = []

    for _ in range(2):
        with pytest.raises(ValueError) as caught:
            native_quad_dominant_remesh(vertices, triangles, config=config)
        errors.append(str(caught.value))

    assert errors == [message, message]
    np.testing.assert_equal(vertices, vertices_before)
    np.testing.assert_equal(triangles, triangles_before)


@pytest.mark.parametrize("protected_wall_edges", [[(True, 2)], [("0", "2")]])
def test_protected_wall_edges_reject_lossy_raw_indices(
    protected_wall_edges: list[tuple[int, int]],
) -> None:
    with pytest.raises(
        ValueError,
        match="protected_wall_edges must contain pairs of exact signed int64 indices",
    ):
        QuadDominantConfig(protected_wall_edges=protected_wall_edges)


@pytest.mark.parametrize(
    ("vertices", "triangles", "message"),
    [
        (
            np.array([[0.0, 0.0, 0.0], [1.0, 0.0, 0.0], [0.0, 1.0, 0.0]]),
            np.array([[0, 1, 1]], dtype=np.int64),
            "degenerate triangle",
        ),
        (
            np.array([[0.0, 0.0, 0.0], [1.0, 0.0, 0.0], [0.0, 1.0, 0.0]]),
            np.array([[0, 1, 2], [2, 1, 0]], dtype=np.int64),
            "duplicate triangle",
        ),
        (
            np.array([[0.0, 0.0, 0.0], [1.0, 0.0, 0.0], [2.0, 0.0, 0.0]]),
            np.array([[0, 1, 2]], dtype=np.int64),
            "zero-area triangle",
        ),
        (
            np.array([[0.0, 0.0, 0.0], [1.0, 0.0, 0.0], [0.0, 1.0, 0.0], [0.0, 0.0, 1.0]]),
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
    ],
)
def test_invalid_topology_is_rejected_before_quad_pairing(
    vertices: np.ndarray,
    triangles: np.ndarray,
    message: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from core.utils import native_extensions

    errors: list[str] = []
    with pytest.raises(ValueError, match=message) as native_error:
        native_quad_dominant_remesh(vertices, triangles)
    errors.append(str(native_error.value))
    monkeypatch.setattr(native_extensions, "load_native_metrics", lambda: None)
    with pytest.raises(ValueError, match=message) as python_error:
        native_quad_dominant_remesh(vertices, triangles)
    errors.append(str(python_error.value))
    assert errors[0] == errors[1]


def test_vertex_link_non_manifold_input_fails_closed_without_mutation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Two fans at one vertex cannot be emitted as a source-topology-preserving mesh."""
    vertices = np.array(
        [
            [0.0, 0.0, 0.0],
            [1.0, 0.0, 0.0],
            [1.0, 1.0, 0.0],
            [0.0, 1.0, 0.0],
            [-1.0, 0.0, 0.0],
            [-1.0, -1.0, 0.0],
            [0.0, -1.0, 0.0],
        ]
    )
    triangles = np.array([[0, 1, 2], [0, 2, 3], [0, 4, 5], [0, 5, 6]], dtype=np.int64)
    vertices_before = vertices.copy()
    triangles_before = triangles.copy()
    errors: list[str] = []

    from core.utils import native_extensions

    for attempt in range(2):
        if attempt == 1:
            monkeypatch.setattr(native_extensions, "load_native_metrics", lambda: None)
        with pytest.raises(ValueError) as caught:
            native_quad_dominant_remesh(vertices, triangles)
        errors.append(str(caught.value))

    assert errors == ["surface contains non-manifold vertex 0"] * 2
    np.testing.assert_equal(vertices, vertices_before)
    np.testing.assert_equal(triangles, triangles_before)


def test_disconnected_manifold_components_remain_valid_and_independent() -> None:
    vertices = np.array(
        [
            [0.0, 0.0, 0.0],
            [1.0, 0.0, 0.0],
            [1.0, 1.0, 0.0],
            [0.0, 1.0, 0.0],
            [3.0, 0.0, 0.0],
            [4.0, 0.0, 0.0],
            [4.0, 1.0, 0.0],
            [3.0, 1.0, 0.0],
        ]
    )
    triangles = np.array([[0, 1, 2], [0, 2, 3], [4, 5, 6], [4, 6, 7]], dtype=np.int64)

    result = native_quad_dominant_remesh(vertices, triangles)

    assert result.triangles.shape == (0, 3)
    assert result.quads.shape == (2, 4)
    np.testing.assert_array_equal(result.vertices, vertices)


def test_native_quad_preparer_matches_oracle_with_duplicate_wall_and_repeats() -> None:
    native = _native_quad_preparer()
    vertices, triangles, _ = _regular_grid(8)
    wall_edges = [(0, 10), (10, 0)]
    expected = _prepare_quad_pairs_python(vertices, triangles, wall_edges, 45.0)
    wall_array = np.asarray(wall_edges, dtype=np.int64)

    observed = [native.prepare_quad_pairs(vertices, triangles, wall_array, 45.0) for _ in range(3)]

    for face_pairs, diagnostics in observed:
        np.testing.assert_array_equal(face_pairs, expected[0])
        np.testing.assert_array_equal(diagnostics, expected[1])
    for index in range(1, len(observed)):
        np.testing.assert_array_equal(observed[index][0], observed[0][0])
        np.testing.assert_array_equal(observed[index][1], observed[0][1])


def test_native_quad_preparer_preserves_open_boundary_and_threshold_comparison() -> None:
    native = _native_quad_preparer()
    vertices = np.array(
        [
            [0.0, 0.0, 0.0],
            [1.0, 0.0, 0.0],
            [0.0, 1.0, 0.0],
            [0.0, -0.5, np.sqrt(3.0) / 2.0],
        ],
        dtype=np.float64,
    )
    triangles = np.array([[0, 1, 2], [1, 0, 3]], dtype=np.int64)
    walls = np.empty((0, 2), dtype=np.int64)
    expected = _prepare_quad_pairs_python(vertices, triangles, [], 60.0)
    observed = native.prepare_quad_pairs(vertices, triangles, walls, 60.0)

    np.testing.assert_array_equal(observed[0], expected[0])
    np.testing.assert_array_equal(observed[1], expected[1])
    assert int(observed[1][0]) == 4
    assert int(observed[1][3]) == 1


def test_native_quad_preparer_supports_empty_surface() -> None:
    native = _native_quad_preparer()
    result = native.prepare_quad_pairs(
        np.empty((0, 3), dtype=np.float64),
        np.empty((0, 3), dtype=np.int64),
        np.empty((0, 2), dtype=np.int64),
        45.0,
    )

    assert result[0].shape == (0, 2)
    np.testing.assert_array_equal(result[1], np.zeros(5, dtype=np.int64))


@pytest.mark.parametrize(
    ("field", "replacement"),
    [
        ("vertices", lambda value: value.astype(np.float32)),
        ("vertices", np.asfortranarray),
        ("triangles", lambda value: value.astype(np.int32)),
        ("triangles", np.asfortranarray),
        ("wall_edges", lambda value: value.astype(np.int32)),
        (
            "wall_edges",
            lambda _value: np.array([[0, 9, 2, 9], [0, 9, 2, 9]], dtype=np.int64)[:, ::2],
        ),
    ],
)
def test_native_quad_preparer_requires_exact_contiguous_arrays(
    field: str,
    replacement: Callable[[np.ndarray], np.ndarray],
) -> None:
    native = _native_quad_preparer()
    inputs = {
        "vertices": np.array(
            [[0.0, 0.0, 0.0], [1.0, 0.0, 0.0], [1.0, 1.0, 0.0], [0.0, 1.0, 0.0]],
            dtype=np.float64,
        ),
        "triangles": np.array([[0, 1, 2], [0, 2, 3]], dtype=np.int64),
        "wall_edges": np.array([[0, 2]], dtype=np.int64),
    }
    inputs[field] = replacement(inputs[field])
    with pytest.raises(TypeError):
        native.prepare_quad_pairs(
            inputs["vertices"], inputs["triangles"], inputs["wall_edges"], 45.0
        )


def test_native_pair_selector_matches_oracle_and_is_order_deterministic() -> None:
    native = _native_quad_selector()
    vertices, triangles, face_pairs = _regular_grid(6)
    kwargs = {
        "min_scaled_jacobian": 0.01,
        "max_aspect_ratio": 10.0,
        "max_warpage": 1.0,
    }
    expected = _select_quad_pairs_python(vertices, triangles, face_pairs, **kwargs)

    rng = np.random.default_rng(20260730)
    observed_results: list[dict[str, Any]] = []
    for pairs in (face_pairs, face_pairs[rng.permutation(len(face_pairs))]):
        observed_results.append(
            native.select_quad_pairs(
                vertices,
                triangles,
                np.ascontiguousarray(pairs),
                kwargs["min_scaled_jacobian"],
                kwargs["max_aspect_ratio"],
                kwargs["max_warpage"],
            )
        )

    for observed in observed_results:
        np.testing.assert_array_equal(observed["accepted_face_pairs"], expected[0])
        np.testing.assert_array_equal(observed["quads"], expected[1])
        np.testing.assert_allclose(observed["quality"], expected[2], rtol=0.0, atol=1e-14)
        assert observed["rejected_quality"] == expected[3]
    for key in ("accepted_face_pairs", "quads", "quality"):
        np.testing.assert_array_equal(observed_results[0][key], observed_results[1][key])


def test_native_pair_selector_preserves_nextafter_threshold_classification() -> None:
    native = _native_quad_selector()
    vertices = np.array(
        [[0.0, 0.0, 0.0], [1.0, 0.0, 0.0], [1.1, 1.0, 0.02], [0.0, 1.0, 0.0]],
        dtype=np.float64,
    )
    triangles = np.array([[0, 1, 2], [0, 2, 3]], dtype=np.int64)
    face_pairs = np.array([[0, 1]], dtype=np.int64)
    oriented_points = vertices[np.array([1, 2, 3, 0], dtype=np.int64)]
    quality = _quad_quality(oriented_points)
    assert quality is not None
    scaled_jacobian, aspect_ratio, warpage = quality
    cases = (
        (
            (scaled_jacobian, 10.0, 1.0),
            (np.nextafter(scaled_jacobian, np.inf), 10.0, 1.0),
        ),
        (
            (0.01, aspect_ratio, 1.0),
            (0.01, np.nextafter(aspect_ratio, -np.inf), 1.0),
        ),
        (
            (0.01, 10.0, warpage),
            (0.01, 10.0, np.nextafter(warpage, -np.inf)),
        ),
    )
    for passing, rejecting in cases:
        native_pass = native.select_quad_pairs(vertices, triangles, face_pairs, *passing)
        python_pass = _select_quad_pairs_python(
            vertices,
            triangles,
            face_pairs,
            min_scaled_jacobian=passing[0],
            max_aspect_ratio=passing[1],
            max_warpage=passing[2],
        )
        np.testing.assert_array_equal(native_pass["quads"], python_pass[1])
        assert len(native_pass["quads"]) == 1

        native_reject = native.select_quad_pairs(vertices, triangles, face_pairs, *rejecting)
        python_reject = _select_quad_pairs_python(
            vertices,
            triangles,
            face_pairs,
            min_scaled_jacobian=rejecting[0],
            max_aspect_ratio=rejecting[1],
            max_warpage=rejecting[2],
        )
        np.testing.assert_array_equal(native_reject["quads"], python_reject[1])
        assert len(native_reject["quads"]) == 0
        assert native_reject["rejected_quality"] == 1


@pytest.mark.parametrize(
    ("field", "replacement"),
    [
        ("vertices", lambda value: value.astype(np.float32)),
        ("vertices", np.asfortranarray),
        ("triangles", lambda value: value.astype(np.int32)),
        ("triangles", np.asfortranarray),
        ("face_pairs", lambda value: value.astype(np.int32)),
        (
            "face_pairs",
            lambda _value: np.array([[0, 9, 1, 9], [0, 9, 1, 9]], dtype=np.int64)[:, ::2],
        ),
    ],
)
def test_native_pair_selector_requires_exact_contiguous_arrays(
    field: str,
    replacement: Callable[[np.ndarray], np.ndarray],
) -> None:
    native = _native_quad_selector()
    inputs: dict[str, np.ndarray] = {
        "vertices": np.array(
            [[0.0, 0.0, 0.0], [1.0, 0.0, 0.0], [1.0, 1.0, 0.0], [0.0, 1.0, 0.0]],
            dtype=np.float64,
        ),
        "triangles": np.array([[0, 1, 2], [0, 2, 3]], dtype=np.int64),
        "face_pairs": np.array([[0, 1]], dtype=np.int64),
    }
    inputs[field] = replacement(inputs[field])
    with pytest.raises(TypeError):
        native.select_quad_pairs(
            inputs["vertices"], inputs["triangles"], inputs["face_pairs"], 0.2, 4.0, 0.05
        )


@pytest.mark.parametrize(
    ("vertices", "triangles", "face_pairs", "message"),
    [
        (
            np.array([[0.0, 0.0, 0.0], [np.nan, 0.0, 0.0], [0.0, 1.0, 0.0]]),
            np.array([[0, 1, 2]], dtype=np.int64),
            np.empty((0, 2), dtype=np.int64),
            "finite",
        ),
        (
            np.array([[0.0, 0.0, 0.0], [1.0, 0.0, 0.0], [0.0, 1.0, 0.0]]),
            np.array([[0, 1, 1]], dtype=np.int64),
            np.empty((0, 2), dtype=np.int64),
            "distinct vertex",
        ),
        (
            np.array([[0.0, 0.0, 0.0], [1.0, 0.0, 0.0], [0.0, 1.0, 0.0]]),
            np.array([[0, 1, 2]], dtype=np.int64),
            np.array([[0, 0]], dtype=np.int64),
            "distinct triangle",
        ),
        (
            np.array([[0.0, 0.0, 0.0], [1.0, 0.0, 0.0], [0.0, 1.0, 0.0]]),
            np.array([[0, 1, 2]], dtype=np.int64),
            np.array([[0, 1]], dtype=np.int64),
            "invalid triangle",
        ),
    ],
)
def test_native_pair_selector_fails_closed_on_invalid_payload(
    vertices: np.ndarray,
    triangles: np.ndarray,
    face_pairs: np.ndarray,
    message: str,
) -> None:
    native = _native_quad_selector()
    with pytest.raises(ValueError, match=message):
        native.select_quad_pairs(vertices, triangles, face_pairs, 0.2, 4.0, 0.05)


def test_huge_finite_coordinates_never_emit_nonfinite_quad_quality() -> None:
    native = _native_quad_selector()
    vertices = np.array(
        [
            [0.0, 0.0, 0.0],
            [1e300, 0.0, 0.0],
            [1e300, 1e300, 0.0],
            [0.0, 1e300, 0.0],
        ],
        dtype=np.float64,
    )
    triangles = np.array([[0, 1, 2], [0, 2, 3]], dtype=np.int64)
    face_pairs = np.array([[0, 1]], dtype=np.int64)

    direct = native.select_quad_pairs(vertices, triangles, face_pairs, 0.2, 4.0, 0.05)
    fallback = _select_quad_pairs_python(
        vertices,
        triangles,
        face_pairs,
        min_scaled_jacobian=0.2,
        max_aspect_ratio=4.0,
        max_warpage=0.05,
    )
    result = native_quad_dominant_remesh(vertices, triangles)
    assert direct["rejected_quality"] == 0
    assert fallback[3] == 0
    np.testing.assert_array_equal(direct["accepted_face_pairs"], fallback[0])
    np.testing.assert_array_equal(direct["quads"], fallback[1])
    np.testing.assert_array_equal(direct["quality"], fallback[2])
    assert np.isfinite(direct["quality"]).all()
    np.testing.assert_array_equal(result.vertices, vertices)
    assert result.triangles.shape == (0, 3)
    assert result.quads.shape == (1, 4)
    assert result.diagnostics.rejected_quality == 0
    for value in (
        result.diagnostics.min_quad_scaled_jacobian,
        result.diagnostics.max_quad_aspect_ratio,
        result.diagnostics.max_quad_warpage,
    ):
        assert value is None or np.isfinite(value)


def test_public_quad_route_matches_native_disabled_fallback_and_repeats(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    vertices, triangles, _ = _regular_grid(5)
    native_results = [native_quad_dominant_remesh(vertices, triangles) for _ in range(3)]
    first = native_results[0]
    for result in native_results[1:]:
        np.testing.assert_array_equal(result.vertices, first.vertices)
        np.testing.assert_array_equal(result.triangles, first.triangles)
        np.testing.assert_array_equal(result.quads, first.quads)
        assert result.diagnostics.model_dump() == first.diagnostics.model_dump()

    from core.utils import native_extensions

    monkeypatch.setattr(native_extensions, "load_native_metrics", lambda: None)
    fallback = native_quad_dominant_remesh(vertices, triangles)
    np.testing.assert_array_equal(fallback.vertices, first.vertices)
    np.testing.assert_array_equal(fallback.triangles, first.triangles)
    np.testing.assert_array_equal(fallback.quads, first.quads)
    fallback_diagnostics = fallback.diagnostics.model_dump()
    native_diagnostics = first.diagnostics.model_dump()
    for metric in (
        "min_quad_scaled_jacobian",
        "max_quad_aspect_ratio",
        "max_quad_warpage",
    ):
        fallback_value = fallback_diagnostics.pop(metric)
        native_value = native_diagnostics.pop(metric)
        assert fallback_value is not None and native_value is not None
        assert abs(fallback_value - native_value) <= 1e-14
    assert fallback_diagnostics == native_diagnostics


@pytest.mark.parametrize(
    "malformed_result",
    [
        {
            "accepted_face_pairs": np.array([[0, 1]], dtype=np.int32),
            "quads": np.array([[1, 2, 3, 0]], dtype=np.int64),
            "quality": np.array([[1.0, 1.0, 0.0]], dtype=np.float64),
            "rejected_quality": 0,
        },
        {
            "accepted_face_pairs": np.array([[0, 1]], dtype=np.int64),
            "quads": np.array([[1, 2, 3]], dtype=np.int64),
            "quality": np.array([[1.0, 1.0, 0.0]], dtype=np.float64),
            "rejected_quality": 0,
        },
        {
            "accepted_face_pairs": np.array([[0, 1]], dtype=np.int64),
            "quads": np.array([[1, 2, 3, 0]], dtype=np.int64),
            "quality": np.array([[1.0, 1.0, 0.0]], dtype=np.float64),
            "rejected_quality": -1,
        },
    ],
)
def test_native_pair_selector_rejects_malformed_backend_without_fallback(
    malformed_result: dict[str, object],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    vertices = np.array(
        [[0.0, 0.0, 0.0], [1.0, 0.0, 0.0], [1.0, 1.0, 0.0], [0.0, 1.0, 0.0]],
        dtype=np.float64,
    )
    triangles = np.array([[0, 1, 2], [0, 2, 3]], dtype=np.int64)
    face_pairs = np.array([[0, 1]], dtype=np.int64)
    calls = 0

    def malformed_backend(*_args: object) -> dict[str, object]:
        nonlocal calls
        calls += 1
        return malformed_result

    from core.utils import native_extensions

    monkeypatch.setattr(
        native_extensions,
        "load_native_metrics",
        lambda: SimpleNamespace(select_quad_pairs=malformed_backend),
    )
    with pytest.raises(RuntimeError, match="native select_quad_pairs returned invalid"):
        _select_quad_pairs(
            vertices,
            triangles,
            face_pairs,
            min_scaled_jacobian=0.2,
            max_aspect_ratio=4.0,
            max_warpage=0.05,
        )
    assert calls == 1


@pytest.mark.parametrize(
    ("malformed_result", "message"),
    [
        ("not-a-tuple", "invalid result"),
        (
            (
                np.array([[0, 1]], dtype=np.int32),
                np.array([4, 0, 0, 1, 0], dtype=np.int64),
            ),
            "invalid face_pairs",
        ),
        (
            (
                np.array([[0, 1]], dtype=np.int64),
                np.array([4, 0, 0, 1], dtype=np.int64),
            ),
            "invalid diagnostics",
        ),
    ],
)
def test_native_quad_preparer_rejects_malformed_arrays_without_fallback(
    malformed_result: object,
    message: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    vertices = np.array(
        [[0.0, 0.0, 0.0], [1.0, 0.0, 0.0], [1.0, 1.0, 0.0], [0.0, 1.0, 0.0]],
        dtype=np.float64,
    )
    triangles = np.array([[0, 1, 2], [0, 2, 3]], dtype=np.int64)
    calls = 0

    def malformed_backend(*_args: object) -> object:
        nonlocal calls
        calls += 1
        return malformed_result

    from core.utils import native_extensions

    monkeypatch.setattr(
        native_extensions,
        "load_native_metrics",
        lambda: SimpleNamespace(prepare_quad_pairs=malformed_backend),
    )
    with pytest.raises(RuntimeError, match=message):
        _prepare_quad_pairs(vertices, triangles, [], 45.0)
    assert calls == 1


@pytest.mark.parametrize(
    ("vertices", "triangles", "walls", "face_pairs", "diagnostics", "message"),
    [
        (
            np.array(
                [
                    [0.0, 0.0, 0.0],
                    [1.0, 0.0, 0.0],
                    [0.0, 1.0, 0.0],
                    [3.0, 0.0, 0.0],
                    [4.0, 0.0, 0.0],
                    [3.0, 1.0, 0.0],
                ]
            ),
            np.array([[0, 1, 2], [3, 4, 5]], dtype=np.int64),
            [],
            np.array([[0, 1]], dtype=np.int64),
            np.array([6, 0, 0, 1, 0], dtype=np.int64),
            "non-adjacent",
        ),
        (
            np.array([[0.0, 0.0, 0.0], [1.0, 0.0, 0.0], [1.0, 1.0, 0.0], [0.0, 1.0, 0.0]]),
            np.array([[0, 1, 2], [0, 2, 3]], dtype=np.int64),
            [(0, 2)],
            np.array([[0, 1]], dtype=np.int64),
            np.array([4, 0, 1, 1, 0], dtype=np.int64),
            "protected wall",
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
            np.array([[0, 1, 2], [1, 0, 3]], dtype=np.int64),
            [],
            np.array([[0, 1]], dtype=np.int64),
            np.array([4, 1, 0, 1, 0], dtype=np.int64),
            "protected feature",
        ),
    ],
)
def test_native_quad_preparer_rejects_invented_or_protected_pairs(
    vertices: np.ndarray,
    triangles: np.ndarray,
    walls: list[tuple[int, int]],
    face_pairs: np.ndarray,
    diagnostics: np.ndarray,
    message: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from core.utils import native_extensions

    monkeypatch.setattr(
        native_extensions,
        "load_native_metrics",
        lambda: SimpleNamespace(prepare_quad_pairs=lambda *_args: (face_pairs, diagnostics)),
    )
    with pytest.raises(RuntimeError, match=message):
        _prepare_quad_pairs(vertices, triangles, walls, 45.0)


def test_native_quad_preparer_preserves_non_iterable_wall_contract(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from core.utils import native_extensions

    monkeypatch.setattr(
        native_extensions,
        "load_native_metrics",
        lambda: SimpleNamespace(prepare_quad_pairs=lambda *_args: None),
    )
    with pytest.raises(
        ValueError,
        match="protected_wall_edges must contain pairs of exact signed int64 indices",
    ):
        _prepare_quad_pairs(
            np.empty((0, 3), dtype=np.float64),
            np.empty((0, 3), dtype=np.int64),
            "not-an-edge-list",
            45.0,
        )
