"""L0 geometry/topology binding evidence for actual tri+quad output."""

from __future__ import annotations

import os
from unittest.mock import patch

import numpy as np
import pytest

from core.evaluator.surface_physical_group_provenance import (
    AuthoritativePhysicalGroupMapping,
)
from core.preprocessor.native_quad.quad_dominant_geometry_topology_binding_l0 import (
    AuthoritativeFeatureEdges,
    diagnose_quad_dominant_geometry_topology_binding_l0,
)
from core.preprocessor.native_quad.quad_dominant_payload_binding_l0 import (
    diagnose_quad_dominant_payload_binding_l0,
)
from core.preprocessor.native_remesh.quad_dominant import native_quad_dominant_remesh

_GEOMETRY_ENV = "AUTO_TESSELL_TRI_QUAD_GEOMETRY_TOPOLOGY_BINDING_L0"
_PAYLOAD_ENV = "AUTO_TESSELL_TRI_QUAD_PAYLOAD_BINDING_L0"


def _fixture() -> tuple[np.ndarray, np.ndarray]:
    return (
        np.array(
            (
                (0.0, 0.0, 0.0),
                (1.0, 0.0, 0.0),
                (1.0, 1.0, 0.0),
                (0.0, 1.0, 0.0),
                (3.0, 0.0, 0.0),
                (4.0, 0.0, 0.0),
                (3.0, 1.0, 0.0),
                (6.0, 0.0, 0.0),
                (7.0, 0.0, 0.0),
                (6.0, 1.0, 0.0),
            ),
            dtype=np.float64,
        ),
        np.array(((0, 1, 2), (0, 2, 3), (4, 5, 6), (7, 8, 9)), dtype=np.int64),
    )


def _arguments() -> tuple[object, ...]:
    vertices, triangles = _fixture()
    result = native_quad_dominant_remesh(vertices, triangles)
    with patch.dict(os.environ, {_PAYLOAD_ENV: "1"}):
        payload = diagnose_quad_dominant_payload_binding_l0(
            vertices,
            triangles,
            result,
            source_patch_ids=("wall", "wall", "outlet", "far"),
            source_physical_groups=AuthoritativePhysicalGroupMapping(
                ("inlet", "inlet", "outlet", "far"),
                True,
            ),
            output_triangle_patch_ids=("outlet", "far"),
            output_quad_patch_ids=("wall",),
            output_triangle_physical_groups=("outlet", "far"),
            output_quad_physical_groups=("inlet",),
        )
    return vertices, triangles, result, payload


def _diagnose(
    vertices: object,
    triangles: object,
    result: object,
    payload: object,
    features: object,
):
    return diagnose_quad_dominant_geometry_topology_binding_l0(
        vertices,
        triangles,
        result,
        payload_binding=payload,
        source_feature_edges=features,
    )


def test_default_off_does_not_bind_or_claim_tri_quad_product() -> None:
    report = _diagnose(*_arguments(), AuthoritativeFeatureEdges((), True))

    assert report.status == "reject_tri_quad_geometry_topology_binding_disabled"
    assert report.enabled is False
    assert report.accepted is False
    assert report.product_claimed is False


def test_complete_geometry_topology_binding_is_deterministic_and_immutable() -> None:
    vertices, triangles, result, payload = _arguments()
    snapshots = (
        vertices.tobytes(),
        triangles.tobytes(),
        result.vertices.tobytes(),
        result.triangles.tobytes(),
        result.quads.tobytes(),
    )
    with patch.dict(os.environ, {_GEOMETRY_ENV: "1"}):
        reports = tuple(
            _diagnose(vertices, triangles, result, payload, AuthoritativeFeatureEdges((), True))
            for _ in range(3)
        )

    report = reports[0]
    assert reports == (report,) * 3
    assert report.status == "report_tri_quad_geometry_topology_binding_complete_unverified"
    assert report.source_vertices_exact is True
    assert report.output_face_provenance_exact is True
    assert report.payload_binding_complete is True
    assert report.source_feature_edges_authoritative is True
    assert report.source_oriented_manifold is True
    assert report.output_oriented_manifold is True
    assert report.boundary_equal is True
    assert report.features_preserved is True
    assert report.component_count_equal is True
    assert report.euler_characteristic_equal is True
    assert report.arrays_unchanged is True
    assert report.geometry_topology_complete is True
    assert report.accepted is False
    assert report.product_claimed is False
    assert snapshots == (
        vertices.tobytes(),
        triangles.tobytes(),
        result.vertices.tobytes(),
        result.triangles.tobytes(),
        result.quads.tobytes(),
    )


@pytest.mark.parametrize(
    ("features", "status"),
    (
        (None, "reject_tri_quad_geometry_topology_feature_authority"),
        (
            AuthoritativeFeatureEdges((), False),
            "reject_tri_quad_geometry_topology_feature_authority",
        ),
        (
            AuthoritativeFeatureEdges(((2, 0),), True),
            "reject_tri_quad_geometry_topology_feature_authority",
        ),
        (
            AuthoritativeFeatureEdges(((0, 1), (0, 1)), True),
            "reject_tri_quad_geometry_topology_feature_authority",
        ),
        (
            AuthoritativeFeatureEdges(((0, 9),), True),
            "reject_tri_quad_geometry_topology_feature_authority",
        ),
        (AuthoritativeFeatureEdges(((0, 2),), True), "reject_tri_quad_geometry_topology_binding"),
    ),
)
def test_missing_malformed_or_removed_protected_features_reject(
    features: object,
    status: str,
) -> None:
    with patch.dict(os.environ, {_GEOMETRY_ENV: "1"}):
        report = _diagnose(*_arguments(), features)

    assert report.status == status
    assert report.accepted is False
    assert report.product_claimed is False


def test_incomplete_payload_or_tampered_provenance_rejects_fail_closed() -> None:
    vertices, triangles, result, payload = _arguments()
    with patch.dict(os.environ, {_GEOMETRY_ENV: "1"}):
        incomplete = _diagnose(
            vertices,
            triangles,
            result,
            diagnose_quad_dominant_payload_binding_l0(
                vertices,
                triangles,
                result,
                source_patch_ids=(),
                source_physical_groups=None,
                output_triangle_patch_ids=(),
                output_quad_patch_ids=(),
                output_triangle_physical_groups=(),
                output_quad_physical_groups=(),
            ),
            AuthoritativeFeatureEdges((), True),
        )
        result.remaining_triangle_source_indices = np.array((0, 1), dtype=np.int64)
        tampered = _diagnose(
            vertices,
            triangles,
            result,
            payload,
            AuthoritativeFeatureEdges((), True),
        )

    assert incomplete.status == "reject_tri_quad_geometry_topology_payload_binding"
    assert tampered.status == "reject_tri_quad_geometry_topology_output_provenance"
    for report in (incomplete, tampered):
        assert report.accepted is False
        assert report.product_claimed is False


def test_nonmanifold_source_rejects_after_exact_partition_check() -> None:
    vertices, triangles, result, payload = _arguments()
    nonmanifold_source = triangles.copy()
    nonmanifold_source[2] = (0, 2, 4)
    nonmanifold_result = result.model_copy(deep=True)
    nonmanifold_result.triangles = nonmanifold_source[
        nonmanifold_result.remaining_triangle_source_indices
    ]
    with patch.dict(os.environ, {_GEOMETRY_ENV: "1"}):
        report = _diagnose(
            vertices,
            nonmanifold_source,
            nonmanifold_result,
            payload,
            AuthoritativeFeatureEdges((), True),
        )

    assert report.status == "reject_tri_quad_geometry_topology_nonmanifold"
    assert report.accepted is False
    assert report.product_claimed is False
