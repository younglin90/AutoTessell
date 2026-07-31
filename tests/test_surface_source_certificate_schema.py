"""Report-only source-certificate schema contracts for surface products."""

from __future__ import annotations

from dataclasses import replace
from hashlib import sha256

import pytest

from core.evaluator.surface_source_certificate_schema import (
    SurfaceSourceCertificateEvidence,
    report_surface_source_certificate_schema,
)

_EVIDENCE_NAMES = (
    "source_shape",
    "feature",
    "patch",
    "physical_group",
    "provenance",
)


def _complete_evidence() -> SurfaceSourceCertificateEvidence:
    return SurfaceSourceCertificateEvidence(
        **{f"{name}_sha256": sha256(name.encode("ascii")).hexdigest() for name in _EVIDENCE_NAMES}
    )


def _assert_report_only(report: object) -> None:
    assert getattr(report, "product_accepted") is False
    assert getattr(report, "product_rejection") == "source_product_certificate_required"
    assert getattr(report, "source_geometry_mutated") is False
    assert getattr(report, "candidate_constructed") is False
    assert getattr(report, "production_mesh_changed") is False
    assert getattr(report, "artifact_delta") == 0


@pytest.mark.parametrize("product_class", ("tri", "strict_quad", "tri_quad"))
def test_each_surface_product_reports_all_missing_source_evidence_exactly(
    product_class: str,
) -> None:
    report = report_surface_source_certificate_schema(
        product_class, SurfaceSourceCertificateEvidence()
    )

    assert report.product_class == product_class
    assert report.status == "report_missing_source_certificate_evidence"
    assert report.schema_complete is False
    assert report.missing_evidence == _EVIDENCE_NAMES
    assert report.malformed_evidence == ()
    _assert_report_only(report)


@pytest.mark.parametrize("missing_name", _EVIDENCE_NAMES)
def test_each_required_evidence_field_is_reported_without_granting_acceptance(
    missing_name: str,
) -> None:
    evidence = _complete_evidence()
    report = report_surface_source_certificate_schema(
        "tri_quad", replace(evidence, **{f"{missing_name}_sha256": None})
    )

    assert report.status == "report_missing_source_certificate_evidence"
    assert report.missing_evidence == (missing_name,)
    assert report.malformed_evidence == ()
    _assert_report_only(report)


@pytest.mark.parametrize("product_class", ("tri", "strict_quad", "tri_quad"))
def test_complete_evidence_is_deterministic_but_never_product_acceptance(
    product_class: str,
) -> None:
    evidence = _complete_evidence()
    reports = tuple(
        report_surface_source_certificate_schema(product_class, evidence) for _ in range(3)
    )

    assert reports == (reports[0],) * 3
    report = reports[0]
    assert report.status == "report_complete_source_certificate_evidence_unverified"
    assert report.schema_complete is True
    assert report.missing_evidence == ()
    assert report.malformed_evidence == ()
    _assert_report_only(report)


def test_malformed_or_invalid_schema_is_fail_closed_without_guessing_missing_evidence() -> None:
    malformed = replace(_complete_evidence(), feature_sha256="not-a-digest")
    malformed_report = report_surface_source_certificate_schema("strict_quad", malformed)
    invalid_report = report_surface_source_certificate_schema("quad", object())

    assert malformed_report.status == "report_malformed_source_certificate_evidence"
    assert malformed_report.missing_evidence == ()
    assert malformed_report.malformed_evidence == ("feature",)
    assert invalid_report.status == "report_invalid_surface_product_class"
    assert invalid_report.missing_evidence == _EVIDENCE_NAMES
    _assert_report_only(malformed_report)
    _assert_report_only(invalid_report)
