"""Fail-closed CAD/B-Rep source authority audit.

XDE layers/colors/names are preserved as CAD metadata, not promoted to
physical boundary-condition groups. This module only audits existing reader
payloads; it does not repair or infer mappings.
"""
from __future__ import annotations

import hashlib
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np

from core.analyzer.readers.step import load_cad_native_with_provenance


@dataclass(frozen=True, slots=True)
class CadReleaseAuthorityAudit:
    authoritative: bool
    status: str
    reason: str
    source_sha256: str | None
    reader_payload_sha256: str | None
    brep_identity_bound: bool
    physical_groups_authoritative: bool
    xde_metadata_sha256: str | None

    def as_dict(self) -> dict[str, object]:
        return {
            "authoritative": self.authoritative,
            "status": self.status,
            "reason": self.reason,
            "source_sha256": self.source_sha256,
            "reader_payload_sha256": self.reader_payload_sha256,
            "cad_brep_identity_bound": self.brep_identity_bound,
            "physical_groups_authoritative": self.physical_groups_authoritative,
            "xde_metadata_sha256": self.xde_metadata_sha256,
        }


def _file_sha256(path: Path) -> str | None:
    if path.is_symlink() or not path.is_file():
        return None
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _array_sha256(value: object) -> str:
    array = np.ascontiguousarray(np.asarray(value))
    digest = hashlib.sha256()
    digest.update(array.dtype.str.encode("ascii"))
    digest.update(np.asarray(array.shape, dtype="<i8").tobytes())
    digest.update(array.tobytes(order="C"))
    return digest.hexdigest()


def _payload_sha256(provenance: Any) -> str:
    fields = {
        "face_ordinals": _array_sha256(provenance.triangle_face_ordinals),
        "orientation": _array_sha256(provenance.triangle_orientation_reversed),
        "seam": _array_sha256(provenance.seam_vertex_ids),
        "ordered_triangles": provenance.ordered_triangle_coordinate_sha256,
        "ordered_faces": provenance.ordered_face_ordinal_sha256,
        "ordered_orientation": provenance.ordered_orientation_sha256,
        "seam_hash": provenance.seam_connectivity_sha256,
        "xde": provenance.xde_metadata_sha256,
    }
    return hashlib.sha256(repr(sorted(fields.items())).encode("utf-8")).hexdigest()


def audit_cad_release_authority(
    source_path: str | Path,
    source_vertices: object,
    source_faces: object,
    source_provenance: Any,
) -> CadReleaseAuthorityAudit:
    path = Path(source_path)
    source_sha = _file_sha256(path)
    if source_sha is None:
        return CadReleaseAuthorityAudit(False, "unverified", "cad_source_file_invalid", None, None, False, False, None)
    try:
        reread = load_cad_native_with_provenance(path, path.suffix.lower() or ".step")
    except Exception as exc:  # noqa: BLE001
        return CadReleaseAuthorityAudit(False, "unverified", f"cad_source_readback_failed:{type(exc).__name__}", source_sha, None, False, False, None)
    prov = reread.provenance
    same_arrays = bool(
        np.array_equal(np.asarray(source_vertices), np.asarray(reread.vertices))
        and np.array_equal(np.asarray(source_faces), np.asarray(reread.faces))
    )
    same_payload = source_provenance is not None and all(
        getattr(source_provenance, name, None) == getattr(prov, name, None)
        for name in (
            "ordered_triangle_coordinate_sha256",
            "ordered_face_ordinal_sha256",
            "ordered_orientation_sha256",
            "seam_connectivity_sha256",
            "xde_metadata_sha256",
        )
    )
    identity = bool(
        same_arrays and same_payload and prov.face_ordinals_authoritative
        and prov.face_orientation_authoritative and prov.seam_connectivity_authoritative
    )
    reader_payload = _payload_sha256(prov)
    if not identity:
        return CadReleaseAuthorityAudit(
            False, "unverified", "reject_cad_provenance_identity_mismatch",
            source_sha, reader_payload, False, bool(prov.physical_groups_authoritative),
            prov.xde_metadata_sha256,
        )
    if not prov.physical_groups_authoritative:
        return CadReleaseAuthorityAudit(
            False, "unverified", "cad_physical_group_mapping_missing",
            source_sha, reader_payload, True, False, prov.xde_metadata_sha256,
        )
    return CadReleaseAuthorityAudit(
        True, "measured_authoritative_cad", "", source_sha, reader_payload,
        True, True, prov.xde_metadata_sha256,
    )


__all__ = ["CadReleaseAuthorityAudit", "audit_cad_release_authority"]
