"""Fail-closed evidence for generated Hex boundary-face source bindings.

The current native Hex mesher has no emitted boundary-face to source-B-Rep
mapping.  Input-side CAD provenance therefore cannot certify an output mesh.
This disconnected adapter defines the exact binding payload a future writer
must emit and keeps every result non-accepting, including syntactically
complete fixture evidence.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from hashlib import sha256

import numpy as np

from core.analyzer.readers.step import CadEntityProvenance

_MISSING_ALL = (
    "source_brep",
    "output_boundary_face_to_source_brep",
    "physical_group",
)


@dataclass(frozen=True, slots=True)
class HexOutputSourceBindingCertificateL0:
    """One non-accepting output-binding report; never Hex success evidence."""

    status: str
    source_brep_complete: bool
    source_physical_groups_authoritative: bool
    output_boundary_face_count: int
    source_face_mapping_complete: bool
    physical_group_mapping_complete: bool
    strict_binding_complete: bool
    output_boundary_face_ids_sha256: str | None
    output_to_source_face_sha256: str | None
    output_physical_group_sha256: str | None
    missing_evidence: tuple[str, ...]
    malformed_evidence: tuple[str, ...]
    accepted: bool
    mesher_success_allowed: bool
    product_claimed: bool
    rejection_reason: str
    contract: str = "native_hex_output_source_binding_certificate_l0"


def _canonical_ids(value: object) -> np.ndarray | None:
    if (
        not isinstance(value, np.ndarray)
        or value.dtype != np.dtype(np.int64)
        or value.ndim != 1
        or not value.flags.c_contiguous
        or len(value) == 0
        or (value < 0).any()
        or np.any(value[1:] <= value[:-1])
    ):
        return None
    return value


def _canonical_source_ordinals(value: object, count: int, face_count: int) -> np.ndarray | None:
    if (
        not isinstance(value, np.ndarray)
        or value.dtype != np.dtype(np.int64)
        or value.ndim != 1
        or not value.flags.c_contiguous
        or len(value) != count
        or (value < 0).any()
        or (value >= face_count).any()
    ):
        return None
    return value


def _canonical_groups(value: object, count: int) -> tuple[str, ...] | None:
    if not isinstance(value, (tuple, list)) or len(value) != count:
        return None
    if not all(isinstance(name, str) and name.strip() for name in value):
        return None
    return tuple(value)


def _source_brep_complete(provenance: CadEntityProvenance) -> bool:
    return bool(
        provenance.face_count > 0
        and provenance.topological_edge_count > 0
        and provenance.face_ordinals_authoritative
        and provenance.face_orientation_authoritative
        and provenance.seam_connectivity_authoritative
    )


def _source_groups_complete(provenance: CadEntityProvenance) -> bool:
    return bool(
        provenance.physical_groups_authoritative
        and len(provenance.physical_group_names) == provenance.face_count
        and all(isinstance(name, str) and name.strip() for name in provenance.physical_group_names)
    )


def _array_hash(value: np.ndarray | None) -> str | None:
    if value is None:
        return None
    digest = sha256()
    digest.update(str(value.dtype).encode("ascii"))
    digest.update(np.asarray(value.shape, dtype=np.int64).tobytes())
    digest.update(value.tobytes())
    return digest.hexdigest()


def _group_hash(value: tuple[str, ...] | None) -> str | None:
    if value is None:
        return None
    return sha256(json.dumps(value, ensure_ascii=True, separators=(",", ":")).encode("utf-8")).hexdigest()


def _report(
    *,
    status: str,
    source_brep_complete: bool,
    source_groups_authoritative: bool,
    output_ids: np.ndarray | None,
    source_ordinals: np.ndarray | None,
    groups: tuple[str, ...] | None,
    source_mapping_complete: bool,
    physical_mapping_complete: bool,
    missing: tuple[str, ...],
    malformed: tuple[str, ...],
    rejection_reason: str,
) -> HexOutputSourceBindingCertificateL0:
    return HexOutputSourceBindingCertificateL0(
        status=status,
        source_brep_complete=source_brep_complete,
        source_physical_groups_authoritative=source_groups_authoritative,
        output_boundary_face_count=0 if output_ids is None else len(output_ids),
        source_face_mapping_complete=source_mapping_complete,
        physical_group_mapping_complete=physical_mapping_complete,
        strict_binding_complete=source_mapping_complete and physical_mapping_complete,
        output_boundary_face_ids_sha256=_array_hash(output_ids),
        output_to_source_face_sha256=_array_hash(source_ordinals),
        output_physical_group_sha256=_group_hash(groups),
        missing_evidence=missing,
        malformed_evidence=malformed,
        accepted=False,
        mesher_success_allowed=False,
        product_claimed=False,
        rejection_reason=rejection_reason,
    )


def diagnose_hex_output_source_binding_l0(
    source_provenance: object,
    output_boundary_face_ids: object,
    output_to_source_face_ordinals: object,
    output_physical_groups: object,
) -> HexOutputSourceBindingCertificateL0:
    """Diagnose output binding completeness without authorizing Hex success.

    A caller must supply one sorted unique output boundary-face ID and one
    authoritative source B-Rep face ordinal per generated output face.  Every
    emitted physical-group name must exactly equal its mapped source-face
    group.  Complete binding is still unverified product evidence: output
    surface geometry, feature, and topology checks remain separate hard gates.
    """
    if not isinstance(source_provenance, CadEntityProvenance):
        return _report(
            status="reject_invalid_source_brep_provenance",
            source_brep_complete=False,
            source_groups_authoritative=False,
            output_ids=None,
            source_ordinals=None,
            groups=None,
            source_mapping_complete=False,
            physical_mapping_complete=False,
            missing=_MISSING_ALL,
            malformed=(),
            rejection_reason="hex_output_source_binding_required",
        )

    brep_complete = _source_brep_complete(source_provenance)
    groups_authoritative = _source_groups_complete(source_provenance)
    if not brep_complete:
        return _report(
            status="reject_incomplete_source_brep_authority",
            source_brep_complete=False,
            source_groups_authoritative=False,
            output_ids=None,
            source_ordinals=None,
            groups=None,
            source_mapping_complete=False,
            physical_mapping_complete=False,
            missing=_MISSING_ALL,
            malformed=(),
            rejection_reason="hex_output_source_binding_required",
        )
    if not groups_authoritative:
        return _report(
            status="reject_source_physical_groups_unavailable",
            source_brep_complete=True,
            source_groups_authoritative=False,
            output_ids=None,
            source_ordinals=None,
            groups=None,
            source_mapping_complete=False,
            physical_mapping_complete=False,
            missing=("physical_group",),
            malformed=(),
            rejection_reason="hex_output_source_binding_required",
        )

    output_ids = _canonical_ids(output_boundary_face_ids)
    if output_ids is None:
        return _report(
            status="reject_output_boundary_face_ids_invalid",
            source_brep_complete=True,
            source_groups_authoritative=True,
            output_ids=None,
            source_ordinals=None,
            groups=None,
            source_mapping_complete=False,
            physical_mapping_complete=False,
            missing=("output_boundary_face_to_source_brep", "physical_group"),
            malformed=("output_boundary_face_ids",),
            rejection_reason="hex_output_source_binding_required",
        )
    ordinals = _canonical_source_ordinals(
        output_to_source_face_ordinals,
        len(output_ids),
        source_provenance.face_count,
    )
    if ordinals is None:
        return _report(
            status="reject_output_source_face_mapping_invalid",
            source_brep_complete=True,
            source_groups_authoritative=True,
            output_ids=output_ids,
            source_ordinals=None,
            groups=None,
            source_mapping_complete=False,
            physical_mapping_complete=False,
            missing=("output_boundary_face_to_source_brep", "physical_group"),
            malformed=("output_boundary_face_to_source_brep",),
            rejection_reason="hex_output_source_binding_required",
        )
    groups = _canonical_groups(output_physical_groups, len(output_ids))
    if groups is None:
        return _report(
            status="reject_output_physical_group_mapping_invalid",
            source_brep_complete=True,
            source_groups_authoritative=True,
            output_ids=output_ids,
            source_ordinals=ordinals,
            groups=None,
            source_mapping_complete=True,
            physical_mapping_complete=False,
            missing=("physical_group",),
            malformed=("output_physical_group",),
            rejection_reason="hex_output_source_binding_required",
        )
    expected_groups = tuple(source_provenance.physical_group_names[int(face)] for face in ordinals)
    if groups != expected_groups:
        return _report(
            status="reject_output_physical_group_mapping_mismatch",
            source_brep_complete=True,
            source_groups_authoritative=True,
            output_ids=output_ids,
            source_ordinals=ordinals,
            groups=groups,
            source_mapping_complete=True,
            physical_mapping_complete=False,
            missing=(),
            malformed=("output_physical_group",),
            rejection_reason="hex_output_source_binding_required",
        )
    return _report(
        status="report_hex_output_source_binding_complete_unverified",
        source_brep_complete=True,
        source_groups_authoritative=True,
        output_ids=output_ids,
        source_ordinals=ordinals,
        groups=groups,
        source_mapping_complete=True,
        physical_mapping_complete=True,
        missing=(),
        malformed=(),
        rejection_reason="hex_output_product_certificate_required",
    )


__all__ = [
    "HexOutputSourceBindingCertificateL0",
    "diagnose_hex_output_source_binding_l0",
]
