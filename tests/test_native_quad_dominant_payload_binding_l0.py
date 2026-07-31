"""L0 payload-binding evidence for actual default-OFF quad-dominant output."""

from __future__ import annotations

import os
from unittest.mock import patch

import numpy as np
import pytest

from core.evaluator.surface_physical_group_provenance import (
    AuthoritativePhysicalGroupMapping,
)
from core.preprocessor.native_quad.quad_dominant_payload_binding_l0 import (
    diagnose_quad_dominant_payload_binding_l0,
)
from core.preprocessor.native_remesh.quad_dominant import native_quad_dominant_remesh

_ENV = "AUTO_TESSELL_TRI_QUAD_PAYLOAD_BINDING_L0"


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
        np.array(
            ((0, 1, 2), (0, 2, 3), (4, 5, 6), (7, 8, 9)),
            dtype=np.int64,
        ),
    )


def _arguments() -> tuple[object, ...]:
    vertices, triangles = _fixture()
    result = native_quad_dominant_remesh(vertices, triangles)
    return (
        vertices,
        triangles,
        result,
        ("wall", "wall", "outlet", "far"),
        AuthoritativePhysicalGroupMapping(("inlet", "inlet", "outlet", "far"), True),
        ("outlet", "far"),
        ("wall",),
        ("outlet", "far"),
        ("inlet",),
    )


def _diagnose(*values: object):
    (
        vertices,
        triangles,
        result,
        source_patches,
        source_groups,
        triangle_patches,
        quad_patches,
        triangle_groups,
        quad_groups,
    ) = values
    return diagnose_quad_dominant_payload_binding_l0(
        vertices,
        triangles,
        result,
        source_patch_ids=source_patches,
        source_physical_groups=source_groups,
        output_triangle_patch_ids=triangle_patches,
        output_quad_patch_ids=quad_patches,
        output_triangle_physical_groups=triangle_groups,
        output_quad_physical_groups=quad_groups,
    )


def test_default_off_does_not_bind_or_claim_tri_quad_product() -> None:
    report = _diagnose(*_arguments())

    assert report.enabled is False
    assert report.status == "reject_tri_quad_payload_binding_disabled"
    assert report.missing_evidence == ("payload_binding_opt_in",)
    assert report.accepted is False
    assert report.product_claimed is False


def test_complete_actual_binding_is_deterministic_but_never_product_success() -> None:
    with patch.dict(os.environ, {_ENV: "1"}):
        reports = tuple(_diagnose(*_arguments()) for _ in range(3))

    report = reports[0]
    assert reports == (report,) * 3
    assert report.status == "report_tri_quad_payload_binding_complete_unverified"
    assert report.source_vertices_exact is True
    assert report.output_face_provenance_exact is True
    assert report.source_patch_payload_valid is True
    assert report.source_physical_groups_authoritative is True
    assert report.output_triangle_payloads_valid is True
    assert report.output_quad_payloads_valid is True
    assert report.patch_payload_preserved is True
    assert report.physical_group_payload_preserved is True
    assert report.binding_complete is True
    assert report.source_patch_payload_sha256 is not None
    assert report.source_physical_group_sha256 is not None
    assert report.accepted is False
    assert report.product_claimed is False


@pytest.mark.parametrize(
    ("position", "replacement", "status"),
    (
        (3, None, "reject_tri_quad_payload_binding_source_patch"),
        (
            4,
            AuthoritativePhysicalGroupMapping(("inlet", "inlet", "outlet", "far"), False),
            "reject_tri_quad_payload_binding_source_physical_group",
        ),
        (
            3,
            ("wall", "inlet", "outlet", "far"),
            "reject_tri_quad_payload_binding_mixed_pair_patch",
        ),
        (
            4,
            AuthoritativePhysicalGroupMapping(("inlet", "wall", "outlet", "far"), True),
            "reject_tri_quad_payload_binding_mixed_pair_physical_group",
        ),
        (5, ("far", "outlet"), "reject_tri_quad_payload_binding_output_mismatch"),
        (6, (), "reject_tri_quad_payload_binding_output_payload"),
    ),
)
def test_absent_malformed_mixed_or_reordered_payloads_reject(
    position: int,
    replacement: object,
    status: str,
) -> None:
    values = list(_arguments())
    values[position] = replacement
    with patch.dict(os.environ, {_ENV: "1"}):
        report = _diagnose(*values)

    assert report.status == status
    assert report.accepted is False
    assert report.product_claimed is False


def test_tampered_face_provenance_rejects_before_payload_binding() -> None:
    values = list(_arguments())
    result = values[2]
    assert hasattr(result, "remaining_triangle_source_indices")
    result.remaining_triangle_source_indices = np.array((0,), dtype=np.int64)
    with patch.dict(os.environ, {_ENV: "1"}):
        report = _diagnose(*values)

    assert report.status == "reject_tri_quad_payload_binding_output_provenance"
    assert report.accepted is False
    assert report.product_claimed is False
