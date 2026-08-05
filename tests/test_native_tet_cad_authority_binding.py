"""CAD B-Rep binding evidence for the user-declared Native Tet ledger."""

from __future__ import annotations

import json
from pathlib import Path

from core.layers.native_tet_cad_authority_binding import bind_tet_cad_source


def test_t_junction_cad_brep_identity_binds_without_promoting_physical_groups() -> None:
    ledger = json.loads(Path("docs/qa/authority/native_tet_surface_source_ledgers_v1.json").read_text())
    entry = next(item for item in ledger["sources"] if item["case"] == "t-junction-cad")
    report = bind_tet_cad_source(entry["path"], entry)
    print(report)
    assert report["status"] == "USER_DECLARED_PROVISIONAL_BREP_BOUND", report
    assert report["face_count"] == 12
    assert report["topological_edge_count"] > 0
    assert report["face_orientation_authoritative"] is True
    assert report["seam_connectivity_authoritative"] is True
    assert report["physical_groups_authoritative"] is False
    assert report["display_metadata_promoted"] is False
    assert report["release_eligible"] is False
