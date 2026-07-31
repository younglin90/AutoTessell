"""Fail-closed product evidence for the current native-tri route output.

The L2 route currently returns an unchanged source while the topology-changing
operator lacks a whole-surface certificate.  This adapter binds that actual
route result to the existing source-clone certificate and never promotes it to
an independent surface-mesher product success.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from .certificate import NativeTriCandidateCertificate, certify_native_tri_candidate
from .route import NativeTriL2RouteResult


@dataclass(frozen=True, slots=True)
class NativeTriProductOutputCertificateL0:
    """Actual route-output evidence; product acceptance is deliberately false."""

    status: str
    rejection_reason: str
    source_output_hashes_match: bool
    route_flags_match_certificate: bool
    source_vertices_preserved: bool
    source_faces_preserved: bool
    topology_preserved: bool
    provenance_preserved: bool
    source_certificate: NativeTriCandidateCertificate
    accepted: bool
    mesher_success_allowed: bool
    product_claimed: bool
    contract: str = "native_tri_product_output_certificate_l0"


def _clone_provenance(face_count: int) -> tuple[tuple[int, ...], ...]:
    return tuple((index,) for index in range(face_count))


def diagnose_native_tri_product_output_l0(
    source_vertices: np.ndarray,
    source_faces: np.ndarray,
    route_result: NativeTriL2RouteResult,
) -> NativeTriProductOutputCertificateL0:
    """Bind one L2 route output to exact source evidence without product success.

    Any mismatch in vertices, faces, hashes, topology, or face provenance is a
    fail-closed output-certificate rejection.  Even a perfect source clone
    remains non-accepting because it proves only the route's current no-op,
    not an independent native-tri mesher output.
    """
    if not isinstance(route_result, NativeTriL2RouteResult):
        raise TypeError("route_result must be NativeTriL2RouteResult")

    certificate = certify_native_tri_candidate(
        source_vertices,
        source_faces,
        route_result.vertices,
        route_result.faces,
        face_provenance=_clone_provenance(len(route_result.faces)),
    )
    source_output_hashes_match = bool(
        certificate.source_vertices_hash is not None
        and certificate.source_faces_hash is not None
        and certificate.candidate_vertices_hash is not None
        and certificate.candidate_faces_hash is not None
        and certificate.source_vertices_hash == certificate.candidate_vertices_hash
        and certificate.source_faces_hash == certificate.candidate_faces_hash
        and route_result.source_vertices_hash == certificate.source_vertices_hash
        and route_result.source_faces_hash == certificate.source_faces_hash
        and route_result.output_vertices_hash == certificate.candidate_vertices_hash
        and route_result.output_faces_hash == certificate.candidate_faces_hash
        and route_result.provenance_hash == certificate.source_faces_hash
    )
    route_flags_match_certificate = bool(
        route_result.source_envelope_preserved == certificate.source_envelope_preserved
        and route_result.topology_preserved == certificate.topology_preserved
        and route_result.provenance_preserved == certificate.provenance_preserved
    )
    source_vertices_preserved = bool(certificate.source_envelope_preserved)
    source_faces_preserved = bool(
        certificate.source_faces_hash is not None
        and certificate.source_faces_hash == certificate.candidate_faces_hash
    )
    topology_preserved = bool(certificate.topology_preserved)
    provenance_preserved = bool(certificate.provenance_preserved)

    if not certificate.accepted or not source_output_hashes_match or not route_flags_match_certificate:
        status = "reject_native_tri_output_source_certificate_invalid"
        reason = "native_tri_output_source_certificate_invalid"
    elif route_result.accepted:
        status = "reject_native_tri_product_certificate_required"
        reason = "native_tri_independent_product_certificate_required"
    else:
        status = "reject_native_tri_route_not_product_ready"
        reason = route_result.reason

    return NativeTriProductOutputCertificateL0(
        status=status,
        rejection_reason=reason,
        source_output_hashes_match=source_output_hashes_match,
        route_flags_match_certificate=route_flags_match_certificate,
        source_vertices_preserved=source_vertices_preserved,
        source_faces_preserved=source_faces_preserved,
        topology_preserved=topology_preserved,
        provenance_preserved=provenance_preserved,
        source_certificate=certificate,
        accepted=False,
        mesher_success_allowed=False,
        product_claimed=False,
    )


__all__ = [
    "NativeTriProductOutputCertificateL0",
    "diagnose_native_tri_product_output_l0",
]
