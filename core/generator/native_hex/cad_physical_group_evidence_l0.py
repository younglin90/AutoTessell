"""Report-only distinction between CAD B-Rep and physical-group authority.

CAD face ordinals, orientation, and seam connectivity can be complete without
authorizing a CFD physical group.  This diagnostic keeps that gap explicit;
it does not infer a group from names, layers, colours, geometry, or assembly
metadata and never constructs a local-front candidate.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from hashlib import sha256

from core.analyzer.readers.step import CadEntityProvenance


@dataclass(frozen=True, slots=True)
class CadPhysicalGroupEvidenceReport:
    """Fail-closed CAD metadata evidence; never a product acceptance."""

    status: str
    cad_brep_complete: bool
    physical_groups_declared_authoritative: bool
    physical_group_name_count: int
    physical_group_evidence_sha256: str | None
    missing_evidence: tuple[str, ...]
    malformed_evidence: tuple[str, ...]
    product_accepted: bool
    candidate_constructed: bool
    production_mesh_changed: bool
    artifact_delta: int


def _cad_brep_complete(provenance: CadEntityProvenance) -> bool:
    return bool(
        provenance.face_count > 0
        and provenance.topological_edge_count > 0
        and provenance.face_ordinals_authoritative
        and provenance.face_orientation_authoritative
        and provenance.seam_connectivity_authoritative
    )


def _physical_groups_are_declared(provenance: CadEntityProvenance) -> bool:
    names = provenance.physical_group_names
    return bool(
        provenance.physical_groups_authoritative
        and len(names) == provenance.face_count
        and all(isinstance(name, str) and name.strip() for name in names)
    )


def _report(
    *,
    status: str,
    cad_brep_complete: bool,
    physical_groups_declared_authoritative: bool,
    physical_group_name_count: int,
    physical_group_evidence_sha256: str | None,
    missing_evidence: tuple[str, ...],
    malformed_evidence: tuple[str, ...],
) -> CadPhysicalGroupEvidenceReport:
    return CadPhysicalGroupEvidenceReport(
        status,
        cad_brep_complete,
        physical_groups_declared_authoritative,
        physical_group_name_count,
        physical_group_evidence_sha256,
        missing_evidence,
        malformed_evidence,
        False,
        False,
        False,
        0,
    )


def diagnose_cad_physical_group_evidence(
    provenance: object,
) -> CadPhysicalGroupEvidenceReport:
    """Report the physical-group authority gap without inferring semantics."""
    if not isinstance(provenance, CadEntityProvenance):
        return _report(
            status="reject_invalid_cad_provenance",
            cad_brep_complete=False,
            physical_groups_declared_authoritative=False,
            physical_group_name_count=0,
            physical_group_evidence_sha256=None,
            missing_evidence=("cad_brep", "physical_group"),
            malformed_evidence=(),
        )
    brep_complete = _cad_brep_complete(provenance)
    name_count = len(provenance.physical_group_names)
    if not brep_complete:
        return _report(
            status="reject_incomplete_cad_brep_authority",
            cad_brep_complete=False,
            physical_groups_declared_authoritative=False,
            physical_group_name_count=name_count,
            physical_group_evidence_sha256=None,
            missing_evidence=("cad_brep", "physical_group"),
            malformed_evidence=(),
        )
    if not provenance.physical_groups_authoritative:
        return _report(
            status="reject_cad_physical_groups_unknown",
            cad_brep_complete=True,
            physical_groups_declared_authoritative=False,
            physical_group_name_count=name_count,
            physical_group_evidence_sha256=None,
            missing_evidence=("physical_group",),
            malformed_evidence=(),
        )
    if not _physical_groups_are_declared(provenance):
        return _report(
            status="reject_invalid_cad_physical_group_payload",
            cad_brep_complete=True,
            physical_groups_declared_authoritative=False,
            physical_group_name_count=name_count,
            physical_group_evidence_sha256=None,
            missing_evidence=(),
            malformed_evidence=("physical_group",),
        )
    digest = sha256(
        json.dumps(
            provenance.physical_group_names,
            ensure_ascii=True,
            separators=(",", ":"),
        ).encode("utf-8")
    ).hexdigest()
    return _report(
        status="report_cad_physical_groups_authoritative_unverified",
        cad_brep_complete=True,
        physical_groups_declared_authoritative=True,
        physical_group_name_count=name_count,
        physical_group_evidence_sha256=digest,
        missing_evidence=(),
        malformed_evidence=(),
    )
