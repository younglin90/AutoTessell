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
            np.array(
                [[0.0, 0.0, 0.0], [1.0, 0.0, 0.0], [0.0, 1.0, 0.0], [0.0, 0.0, 1.0]]
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
    ],
)
def test_invalid_topology_is_rejected_before_quad_pairing(
    vertices: np.ndarray,
    triangles: np.ndarray,
    message: str,
) -> None:
    with pytest.raises(ValueError, match=message):
        native_quad_dominant_remesh(vertices, triangles)
