"""L0/L1 fail-closed contracts for the three native surface products."""

from __future__ import annotations

import numpy as np

from core.preprocessor.native_remesh.quad_dominant import native_quad_dominant_remesh
from core.preprocessor.native_remesh.surface_mode_contract import (
    SurfaceProductClassification,
    SurfaceProductMode,
    certify_surface_product_mode,
)


def test_tri_product_accepts_only_triangle_representation() -> None:
    accepted = certify_surface_product_mode(
        "tri",
        triangle_count=12,
        quad_count=0,
        separate_tri_quad_representation=False,
        triangular_handoff=False,
    )
    rejected = certify_surface_product_mode(
        "tri",
        triangle_count=11,
        quad_count=1,
        separate_tri_quad_representation=True,
        triangular_handoff=False,
    )

    assert accepted.accepted is True
    assert accepted.classification is SurfaceProductClassification.TRI_ONLY
    assert rejected.accepted is False
    assert rejected.rejection_reason == "representation_not_tri_only"


def test_strict_quad_rejects_any_triangle_and_triangular_handoff() -> None:
    pure_quad = certify_surface_product_mode(
        SurfaceProductMode.QUAD,
        triangle_count=0,
        quad_count=6,
        separate_tri_quad_representation=False,
        triangular_handoff=False,
    )
    triangle_remainder = certify_surface_product_mode(
        "quad",
        triangle_count=1,
        quad_count=6,
        separate_tri_quad_representation=True,
        triangular_handoff=False,
    )
    handoff = certify_surface_product_mode(
        "quad",
        triangle_count=0,
        quad_count=6,
        separate_tri_quad_representation=False,
        triangular_handoff=True,
    )

    assert pure_quad.accepted is True
    assert pure_quad.classification is SurfaceProductClassification.STRICT_QUAD
    assert triangle_remainder.accepted is False
    assert triangle_remainder.rejection_reason == "triangles_not_allowed_in_strict_quad"
    assert handoff.accepted is False
    assert handoff.rejection_reason == "triangular_handoff_not_strict_quad"


def test_native_quad_dominant_is_candidate_mixed_never_strict_quad() -> None:
    strict_request = certify_surface_product_mode(
        "quad",
        triangle_count=0,
        quad_count=6,
        separate_tri_quad_representation=True,
        triangular_handoff=False,
        producer="native_quad_dominant",
    )
    mixed_request = certify_surface_product_mode(
        "native_tri_quad_mixed",
        triangle_count=0,
        quad_count=6,
        separate_tri_quad_representation=True,
        triangular_handoff=False,
        producer="native_quad_dominant",
    )

    assert strict_request.classification is SurfaceProductClassification.CANDIDATE_MIXED
    assert strict_request.accepted is False
    assert strict_request.rejection_reason == "representation_not_strict_quad"
    assert mixed_request.requested_mode is SurfaceProductMode.TRI_QUAD
    assert mixed_request.classification is SurfaceProductClassification.CANDIDATE_MIXED
    assert mixed_request.accepted is True


def test_mode_contract_rejects_invalid_counts_and_unknown_modes() -> None:
    invalid_counts = certify_surface_product_mode(
        "tri",
        triangle_count=True,
        quad_count=0,
        separate_tri_quad_representation=False,
        triangular_handoff=False,
    )
    unknown_mode = certify_surface_product_mode(
        "quad_dominant",
        triangle_count=0,
        quad_count=1,
        separate_tri_quad_representation=False,
        triangular_handoff=False,
    )

    assert invalid_counts.accepted is False
    assert invalid_counts.rejection_reason == "surface_element_counts_invalid"
    assert unknown_mode.requested_mode is None
    assert unknown_mode.accepted is False
    assert unknown_mode.rejection_reason == "unknown_surface_product_mode"


def test_real_quad_dominant_result_has_deterministic_candidate_mixed_certificate() -> None:
    vertices = np.array(((0.0, 0.0, 0.0), (1.0, 0.0, 0.0), (1.0, 1.0, 0.0), (0.0, 1.0, 0.0)))
    triangles = np.array(((0, 1, 2), (0, 2, 3)), dtype=np.int64)
    certificates = []
    for _ in range(3):
        result = native_quad_dominant_remesh(
            vertices,
            triangles,
        )
        certificates.append(
            certify_surface_product_mode(
                "tri_quad",
                triangle_count=len(result.triangles),
                quad_count=len(result.quads),
                separate_tri_quad_representation=True,
                triangular_handoff=False,
                producer="native_quad_dominant",
            )
        )

    assert all(certificate.accepted for certificate in certificates)
    assert all(
        certificate.classification is SurfaceProductClassification.CANDIDATE_MIXED
        for certificate in certificates
    )
    assert certificates == [certificates[0]] * 3
