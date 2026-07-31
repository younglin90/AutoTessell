"""Fail-closed report schema for future tri/quad source certificates.

This module validates only declared evidence *identifiers*.  It does not read
geometry, validate a certificate's mathematical claims, construct a candidate,
or grant a product acceptance.  It exists so every future surface-product
route reports the same missing-evidence vocabulary before integration work.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

SurfaceProductClass = Literal["tri", "strict_quad", "tri_quad"]
SourceCertificateEvidenceName = Literal[
    "source_shape",
    "feature",
    "patch",
    "physical_group",
    "provenance",
]

_PRODUCT_CLASSES = frozenset({"tri", "strict_quad", "tri_quad"})
_EVIDENCE_FIELDS: tuple[tuple[SourceCertificateEvidenceName, str], ...] = (
    ("source_shape", "source_shape_sha256"),
    ("feature", "feature_sha256"),
    ("patch", "patch_sha256"),
    ("physical_group", "physical_group_sha256"),
    ("provenance", "provenance_sha256"),
)


@dataclass(frozen=True, slots=True)
class SurfaceSourceCertificateEvidence:
    """Opaque SHA-256 evidence identifiers; ``None`` means not supplied."""

    source_shape_sha256: str | None = None
    feature_sha256: str | None = None
    patch_sha256: str | None = None
    physical_group_sha256: str | None = None
    provenance_sha256: str | None = None


@dataclass(frozen=True, slots=True)
class SurfaceSourceCertificateSchemaReport:
    """Deterministic metadata report; never a source-product certificate."""

    product_class: str
    status: str
    schema_complete: bool
    missing_evidence: tuple[SourceCertificateEvidenceName, ...]
    malformed_evidence: tuple[SourceCertificateEvidenceName, ...]
    product_accepted: bool
    product_rejection: str
    source_geometry_mutated: bool
    candidate_constructed: bool
    production_mesh_changed: bool
    artifact_delta: int


def _is_canonical_sha256(value: object) -> bool:
    return bool(
        isinstance(value, str)
        and len(value) == 64
        and value == value.lower()
        and all(character in "0123456789abcdef" for character in value)
    )


def report_surface_source_certificate_schema(
    product_class: object,
    evidence: object,
) -> SurfaceSourceCertificateSchemaReport:
    """Report exact missing source evidence without accepting any product.

    A syntactically complete set of opaque IDs remains unverified because this
    schema neither binds them to source geometry nor checks their semantics.
    Product acceptance consequently stays false for every return path.
    """
    normalized_class = product_class if isinstance(product_class, str) else "invalid"
    if normalized_class not in _PRODUCT_CLASSES:
        return SurfaceSourceCertificateSchemaReport(
            normalized_class,
            "report_invalid_surface_product_class",
            False,
            tuple(name for name, _ in _EVIDENCE_FIELDS),
            (),
            False,
            "source_product_certificate_required",
            False,
            False,
            False,
            0,
        )
    if not isinstance(evidence, SurfaceSourceCertificateEvidence):
        return SurfaceSourceCertificateSchemaReport(
            normalized_class,
            "report_invalid_source_certificate_schema",
            False,
            tuple(name for name, _ in _EVIDENCE_FIELDS),
            (),
            False,
            "source_product_certificate_required",
            False,
            False,
            False,
            0,
        )
    missing = tuple(name for name, field in _EVIDENCE_FIELDS if getattr(evidence, field) is None)
    malformed = tuple(
        name
        for name, field in _EVIDENCE_FIELDS
        if getattr(evidence, field) is not None
        and not _is_canonical_sha256(getattr(evidence, field))
    )
    complete = not missing and not malformed
    status = (
        "report_complete_source_certificate_evidence_unverified"
        if complete
        else (
            "report_malformed_source_certificate_evidence"
            if malformed
            else "report_missing_source_certificate_evidence"
        )
    )
    return SurfaceSourceCertificateSchemaReport(
        normalized_class,
        status,
        complete,
        missing,
        malformed,
        False,
        "source_product_certificate_required",
        False,
        False,
        False,
        0,
    )
