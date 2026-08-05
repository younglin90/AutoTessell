"""Read-only binding of user-declared CAD ledger entries to B-Rep evidence."""

from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any, Mapping

from core.analyzer.readers.step import load_cad_native_with_provenance


def bind_tet_cad_source(path: str | Path, ledger_entry: Mapping[str, Any]) -> dict[str, Any]:
    source = Path(path)
    raw_hash = hashlib.sha256(source.read_bytes()).hexdigest()
    if raw_hash != ledger_entry.get("sha256"):
        return {"status": "UNVERIFIED", "reason": "source_hash_mismatch", "release_eligible": False}
    try:
        triangulation = load_cad_native_with_provenance(source, ".step")
    except (ImportError, OSError, ValueError) as exc:
        return {"status": "UNVERIFIED", "reason": f"cad_provenance_unavailable:{type(exc).__name__}", "release_eligible": False}
    provenance = triangulation.provenance
    face_count_ok = provenance.face_count == int(ledger_entry.get("entity_count", -1))
    brep_identity = bool(
        face_count_ok
        and provenance.topological_edge_count > 0
        and provenance.face_ordinals_authoritative
        and provenance.face_orientation_authoritative
        and provenance.seam_connectivity_authoritative
    )
    return {
        "status": "USER_DECLARED_PROVISIONAL_BREP_BOUND" if brep_identity else "UNVERIFIED",
        "reason": "reader_identity_bound_physical_group_still_provisional" if brep_identity else "brep_identity_incomplete",
        "release_eligible": False,
        "source_sha256": raw_hash,
        "face_count": provenance.face_count,
        "topological_edge_count": provenance.topological_edge_count,
        "face_ordinals_authoritative": provenance.face_ordinals_authoritative,
        "face_orientation_authoritative": provenance.face_orientation_authoritative,
        "seam_connectivity_authoritative": provenance.seam_connectivity_authoritative,
        "ordered_face_ordinal_sha256": provenance.ordered_face_ordinal_sha256,
        "ordered_orientation_sha256": provenance.ordered_orientation_sha256,
        "seam_connectivity_sha256": provenance.seam_connectivity_sha256,
        "physical_groups_authoritative": provenance.physical_groups_authoritative,
        "display_metadata_promoted": False,
    }
