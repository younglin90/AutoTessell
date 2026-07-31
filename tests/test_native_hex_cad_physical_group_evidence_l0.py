"""L0 CAD physical-group authority gap diagnostics for native hex."""

from __future__ import annotations

from dataclasses import replace
from hashlib import sha256

import numpy as np

from core.analyzer.readers.step import CadEntityProvenance
from core.generator.native_hex.cad_physical_group_evidence_l0 import (
    diagnose_cad_physical_group_evidence,
)


def _readonly(values: np.ndarray) -> np.ndarray:
    values.setflags(write=False)
    return values


def _provenance(
    *,
    physical_groups_authoritative: bool = False,
    physical_group_names: tuple[str | None, ...] = (None,),
    face_ordinals_authoritative: bool = True,
) -> CadEntityProvenance:
    return CadEntityProvenance(
        status="complete_brep_test_fixture",
        face_count=1,
        topological_edge_count=3,
        triangle_face_ordinals=_readonly(np.asarray((0,), dtype=np.int64)),
        triangle_orientation_reversed=_readonly(np.asarray((False,), dtype=np.bool_)),
        seam_vertex_ids=_readonly(np.asarray((0, 1, 2), dtype=np.int64)),
        canonical_vertex_source_ids=_readonly(np.asarray((0, 1, 2), dtype=np.int64)),
        oriented_canonical_faces=_readonly(np.asarray(((0, 1, 2),), dtype=np.int64)),
        face_names=(None,),
        physical_group_names=physical_group_names,
        xde_layer_names=((),),
        xde_surface_colors=(None,),
        xde_assembly_paths=(None,),
        xde_layer_authoritative=False,
        xde_layer_coverage_count=0,
        xde_color_display_metadata_authoritative=False,
        xde_assembly_identity_authoritative=False,
        face_ordinals_authoritative=face_ordinals_authoritative,
        face_orientation_authoritative=True,
        seam_connectivity_authoritative=True,
        physical_groups_authoritative=physical_groups_authoritative,
        ordered_triangle_coordinate_sha256=sha256(b"triangles").hexdigest(),
        ordered_face_ordinal_sha256=sha256(b"ordinals").hexdigest(),
        ordered_orientation_sha256=sha256(b"orientation").hexdigest(),
        seam_connectivity_sha256=sha256(b"seam").hexdigest(),
        xde_metadata_sha256=sha256(b"xde").hexdigest(),
    )


def _assert_report_only(report: object) -> None:
    assert getattr(report, "product_accepted") is False
    assert getattr(report, "candidate_constructed") is False
    assert getattr(report, "production_mesh_changed") is False
    assert getattr(report, "artifact_delta") == 0


def test_complete_cad_brep_with_unknown_groups_rejects_exact_missing_evidence() -> None:
    provenance = _provenance()
    arrays_before = (
        provenance.triangle_face_ordinals.tobytes(),
        provenance.oriented_canonical_faces.tobytes(),
    )
    reports = tuple(diagnose_cad_physical_group_evidence(provenance) for _ in range(3))

    assert reports == (reports[0],) * 3
    report = reports[0]
    assert report.status == "reject_cad_physical_groups_unknown"
    assert report.cad_brep_complete is True
    assert report.physical_groups_declared_authoritative is False
    assert report.missing_evidence == ("physical_group",)
    assert report.malformed_evidence == ()
    assert report.physical_group_evidence_sha256 is None
    assert arrays_before == (
        provenance.triangle_face_ordinals.tobytes(),
        provenance.oriented_canonical_faces.tobytes(),
    )
    _assert_report_only(report)


def test_declared_authoritative_groups_are_distinguished_but_stay_unverified() -> None:
    provenance = _provenance(
        physical_groups_authoritative=True,
        physical_group_names=("wall",),
    )
    reports = tuple(diagnose_cad_physical_group_evidence(provenance) for _ in range(3))

    assert reports == (reports[0],) * 3
    report = reports[0]
    assert report.status == "report_cad_physical_groups_authoritative_unverified"
    assert report.cad_brep_complete is True
    assert report.physical_groups_declared_authoritative is True
    assert report.physical_group_name_count == 1
    assert report.physical_group_evidence_sha256 == sha256(b'["wall"]').hexdigest()
    assert report.missing_evidence == ()
    assert report.malformed_evidence == ()
    _assert_report_only(report)


def test_invalid_declared_group_payload_and_incomplete_brep_fail_closed() -> None:
    invalid_payload = _provenance(
        physical_groups_authoritative=True,
        physical_group_names=(None,),
    )
    incomplete = replace(_provenance(), face_ordinals_authoritative=False)
    invalid_report = diagnose_cad_physical_group_evidence(invalid_payload)
    incomplete_report = diagnose_cad_physical_group_evidence(incomplete)

    assert invalid_report.status == "reject_invalid_cad_physical_group_payload"
    assert invalid_report.missing_evidence == ()
    assert invalid_report.malformed_evidence == ("physical_group",)
    assert incomplete_report.status == "reject_incomplete_cad_brep_authority"
    assert incomplete_report.missing_evidence == ("cad_brep", "physical_group")
    _assert_report_only(invalid_report)
    _assert_report_only(incomplete_report)
