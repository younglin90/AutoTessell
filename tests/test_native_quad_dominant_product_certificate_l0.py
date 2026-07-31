"""Actual-output fail-closed certificates for the quad-dominant candidate."""

from __future__ import annotations

import numpy as np
import pytest

from core.preprocessor.native_quad.quad_dominant_product_certificate_l0 import (
    diagnose_quad_dominant_product_output_l0,
)
from core.preprocessor.native_remesh.quad_dominant import native_quad_dominant_remesh
from core.preprocessor.native_remesh.surface_mode_contract import (
    SurfaceProductClassification,
    SurfaceProductMode,
)


def _square() -> tuple[np.ndarray, np.ndarray]:
    return (
        np.array(
            ((0.0, 0.0, 0.0), (1.0, 0.0, 0.0), (1.0, 1.0, 0.0), (0.0, 1.0, 0.0)),
            dtype=np.float64,
        ),
        np.array(((0, 1, 2), (0, 2, 3)), dtype=np.int64),
    )


def _square_and_residual() -> tuple[np.ndarray, np.ndarray]:
    vertices, triangles = _square()
    return (
        np.vstack((vertices, np.array(((3.0, 0.0, 0.0), (4.0, 0.0, 0.0), (3.0, 1.0, 0.0))))),
        np.vstack((triangles, np.array(((4, 5, 6),), dtype=np.int64))),
    )


def test_actual_quad_dominant_output_rejects_strict_quad_even_when_all_pairs_merge() -> None:
    vertices, triangles = _square()
    result = native_quad_dominant_remesh(vertices, triangles)

    certificates = tuple(
        diagnose_quad_dominant_product_output_l0(
            vertices,
            triangles,
            result,
            requested_mode=SurfaceProductMode.QUAD,
        )
        for _ in range(3)
    )

    certificate = certificates[0]
    assert certificates == (certificate,) * 3
    assert result.triangles.shape == (0, 3)
    assert result.quads.shape == (1, 4)
    assert certificate.representation_certificate.classification is (
        SurfaceProductClassification.CANDIDATE_MIXED
    )
    assert certificate.accepted is False
    assert certificate.product_claimed is False
    assert certificate.status == "reject_quad_dominant_representation"
    assert certificate.rejection_reason == "representation_not_strict_quad"
    assert certificate.source_vertices_exact is True
    assert certificate.missing_source_evidence == (
        "feature",
        "boundary",
        "topology",
        "physical_group",
        "provenance",
    )


def test_actual_quad_dominant_output_rejects_mixed_until_source_certificate_exists() -> None:
    vertices, triangles = _square()
    result = native_quad_dominant_remesh(vertices, triangles)

    certificate = diagnose_quad_dominant_product_output_l0(
        vertices,
        triangles,
        result,
        requested_mode="tri_quad",
    )

    assert certificate.representation_certificate.accepted is True
    assert certificate.representation_certificate.classification is (
        SurfaceProductClassification.CANDIDATE_MIXED
    )
    assert certificate.accepted is False
    assert certificate.product_claimed is False
    assert certificate.source_certificate_complete is False
    assert certificate.status == "reject_quad_dominant_source_certificate_required"
    assert certificate.rejection_reason == "quad_dominant_source_certificate_required"


def test_actual_output_records_exact_face_partition_without_product_promotion() -> None:
    vertices, triangles = _square_and_residual()
    result = native_quad_dominant_remesh(vertices, triangles)
    certificates = tuple(
        diagnose_quad_dominant_product_output_l0(
            vertices,
            triangles,
            result,
            requested_mode="tri_quad",
        )
        for _ in range(3)
    )

    certificate = certificates[0]
    assert certificates == (certificate,) * 3
    np.testing.assert_array_equal(result.vertices, vertices)
    np.testing.assert_array_equal(
        result.accepted_face_pairs,
        np.array(((0, 1),), dtype=np.int64),
    )
    np.testing.assert_array_equal(
        result.remaining_triangle_source_indices,
        np.array((2,), dtype=np.int64),
    )
    np.testing.assert_array_equal(
        result.triangles,
        triangles[result.remaining_triangle_source_indices],
    )
    assert certificate.output_face_provenance_exact is True
    assert certificate.accepted_face_pairs_hash is not None
    assert certificate.remaining_triangle_source_indices_hash is not None
    assert certificate.accepted is False
    assert certificate.product_claimed is False


@pytest.mark.parametrize(
    ("field", "value"),
    (
        ("accepted_face_pairs", np.array(((1, 0),), dtype=np.int64)),
        ("accepted_face_pairs", np.array(((0, 2),), dtype=np.int64)),
        ("remaining_triangle_source_indices", np.array((0,), dtype=np.int64)),
    ),
)
def test_malformed_actual_face_partition_remains_rejected_without_product_claim(
    field: str,
    value: np.ndarray,
) -> None:
    vertices, triangles = _square_and_residual()
    result = native_quad_dominant_remesh(vertices, triangles)
    setattr(result, field, value)

    certificate = diagnose_quad_dominant_product_output_l0(
        vertices,
        triangles,
        result,
        requested_mode="tri_quad",
    )

    assert certificate.output_face_provenance_exact is False
    assert certificate.accepted is False
    assert certificate.product_claimed is False
    assert certificate.status == "reject_quad_dominant_source_certificate_required"


def test_moved_actual_output_fails_source_shape_before_any_product_claim() -> None:
    vertices, triangles = _square()
    result = native_quad_dominant_remesh(vertices, triangles)
    moved_source = vertices.copy()
    moved_source[0, 0] = 0.25

    certificate = diagnose_quad_dominant_product_output_l0(
        moved_source,
        triangles,
        result,
        requested_mode="tri_quad",
    )

    assert certificate.accepted is False
    assert certificate.product_claimed is False
    assert certificate.source_vertices_exact is False
    assert certificate.status == "reject_quad_dominant_source_shape"
    assert certificate.rejection_reason == "quad_dominant_source_vertices_not_exact"
    assert certificate.missing_source_evidence == (
        "source_shape",
        "feature",
        "boundary",
        "topology",
        "physical_group",
        "provenance",
    )
