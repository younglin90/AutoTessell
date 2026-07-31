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

from collections import Counter
from collections.abc import Sequence
from dataclasses import dataclass
from hashlib import sha256
from numbers import Integral
from pathlib import Path
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
_CORPUS_AUTHORITY_KINDS = frozenset({"checked_in_fixture", "cad_brep", "unknown", "synthetic"})
_SOURCE_DIGEST_CHUNK_BYTES = 1024 * 1024


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
class LocalFrontCorpusAuthorityMetadataL2:
    """One declared corpus row before sidecar or numeric evidence is read.

    ``authority_key`` identifies the sole metadata owner for a corpus input.
    ``manifest_order`` gives its explicit presentation order.  The L2 audit
    rejects ties in either field rather than letting caller iteration order
    select an arbitrary authority declaration.
    """

    authority_key: str
    manifest_order: int
    source_path: str


@dataclass(frozen=True, slots=True)
class LocalFrontAuthorityManifestAuditL2:
    """Read-only corpus-metadata result before any sidecar/preflight call."""

    status: str
    metadata_count: int
    canonical_authority_keys: tuple[str, ...]
    duplicate_authority_keys: tuple[str, ...]
    duplicate_manifest_orders: tuple[int, ...]
    sidecar_invoked: bool
    numeric_preflight_invoked: bool
    candidate_constructed: bool
    production_mesh_changed: bool
    artifact_delta: int


@dataclass(frozen=True, slots=True)
class LocalFrontCorpusSourceDigestL3:
    """Declared immutable byte identity for one already-unambiguous L2 row."""

    metadata: LocalFrontCorpusAuthorityMetadataL2
    source_file_sha256: str


@dataclass(frozen=True, slots=True)
class LocalFrontAuthoritySourceDigestAuditL3:
    """Read-only source-byte identity result before sidecar/numeric work."""

    status: str
    metadata_status: str
    metadata_count: int
    canonical_authority_keys: tuple[str, ...]
    source_file_exists: bool
    source_digest_matches: bool
    sidecar_invoked: bool
    numeric_preflight_invoked: bool
    candidate_constructed: bool
    production_mesh_changed: bool
    artifact_delta: int


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


def audit_local_front_authority_manifest_l2(
    metadata: Sequence[LocalFrontCorpusAuthorityMetadataL2],
) -> LocalFrontAuthorityManifestAuditL2:
    """Fail closed on non-unique corpus authority before any mesh evidence.

    This is intentionally narrower than :func:`audit_local_front_authority_corpus_l1`:
    it neither reads source bytes nor accepts a sidecar.  The caller must first
    establish that every authority key and explicit manifest order has one,
    deterministic owner.  Rows are canonically sorted by the declared order,
    so harmless caller iteration reordering cannot decide authority.
    """
    rows = tuple(metadata)
    invalid = any(
        not isinstance(row, LocalFrontCorpusAuthorityMetadataL2)
        or not isinstance(row.authority_key, str)
        or not isinstance(row.source_path, str)
        or not isinstance(row.manifest_order, Integral)
        or isinstance(row.manifest_order, bool)
        or not row.authority_key.strip()
        or not row.source_path.strip()
        or row.manifest_order < 0
        for row in rows
    )
    if invalid or not rows:
        return LocalFrontAuthorityManifestAuditL2(
            "reject_invalid_authority_corpus_metadata",
            len(rows),
            (),
            (),
            (),
            False,
            False,
            False,
            False,
            0,
        )
    key_counts = Counter(row.authority_key for row in rows)
    order_counts = Counter(row.manifest_order for row in rows)
    duplicate_keys = tuple(sorted(key for key, count in key_counts.items() if count > 1))
    duplicate_orders = tuple(sorted(order for order, count in order_counts.items() if count > 1))
    canonical_keys = tuple(
        row.authority_key for row in sorted(rows, key=lambda row: row.manifest_order)
    )
    if duplicate_keys:
        status = "reject_duplicate_authority_key"
    elif duplicate_orders:
        status = "reject_manifest_order_ambiguity"
    else:
        status = "pass_unambiguous_authority_corpus_metadata"
    return LocalFrontAuthorityManifestAuditL2(
        status,
        len(rows),
        canonical_keys,
        duplicate_keys,
        duplicate_orders,
        False,
        False,
        False,
        False,
        0,
    )


def _source_digest_report_l3(
    *,
    status: str,
    metadata_audit: LocalFrontAuthorityManifestAuditL2,
    source_file_exists: bool,
    source_digest_matches: bool,
) -> LocalFrontAuthoritySourceDigestAuditL3:
    """Build a fixed-shape L3 report without invoking any mesh operation."""
    return LocalFrontAuthoritySourceDigestAuditL3(
        status,
        metadata_audit.status,
        metadata_audit.metadata_count,
        metadata_audit.canonical_authority_keys,
        source_file_exists,
        source_digest_matches,
        False,
        False,
        False,
        False,
        0,
    )


def _is_canonical_sha256(value: object) -> bool:
    return bool(
        isinstance(value, str)
        and len(value) == 64
        and value == value.lower()
        and all(character in "0123456789abcdef" for character in value)
    )


def _source_file_sha256_l3(source_path: Path) -> str:
    """Hash exact source bytes with bounded memory for large mesh fixtures."""
    digest = sha256()
    with source_path.open("rb") as source_file:
        while chunk := source_file.read(_SOURCE_DIGEST_CHUNK_BYTES):
            digest.update(chunk)
    return digest.hexdigest()


def audit_local_front_authority_source_digest_l3(
    source_digests: Sequence[LocalFrontCorpusSourceDigestL3],
) -> LocalFrontAuthoritySourceDigestAuditL3:
    """Bind L2 metadata labels to immutable source bytes before sidecar work.

    File bytes are hashed directly; this function does not call a surface
    reader or parse source geometry.  A missing file, malformed declaration,
    or digest mismatch is an explicit refusal before sidecar, numeric
    preflight, or candidate construction can become eligible.
    """
    rows = tuple(source_digests)
    invalid = not rows or any(
        not isinstance(row, LocalFrontCorpusSourceDigestL3)
        or not isinstance(row.metadata, LocalFrontCorpusAuthorityMetadataL2)
        or not _is_canonical_sha256(row.source_file_sha256)
        for row in rows
    )
    if invalid:
        empty_audit = LocalFrontAuthorityManifestAuditL2(
            "reject_invalid_authority_corpus_metadata",
            0,
            (),
            (),
            (),
            False,
            False,
            False,
            False,
            0,
        )
        return _source_digest_report_l3(
            status="reject_invalid_source_digest_metadata",
            metadata_audit=empty_audit,
            source_file_exists=False,
            source_digest_matches=False,
        )
    metadata_audit = audit_local_front_authority_manifest_l2(tuple(row.metadata for row in rows))
    if metadata_audit.status != "pass_unambiguous_authority_corpus_metadata":
        return _source_digest_report_l3(
            status="reject_authority_corpus_metadata",
            metadata_audit=metadata_audit,
            source_file_exists=False,
            source_digest_matches=False,
        )
    for row in rows:
        source_path = Path(row.metadata.source_path)
        if not source_path.is_file():
            return _source_digest_report_l3(
                status="reject_source_digest_file_not_found",
                metadata_audit=metadata_audit,
                source_file_exists=False,
                source_digest_matches=False,
            )
        try:
            source_digest = _source_file_sha256_l3(source_path)
        except OSError:
            return _source_digest_report_l3(
                status="reject_source_digest_file_unreadable",
                metadata_audit=metadata_audit,
                source_file_exists=True,
                source_digest_matches=False,
            )
        if source_digest != row.source_file_sha256:
            return _source_digest_report_l3(
                status="reject_source_digest_mismatch",
                metadata_audit=metadata_audit,
                source_file_exists=True,
                source_digest_matches=False,
            )
    return _source_digest_report_l3(
        status="pass_immutable_source_digest_authority",
        metadata_audit=metadata_audit,
        source_file_exists=True,
        source_digest_matches=True,
    )


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
    if sidecar.authority_kind == "cad_brep" and not _cad_brep_is_complete(sidecar.cad_provenance):
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
