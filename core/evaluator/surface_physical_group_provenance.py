"""Fail-closed physical-group mapping evidence for future surface products."""

from __future__ import annotations

import json
from dataclasses import dataclass
from hashlib import sha256


@dataclass(frozen=True, slots=True)
class AuthoritativePhysicalGroupMapping:
    """Explicit source-face-to-physical-group declaration, never inferred."""

    source_face_groups: tuple[str, ...]
    authoritative: bool


@dataclass(frozen=True, slots=True)
class PhysicalGroupProvenanceReport:
    status: str
    physical_group_sha256: str | None
    missing_evidence: tuple[str, ...]
    malformed_evidence: tuple[str, ...]
    product_accepted: bool
    candidate_constructed: bool
    production_mesh_changed: bool
    artifact_delta: int


def report_surface_physical_group_provenance(
    source_face_count: object,
    mapping: object,
) -> PhysicalGroupProvenanceReport:
    """Bind only an explicit authoritative face mapping; never accept product."""
    if (
        isinstance(source_face_count, bool)
        or not isinstance(source_face_count, int)
        or source_face_count <= 0
    ):
        return PhysicalGroupProvenanceReport(
            "reject_invalid_source_face_count",
            None,
            ("physical_group",),
            (),
            False,
            False,
            False,
            0,
        )
    if not isinstance(mapping, AuthoritativePhysicalGroupMapping) or not mapping.authoritative:
        return PhysicalGroupProvenanceReport(
            "defer_missing_explicit_physical_group_mapping",
            None,
            ("physical_group",),
            (),
            False,
            False,
            False,
            0,
        )
    if len(mapping.source_face_groups) != source_face_count or not all(
        isinstance(group, str) and group.strip() for group in mapping.source_face_groups
    ):
        return PhysicalGroupProvenanceReport(
            "reject_invalid_physical_group_mapping",
            None,
            (),
            ("physical_group",),
            False,
            False,
            False,
            0,
        )
    digest = sha256(
        json.dumps(
            mapping.source_face_groups,
            ensure_ascii=True,
            separators=(",", ":"),
        ).encode("utf-8")
    ).hexdigest()
    return PhysicalGroupProvenanceReport(
        "report_authoritative_physical_group_mapping_unverified",
        digest,
        (),
        (),
        False,
        False,
        False,
        0,
    )
