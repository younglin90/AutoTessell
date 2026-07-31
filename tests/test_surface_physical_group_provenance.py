"""L0 physical-group mapping evidence remains report-only."""

from __future__ import annotations

from hashlib import sha256

from core.evaluator.surface_physical_group_provenance import (
    AuthoritativePhysicalGroupMapping,
    report_surface_physical_group_provenance,
)


def _assert_report_only(report: object) -> None:
    assert getattr(report, "product_accepted") is False
    assert getattr(report, "candidate_constructed") is False
    assert getattr(report, "production_mesh_changed") is False
    assert getattr(report, "artifact_delta") == 0


def test_missing_mapping_defers_tri_and_strict_quad_physical_group_evidence() -> None:
    reports = tuple(report_surface_physical_group_provenance(2, None) for _ in range(3))
    assert reports == (reports[0],) * 3
    report = reports[0]
    assert report.status == "defer_missing_explicit_physical_group_mapping"
    assert report.missing_evidence == ("physical_group",)
    _assert_report_only(report)


def test_explicit_authoritative_mapping_has_dedicated_digest_but_stays_unverified() -> None:
    mapping = AuthoritativePhysicalGroupMapping(("wall", "inlet"), True)
    report = report_surface_physical_group_provenance(2, mapping)
    assert report.status == "report_authoritative_physical_group_mapping_unverified"
    assert report.physical_group_sha256 == sha256(b'["wall","inlet"]').hexdigest()
    assert report.missing_evidence == ()
    _assert_report_only(report)


def test_patch_like_or_malformed_mapping_cannot_be_coerced_into_physical_groups() -> None:
    malformed = AuthoritativePhysicalGroupMapping(("wall", ""), True)
    undeclared = AuthoritativePhysicalGroupMapping(("wall", "inlet"), False)
    malformed_report = report_surface_physical_group_provenance(2, malformed)
    undeclared_report = report_surface_physical_group_provenance(2, undeclared)
    assert malformed_report.status == "reject_invalid_physical_group_mapping"
    assert malformed_report.malformed_evidence == ("physical_group",)
    assert undeclared_report.status == "defer_missing_explicit_physical_group_mapping"
    _assert_report_only(malformed_report)
    _assert_report_only(undeclared_report)
