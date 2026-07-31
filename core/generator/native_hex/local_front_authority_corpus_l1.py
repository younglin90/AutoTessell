"""L1 corpus authority gate for the disconnected native-hex local-front audit.

This module classifies a *corpus sidecar*, not mesh geometry.  It deliberately
keeps caller-supplied manifests in :mod:`source_feature_sidecar_l1` unchanged:
that generic contract binds bytes and face order but cannot establish how a
caller obtained the labels.  The corpus gate therefore permits a local-front
preflight only for a checked-in fixture authority or complete CAD B-Rep
authority.  Unknown and synthetic sidecars fail before the preflight.

No mesher, shell constructor, writer, router, or filesystem output is imported
or called here.  This is report-only ``CORRECTNESS_KEEP`` infrastructure.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

import numpy as np

from core.analyzer.readers.step import CadEntityProvenance

from .local_front_admission_l0 import LocalFrontAdmissionL0, audit_local_front_admission_l0
from .source_feature_sidecar_l1 import (
    AuthoritativeSourceFeatureManifest,
    SourceFeatureSidecarAudit,
    audit_authoritative_source_feature_sidecar_l1,
)

CorpusAuthorityKind = Literal[
    "checked_in_fixture",
    "cad_brep",
    "unknown",
    "synthetic",
]
_CORPUS_AUTHORITY_KINDS = frozenset(
    {"checked_in_fixture", "cad_brep", "unknown", "synthetic"}
)


@dataclass(frozen=True, slots=True)
class LocalFrontCorpusSidecarL1:
    """Declared provenance class for one immutable L1 corpus input.

    ``checked_in_fixture`` is restricted to a reviewable test fixture.  A
    ``cad_brep`` sidecar requires immutable OCP B-Rep face, orientation, and
    seam metadata.  Neither kind fabricates physical-group semantics.
    """

    authority_kind: CorpusAuthorityKind
    manifest: AuthoritativeSourceFeatureManifest | None
    physical_groups_authoritative: bool
    cad_provenance: CadEntityProvenance | None = None


@dataclass(frozen=True, slots=True)
class LocalFrontAuthorityCorpusAuditL1:
    """Read-only authority/preflight result; no candidate or artifact exists."""

    status: str
    authority_kind: CorpusAuthorityKind
    sidecar_status: str | None
    source_face_count: int
    two_manifold_edge_count: int
    entity_boundary_edge_count: int
    cad_face_count: int | None
    cad_topological_edge_count: int | None
    physical_groups_authoritative: bool
    preflight_invoked: bool
    preflight_status: str | None
    preflight_admitted: bool
    source_geometry_unchanged: bool
    candidate_constructed: bool
    production_mesh_changed: bool
    artifact_delta: int


def _cad_brep_is_complete(provenance: CadEntityProvenance | None) -> bool:
    """Accept only the explicit B-Rep identities needed by this corpus gate."""
    return bool(
        provenance is not None
        and provenance.face_count > 0
        and provenance.topological_edge_count > 0
        and provenance.face_ordinals_authoritative
        and provenance.face_orientation_authoritative
        and provenance.seam_connectivity_authoritative
    )


def _report(
    *,
    status: str,
    sidecar: LocalFrontCorpusSidecarL1,
    sidecar_audit: SourceFeatureSidecarAudit | None,
    preflight: LocalFrontAdmissionL0 | None,
) -> LocalFrontAuthorityCorpusAuditL1:
    """Build one fixed-shape report without constructing mesh state."""
    provenance = sidecar_audit.provenance if sidecar_audit is not None else None
    cad = sidecar.cad_provenance
    return LocalFrontAuthorityCorpusAuditL1(
        status=status,
        authority_kind=sidecar.authority_kind,
        sidecar_status=sidecar_audit.status if sidecar_audit is not None else None,
        source_face_count=provenance.source_face_count if provenance is not None else 0,
        two_manifold_edge_count=provenance.two_manifold_edge_count if provenance is not None else 0,
        entity_boundary_edge_count=(
            len(provenance.entity_boundaries) if provenance is not None else 0
        ),
        cad_face_count=cad.face_count if cad is not None else None,
        cad_topological_edge_count=cad.topological_edge_count if cad is not None else None,
        physical_groups_authoritative=sidecar.physical_groups_authoritative,
        preflight_invoked=preflight is not None,
        preflight_status=preflight.status if preflight is not None else None,
        preflight_admitted=preflight.admitted if preflight is not None else False,
        source_geometry_unchanged=(
            sidecar_audit.source_geometry_unchanged if sidecar_audit is not None else True
        ),
        candidate_constructed=False,
        production_mesh_changed=False,
        artifact_delta=0,
    )


def audit_local_front_authority_corpus_l1(
    vertices: np.ndarray,
    faces: np.ndarray,
    *,
    source_path: str,
    sidecar: LocalFrontCorpusSidecarL1,
    requested_step: float,
) -> LocalFrontAuthorityCorpusAuditL1:
    """Run local-front preflight only after corpus authority is established.

    CAD source identity alone does not claim a physical group.  A CAD corpus
    row with unknown physical groups therefore returns an explicit rejection
    after validating its sidecar, without running the costly numerical
    clearance preflight or constructing any candidate.
    """
    if sidecar.authority_kind not in _CORPUS_AUTHORITY_KINDS:
        return _report(
            status="reject_unknown_corpus_authority_kind",
            sidecar=sidecar,
            sidecar_audit=None,
            preflight=None,
        )
    if sidecar.authority_kind in {"unknown", "synthetic"}:
        return _report(
            status="reject_non_authoritative_corpus_sidecar",
            sidecar=sidecar,
            sidecar_audit=None,
            preflight=None,
        )
    if sidecar.manifest is None:
        return _report(
            status="reject_missing_authoritative_corpus_manifest",
            sidecar=sidecar,
            sidecar_audit=None,
            preflight=None,
        )
    if sidecar.authority_kind == "cad_brep" and not _cad_brep_is_complete(
        sidecar.cad_provenance
    ):
        return _report(
            status="reject_incomplete_cad_brep_authority",
            sidecar=sidecar,
            sidecar_audit=None,
            preflight=None,
        )

    sidecar_audit = audit_authoritative_source_feature_sidecar_l1(
        vertices,
        faces,
        source_path=source_path,
        manifest=sidecar.manifest,
    )
    if sidecar_audit.status != "pass_authoritative_feature_sidecar":
        return _report(
            status="reject_authoritative_corpus_sidecar_identity",
            sidecar=sidecar,
            sidecar_audit=sidecar_audit,
            preflight=None,
        )
    if not sidecar.physical_groups_authoritative:
        return _report(
            status="reject_cad_physical_groups_unknown",
            sidecar=sidecar,
            sidecar_audit=sidecar_audit,
            preflight=None,
        )

    preflight = audit_local_front_admission_l0(
        vertices,
        faces,
        source_path=source_path,
        manifest=sidecar.manifest,
        requested_step=requested_step,
    )
    return _report(
        status=(
            "pass_authoritative_local_front_preflight"
            if preflight.admitted
            else "reject_authoritative_local_front_preflight"
        ),
        sidecar=sidecar,
        sidecar_audit=sidecar_audit,
        preflight=preflight,
    )
