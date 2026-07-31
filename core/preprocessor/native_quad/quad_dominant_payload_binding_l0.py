"""Default-OFF, report-only payload binding for quad-dominant output.

This module binds explicitly supplied source patch and authoritative physical
group payloads to an already-produced mixed triangle/quad representation.  It
does not select a route, modify a result, write an artifact, or certify a
``tri_quad`` product.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from hashlib import sha256
from numbers import Integral

import numpy as np

from core.evaluator.surface_physical_group_provenance import (
    AuthoritativePhysicalGroupMapping,
    report_surface_physical_group_provenance,
)
from core.preprocessor.native_remesh.quad_dominant import QuadDominantResult
from core.preprocessor.native_remesh.surface_mode_contract import SurfaceProductMode

from .quad_dominant_product_certificate_l0 import (
    diagnose_quad_dominant_product_output_l0,
)

_ENV = "AUTO_TESSELL_TRI_QUAD_PAYLOAD_BINDING_L0"


@dataclass(frozen=True, slots=True)
class QuadDominantPayloadBindingL0:
    """Read-only payload-binding facts; never an output-product acceptance."""

    enabled: bool
    status: str
    rejection_reason: str
    source_vertices_exact: bool
    output_face_provenance_exact: bool
    source_patch_payload_valid: bool
    source_physical_groups_authoritative: bool
    output_triangle_payloads_valid: bool
    output_quad_payloads_valid: bool
    patch_payload_preserved: bool
    physical_group_payload_preserved: bool
    binding_complete: bool
    source_patch_payload_sha256: str | None
    source_physical_group_sha256: str | None
    output_triangle_patch_sha256: str | None
    output_quad_patch_sha256: str | None
    output_triangle_physical_group_sha256: str | None
    output_quad_physical_group_sha256: str | None
    missing_evidence: tuple[str, ...]
    malformed_evidence: tuple[str, ...]
    accepted: bool = False
    product_claimed: bool = False
    contract: str = "native_quad_dominant_payload_binding_l0"


def tri_quad_payload_binding_l0_enabled() -> bool:
    """Return whether this disconnected diagnostic was explicitly requested."""
    return os.environ.get(_ENV) == "1"


def _patch_payloads(value: object, count: int) -> tuple[int | str, ...] | None:
    if not isinstance(value, (tuple, list)) or len(value) != count:
        return None
    payloads: list[int | str] = []
    for raw in value:
        scalar = raw.item() if isinstance(raw, np.generic) else raw
        if isinstance(scalar, bool):
            return None
        if isinstance(scalar, Integral):
            payloads.append(int(scalar))
        elif isinstance(scalar, str) and scalar.strip():
            payloads.append(scalar)
        else:
            return None
    return tuple(payloads)


def _physical_group_payloads(value: object, count: int) -> tuple[str, ...] | None:
    if not isinstance(value, (tuple, list)) or len(value) != count:
        return None
    if not all(isinstance(group, str) and group.strip() for group in value):
        return None
    return tuple(value)


def _payload_hash(value: tuple[int | str, ...] | tuple[str, ...] | None) -> str | None:
    if value is None:
        return None
    return sha256(
        json.dumps(value, ensure_ascii=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()


def _report(
    *,
    enabled: bool,
    status: str,
    rejection_reason: str,
    source_vertices_exact: bool,
    output_face_provenance_exact: bool,
    source_patches: tuple[int | str, ...] | None,
    source_physical_groups: tuple[str, ...] | None,
    triangle_patches: tuple[int | str, ...] | None,
    quad_patches: tuple[int | str, ...] | None,
    triangle_groups: tuple[str, ...] | None,
    quad_groups: tuple[str, ...] | None,
    source_physical_groups_authoritative: bool,
    patch_payload_preserved: bool,
    physical_group_payload_preserved: bool,
    missing: tuple[str, ...] = (),
    malformed: tuple[str, ...] = (),
) -> QuadDominantPayloadBindingL0:
    source_patches_valid = source_patches is not None
    triangle_payloads_valid = triangle_patches is not None and triangle_groups is not None
    quad_payloads_valid = quad_patches is not None and quad_groups is not None
    binding_complete = bool(
        source_vertices_exact
        and output_face_provenance_exact
        and source_patches_valid
        and source_physical_groups_authoritative
        and triangle_payloads_valid
        and quad_payloads_valid
        and patch_payload_preserved
        and physical_group_payload_preserved
    )
    return QuadDominantPayloadBindingL0(
        enabled=enabled,
        status=status,
        rejection_reason=rejection_reason,
        source_vertices_exact=source_vertices_exact,
        output_face_provenance_exact=output_face_provenance_exact,
        source_patch_payload_valid=source_patches_valid,
        source_physical_groups_authoritative=source_physical_groups_authoritative,
        output_triangle_payloads_valid=triangle_payloads_valid,
        output_quad_payloads_valid=quad_payloads_valid,
        patch_payload_preserved=patch_payload_preserved,
        physical_group_payload_preserved=physical_group_payload_preserved,
        binding_complete=binding_complete,
        source_patch_payload_sha256=_payload_hash(source_patches),
        source_physical_group_sha256=_payload_hash(source_physical_groups),
        output_triangle_patch_sha256=_payload_hash(triangle_patches),
        output_quad_patch_sha256=_payload_hash(quad_patches),
        output_triangle_physical_group_sha256=_payload_hash(triangle_groups),
        output_quad_physical_group_sha256=_payload_hash(quad_groups),
        missing_evidence=missing,
        malformed_evidence=malformed,
    )


def diagnose_quad_dominant_payload_binding_l0(
    source_vertices: object,
    source_triangles: object,
    result: object,
    *,
    source_patch_ids: object,
    source_physical_groups: object,
    output_triangle_patch_ids: object,
    output_quad_patch_ids: object,
    output_triangle_physical_groups: object,
    output_quad_physical_groups: object,
) -> QuadDominantPayloadBindingL0:
    """Diagnose explicit payload preservation without accepting a product."""
    if not tri_quad_payload_binding_l0_enabled():
        return _report(
            enabled=False,
            status="reject_tri_quad_payload_binding_disabled",
            rejection_reason="tri_quad_payload_binding_l0_disabled",
            source_vertices_exact=False,
            output_face_provenance_exact=False,
            source_patches=None,
            source_physical_groups=None,
            triangle_patches=None,
            quad_patches=None,
            triangle_groups=None,
            quad_groups=None,
            source_physical_groups_authoritative=False,
            patch_payload_preserved=False,
            physical_group_payload_preserved=False,
            missing=("payload_binding_opt_in",),
        )
    if not isinstance(result, QuadDominantResult):
        return _report(
            enabled=True,
            status="reject_tri_quad_payload_binding_result_invalid",
            rejection_reason="quad_dominant_result_required",
            source_vertices_exact=False,
            output_face_provenance_exact=False,
            source_patches=None,
            source_physical_groups=None,
            triangle_patches=None,
            quad_patches=None,
            triangle_groups=None,
            quad_groups=None,
            source_physical_groups_authoritative=False,
            patch_payload_preserved=False,
            physical_group_payload_preserved=False,
            malformed=("quad_dominant_result",),
        )

    output_certificate = diagnose_quad_dominant_product_output_l0(
        source_vertices,
        source_triangles,
        result,
        requested_mode=SurfaceProductMode.TRI_QUAD,
    )
    if not output_certificate.output_face_provenance_exact:
        return _report(
            enabled=True,
            status="reject_tri_quad_payload_binding_output_provenance",
            rejection_reason="quad_dominant_output_face_provenance_required",
            source_vertices_exact=output_certificate.source_vertices_exact,
            output_face_provenance_exact=False,
            source_patches=None,
            source_physical_groups=None,
            triangle_patches=None,
            quad_patches=None,
            triangle_groups=None,
            quad_groups=None,
            source_physical_groups_authoritative=False,
            patch_payload_preserved=False,
            physical_group_payload_preserved=False,
            missing=("output_face_provenance",),
        )
    if not output_certificate.source_vertices_exact:
        return _report(
            enabled=True,
            status="reject_tri_quad_payload_binding_source_vertices",
            rejection_reason="byte_exact_source_vertices_required",
            source_vertices_exact=False,
            output_face_provenance_exact=True,
            source_patches=None,
            source_physical_groups=None,
            triangle_patches=None,
            quad_patches=None,
            triangle_groups=None,
            quad_groups=None,
            source_physical_groups_authoritative=False,
            patch_payload_preserved=False,
            physical_group_payload_preserved=False,
            missing=("source_shape",),
        )

    source_face_count = 2 * len(result.accepted_face_pairs) + len(
        result.remaining_triangle_source_indices
    )
    source_patches = _patch_payloads(source_patch_ids, source_face_count)
    if source_patches is None:
        return _report(
            enabled=True,
            status="reject_tri_quad_payload_binding_source_patch",
            rejection_reason="source_patch_payload_required",
            source_vertices_exact=output_certificate.source_vertices_exact,
            output_face_provenance_exact=True,
            source_patches=None,
            source_physical_groups=None,
            triangle_patches=None,
            quad_patches=None,
            triangle_groups=None,
            quad_groups=None,
            source_physical_groups_authoritative=False,
            patch_payload_preserved=False,
            physical_group_payload_preserved=False,
            missing=("patch",),
            malformed=("source_patch",),
        )

    physical_report = report_surface_physical_group_provenance(
        source_face_count,
        source_physical_groups,
    )
    if physical_report.status != "report_authoritative_physical_group_mapping_unverified":
        return _report(
            enabled=True,
            status="reject_tri_quad_payload_binding_source_physical_group",
            rejection_reason="authoritative_source_physical_group_required",
            source_vertices_exact=output_certificate.source_vertices_exact,
            output_face_provenance_exact=True,
            source_patches=source_patches,
            source_physical_groups=None,
            triangle_patches=None,
            quad_patches=None,
            triangle_groups=None,
            quad_groups=None,
            source_physical_groups_authoritative=False,
            patch_payload_preserved=False,
            physical_group_payload_preserved=False,
            missing=physical_report.missing_evidence,
            malformed=physical_report.malformed_evidence,
        )
    assert isinstance(source_physical_groups, AuthoritativePhysicalGroupMapping)
    source_groups = source_physical_groups.source_face_groups

    expected_triangle_patches = tuple(
        source_patches[int(index)] for index in result.remaining_triangle_source_indices
    )
    expected_triangle_groups = tuple(
        source_groups[int(index)] for index in result.remaining_triangle_source_indices
    )
    expected_quad_patches: list[int | str] = []
    expected_quad_groups: list[str] = []
    for first, second in result.accepted_face_pairs:
        first_index, second_index = int(first), int(second)
        if source_patches[first_index] != source_patches[second_index]:
            return _report(
                enabled=True,
                status="reject_tri_quad_payload_binding_mixed_pair_patch",
                rejection_reason="quad_pair_patch_payload_ambiguous",
                source_vertices_exact=output_certificate.source_vertices_exact,
                output_face_provenance_exact=True,
                source_patches=source_patches,
                source_physical_groups=source_groups,
                triangle_patches=None,
                quad_patches=None,
                triangle_groups=None,
                quad_groups=None,
                source_physical_groups_authoritative=True,
                patch_payload_preserved=False,
                physical_group_payload_preserved=False,
                malformed=("mixed_quad_pair_patch",),
            )
        if source_groups[first_index] != source_groups[second_index]:
            return _report(
                enabled=True,
                status="reject_tri_quad_payload_binding_mixed_pair_physical_group",
                rejection_reason="quad_pair_physical_group_payload_ambiguous",
                source_vertices_exact=output_certificate.source_vertices_exact,
                output_face_provenance_exact=True,
                source_patches=source_patches,
                source_physical_groups=source_groups,
                triangle_patches=None,
                quad_patches=None,
                triangle_groups=None,
                quad_groups=None,
                source_physical_groups_authoritative=True,
                patch_payload_preserved=False,
                physical_group_payload_preserved=False,
                malformed=("mixed_quad_pair_physical_group",),
            )
        expected_quad_patches.append(source_patches[first_index])
        expected_quad_groups.append(source_groups[first_index])

    triangle_patches = _patch_payloads(
        output_triangle_patch_ids,
        len(result.triangles),
    )
    quad_patches = _patch_payloads(output_quad_patch_ids, len(result.quads))
    triangle_groups = _physical_group_payloads(
        output_triangle_physical_groups,
        len(result.triangles),
    )
    quad_groups = _physical_group_payloads(output_quad_physical_groups, len(result.quads))
    if (
        triangle_patches is None
        or quad_patches is None
        or triangle_groups is None
        or quad_groups is None
    ):
        return _report(
            enabled=True,
            status="reject_tri_quad_payload_binding_output_payload",
            rejection_reason="output_payloads_must_be_exact_and_complete",
            source_vertices_exact=output_certificate.source_vertices_exact,
            output_face_provenance_exact=True,
            source_patches=source_patches,
            source_physical_groups=source_groups,
            triangle_patches=triangle_patches,
            quad_patches=quad_patches,
            triangle_groups=triangle_groups,
            quad_groups=quad_groups,
            source_physical_groups_authoritative=True,
            patch_payload_preserved=False,
            physical_group_payload_preserved=False,
            malformed=("output_payload",),
        )
    patch_preserved = bool(
        triangle_patches == expected_triangle_patches
        and quad_patches == tuple(expected_quad_patches)
    )
    physical_preserved = bool(
        triangle_groups == expected_triangle_groups
        and quad_groups == tuple(expected_quad_groups)
    )
    if not patch_preserved or not physical_preserved:
        return _report(
            enabled=True,
            status="reject_tri_quad_payload_binding_output_mismatch",
            rejection_reason="output_payload_does_not_match_source_face_provenance",
            source_vertices_exact=output_certificate.source_vertices_exact,
            output_face_provenance_exact=True,
            source_patches=source_patches,
            source_physical_groups=source_groups,
            triangle_patches=triangle_patches,
            quad_patches=quad_patches,
            triangle_groups=triangle_groups,
            quad_groups=quad_groups,
            source_physical_groups_authoritative=True,
            patch_payload_preserved=patch_preserved,
            physical_group_payload_preserved=physical_preserved,
            malformed=("output_payload_mismatch",),
        )
    return _report(
        enabled=True,
        status="report_tri_quad_payload_binding_complete_unverified",
        rejection_reason="tri_quad_product_certificate_required",
        source_vertices_exact=output_certificate.source_vertices_exact,
        output_face_provenance_exact=True,
        source_patches=source_patches,
        source_physical_groups=source_groups,
        triangle_patches=triangle_patches,
        quad_patches=quad_patches,
        triangle_groups=triangle_groups,
        quad_groups=quad_groups,
        source_physical_groups_authoritative=True,
        patch_payload_preserved=True,
        physical_group_payload_preserved=True,
    )


__all__ = [
    "QuadDominantPayloadBindingL0",
    "diagnose_quad_dominant_payload_binding_l0",
    "tri_quad_payload_binding_l0_enabled",
]
