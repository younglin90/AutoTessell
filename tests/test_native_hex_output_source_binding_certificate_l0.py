"""Hex output-boundary source/B-Rep binding certificate L0 contracts."""

from __future__ import annotations

from dataclasses import replace
from hashlib import sha256

import numpy as np

from core.analyzer.readers.step import CadEntityProvenance
from core.generator.native_hex.output_source_binding_certificate_l0 import (
    diagnose_hex_output_source_binding_l0,
)


def _readonly(values: np.ndarray) -> np.ndarray:
    values.setflags(write=False)
    return values


def _provenance(*, authoritative_groups: bool = True) -> CadEntityProvenance:
    return CadEntityProvenance(
        status="complete_brep_output_binding_fixture",
        face_count=2,
        topological_edge_count=5,
        triangle_face_ordinals=_readonly(np.asarray((0, 1), dtype=np.int64)),
        triangle_orientation_reversed=_readonly(np.asarray((False, False), dtype=np.bool_)),
        seam_vertex_ids=_readonly(np.asarray((0, 1, 2, 3), dtype=np.int64)),
        canonical_vertex_source_ids=_readonly(np.asarray((0, 1, 2, 3), dtype=np.int64)),
        oriented_canonical_faces=_readonly(np.asarray(((0, 1, 2), (1, 3, 2)), dtype=np.int64)),
        face_names=(None, None),
        physical_group_names=("inlet", "wall"),
        xde_layer_names=((), ()),
        xde_surface_colors=(None, None),
        xde_assembly_paths=(None, None),
        xde_layer_authoritative=False,
        xde_layer_coverage_count=0,
        xde_color_display_metadata_authoritative=False,
        xde_assembly_identity_authoritative=False,
        face_ordinals_authoritative=True,
        face_orientation_authoritative=True,
        seam_connectivity_authoritative=True,
        physical_groups_authoritative=authoritative_groups,
        ordered_triangle_coordinate_sha256=sha256(b"triangles").hexdigest(),
        ordered_face_ordinal_sha256=sha256(b"ordinals").hexdigest(),
        ordered_orientation_sha256=sha256(b"orientation").hexdigest(),
        seam_connectivity_sha256=sha256(b"seams").hexdigest(),
        xde_metadata_sha256=sha256(b"xde").hexdigest(),
    )


def _payload() -> tuple[np.ndarray, np.ndarray, tuple[str, str]]:
    return (
        np.asarray((7, 11), dtype=np.int64),
        np.asarray((0, 1), dtype=np.int64),
        ("inlet", "wall"),
    )


def _assert_never_success(report: object) -> None:
    assert getattr(report, "accepted") is False
    assert getattr(report, "mesher_success_allowed") is False
    assert getattr(report, "product_claimed") is False


def test_complete_fixture_binding_is_deterministic_but_never_hex_success() -> None:
    ids, ordinals, groups = _payload()
    reports = tuple(
        diagnose_hex_output_source_binding_l0(_provenance(), ids, ordinals, groups)
        for _ in range(3)
    )

    assert reports == (reports[0],) * 3
    report = reports[0]
    assert report.status == "report_hex_output_source_binding_complete_unverified"
    assert report.output_boundary_face_count == 2
    assert report.source_face_mapping_complete is True
    assert report.physical_group_mapping_complete is True
    assert report.strict_binding_complete is True
    assert report.missing_evidence == ()
    assert report.malformed_evidence == ()
    assert report.rejection_reason == "hex_output_product_certificate_required"
    assert report.output_boundary_face_ids_sha256 is not None
    assert report.output_to_source_face_sha256 is not None
    assert report.output_physical_group_sha256 is not None
    _assert_never_success(report)


def test_missing_or_invalid_output_mapping_fails_closed_before_product_claim() -> None:
    ids, ordinals, groups = _payload()
    missing = diagnose_hex_output_source_binding_l0(
        _provenance(), ids, np.asarray((), dtype=np.int64), groups
    )
    wrong_group = diagnose_hex_output_source_binding_l0(
        _provenance(), ids, ordinals, ("wall", "inlet")
    )
    duplicate_face = diagnose_hex_output_source_binding_l0(
        _provenance(), np.asarray((7, 7), dtype=np.int64), ordinals, groups
    )

    assert missing.status == "reject_output_source_face_mapping_invalid"
    assert missing.source_face_mapping_complete is False
    assert missing.missing_evidence == ("output_boundary_face_to_source_brep", "physical_group")
    assert missing.malformed_evidence == ("output_boundary_face_to_source_brep",)
    assert wrong_group.status == "reject_output_physical_group_mapping_mismatch"
    assert wrong_group.physical_group_mapping_complete is False
    assert wrong_group.malformed_evidence == ("output_physical_group",)
    assert duplicate_face.status == "reject_output_boundary_face_ids_invalid"
    assert duplicate_face.malformed_evidence == ("output_boundary_face_ids",)
    for report in (missing, wrong_group, duplicate_face):
        _assert_never_success(report)


def test_unknown_source_physical_groups_and_incomplete_brep_remain_hard_gates() -> None:
    ids, ordinals, groups = _payload()
    unknown_groups = diagnose_hex_output_source_binding_l0(
        _provenance(authoritative_groups=False), ids, ordinals, groups
    )
    incomplete_brep = diagnose_hex_output_source_binding_l0(
        replace(_provenance(), face_ordinals_authoritative=False), ids, ordinals, groups
    )

    assert unknown_groups.status == "reject_source_physical_groups_unavailable"
    assert unknown_groups.missing_evidence == ("physical_group",)
    assert incomplete_brep.status == "reject_incomplete_source_brep_authority"
    assert incomplete_brep.missing_evidence == (
        "source_brep",
        "output_boundary_face_to_source_brep",
        "physical_group",
    )
    _assert_never_success(unknown_groups)
    _assert_never_success(incomplete_brep)
