"""Focused contracts for native quad-dominant surface conversion."""

from __future__ import annotations

import numpy as np
import pytest
import trimesh

from core.preprocessor.native_remesh import (
    QuadDominantConfig,
    native_quad_dominant_remesh,
)


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
) -> None:
    with pytest.raises(ValueError, match=message):
        native_quad_dominant_remesh(vertices, triangles)


def test_vertex_link_non_manifold_input_fails_closed_without_mutation() -> None:
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

    for _ in range(2):
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
