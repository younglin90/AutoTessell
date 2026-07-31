"""Deferred, report-only bridge from existing tri/strict-quad diagnostics.

The bridge transfers only a source-evidence digest that an existing diagnostic
already exposes with the required authority predicate.  It never synthesizes
a combined hash from unrelated fields, because that would turn diagnostic
facts into unearned source-certificate authority.
"""

from __future__ import annotations

from dataclasses import dataclass

from core.preprocessor.native_quad.strict_pair_preflight import StrictQuadPairPreflight
from core.preprocessor.native_tri.certificate import NativeTriSourceCertificateDiagnostic

from .surface_source_certificate_schema import (
    SourceCertificateEvidenceName,
    SurfaceSourceCertificateEvidence,
    SurfaceSourceCertificateSchemaReport,
    report_surface_source_certificate_schema,
)


@dataclass(frozen=True, slots=True)
class SurfaceSourceCertificateBridgeReport:
    """Partial source-evidence transfer that cannot authorize a product."""

    product_class: str
    status: str
    directly_bound_evidence: tuple[SourceCertificateEvidenceName, ...]
    deferred_evidence: tuple[SourceCertificateEvidenceName, ...]
    schema_report: SurfaceSourceCertificateSchemaReport
    product_accepted: bool
    candidate_constructed: bool
    production_mesh_changed: bool
    artifact_delta: int


def _report(
    *,
    product_class: str,
    status: str,
    evidence: SurfaceSourceCertificateEvidence,
    directly_bound_evidence: tuple[SourceCertificateEvidenceName, ...],
) -> SurfaceSourceCertificateBridgeReport:
    """Freeze the schema result while retaining the bridge's defer reason."""
    schema = report_surface_source_certificate_schema(product_class, evidence)
    return SurfaceSourceCertificateBridgeReport(
        product_class,
        status,
        directly_bound_evidence,
        schema.missing_evidence,
        schema,
        False,
        False,
        False,
        0,
    )


def report_native_tri_source_certificate_bridge(
    diagnostic: object,
) -> SurfaceSourceCertificateBridgeReport:
    """Bind only the tri diagnostic's explicit source-feature declaration.

    ``source_vertices_hash`` plus ``source_faces_hash`` are not a declared
    single shape certificate.  ``source_payload_hash`` combines faces, patch
    labels, and feature declarations, so it is not an independently bound
    patch digest.  The diagnostic has no physical-group or candidate-face
    provenance digest.  Those facts must remain deferred.
    """
    if not isinstance(diagnostic, NativeTriSourceCertificateDiagnostic):
        return _report(
            product_class="tri",
            status="defer_invalid_native_tri_source_certificate",
            evidence=SurfaceSourceCertificateEvidence(),
            directly_bound_evidence=(),
        )
    feature_sha256 = (
        diagnostic.declared_feature_edges_sha256 if diagnostic.feature_ownership_explicit else None
    )
    return _report(
        product_class="tri",
        status="defer_missing_authoritative_source_certificate_evidence",
        evidence=SurfaceSourceCertificateEvidence(feature_sha256=feature_sha256),
        directly_bound_evidence=("feature",) if feature_sha256 is not None else (),
    )


def report_strict_quad_pair_source_certificate_bridge(
    preflight: object,
) -> SurfaceSourceCertificateBridgeReport:
    """Defer strict-quad bridge until it exposes dedicated authority hashes.

    The pair preflight's vertex/triangle/quad hashes and boolean preservation
    facts are structural diagnostics.  It exposes no one-field source-shape,
    feature, patch, physical-group, or provenance certificate digest, so none
    may be relabelled as schema authority here.
    """
    if not isinstance(preflight, StrictQuadPairPreflight):
        return _report(
            product_class="strict_quad",
            status="defer_invalid_strict_quad_pair_preflight",
            evidence=SurfaceSourceCertificateEvidence(),
            directly_bound_evidence=(),
        )
    return _report(
        product_class="strict_quad",
        status="defer_missing_authoritative_source_certificate_evidence",
        evidence=SurfaceSourceCertificateEvidence(),
        directly_bound_evidence=(),
    )
