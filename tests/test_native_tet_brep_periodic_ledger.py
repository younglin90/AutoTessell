"""C34-A checks for actual seam/periodic B-Rep ledger fail-closed behavior."""

from __future__ import annotations

import hashlib
from pathlib import Path
import sys

sys.path.insert(0, "tests")
sys.path.insert(0, "/tmp/autotessell_surface_bl_front_shared_build")

from native_brep_front_evidence_v2 import (  # noqa: E402
    prepare_brep_layer_input_v2,
    validate_brep_direction_contract_v2,
)

from core.analyzer.readers.step import load_cad_native_with_provenance  # noqa: E402
from core.layers.native_tet_brep_front_evidence_v2 import (  # noqa: E402
    build_brep_front_evidence_v2,
)
from test_native_tet_brep_front_evidence_v2 import _explicit_owner_map  # noqa: E402
from test_cad_xde_physical_authority import _write_styled_box  # noqa: E402


def _actual_box_payload(source: Path) -> tuple[dict, str]:
    source_digest = hashlib.sha256(source.read_bytes()).hexdigest()
    cad = load_cad_native_with_provenance(
        source,
        ".step",
        mesh_domain_side_by_face={
            face_id: 1 for face_id in range(cad_face_count(source))
        },
    )
    return (
        build_brep_front_evidence_v2(
            cad,
            source_digest=source_digest,
            owner_face_by_edge=_explicit_owner_map(cad),
        ),
        source_digest,
    )


def cad_face_count(source: Path) -> int:
    return load_cad_native_with_provenance(source, ".step").provenance.face_count


def test_nonseam_box_records_are_periodic_ledger_complete(tmp_path: Path) -> None:
    source = tmp_path / "styled-box.step"
    _write_styled_box(source)
    payload, source_digest = _actual_box_payload(source)
    records = payload["direction_records"]
    assert records
    assert all(record["is_closed_pcurve"] is False for record in records)
    assert all(record["pcurve_branch_count"] == 1 for record in records)
    assert all(record["seam_branch_count"] == 1 for record in records)
    assert all(record["pcurve_branch_status"] == "single_branch" for record in records)
    assert all(record["period_shift"] == [0, 0] for record in records)
    assert all(record["uv_canonical"] == record["uv_point"] for record in records)
    assert all(len(record["branch_digest"]) == 64 for record in records)
    ledger = prepare_brep_layer_input_v2(payload, 1)
    contract = validate_brep_direction_contract_v2(ledger, records)
    assert contract["accepted"] is True
    assert source_digest == payload["source_digest"]


def test_unresolved_seam_branch_is_refused_before_direction_acceptance(tmp_path: Path) -> None:
    source = tmp_path / "styled-box.step"
    _write_styled_box(source)
    payload, _ = _actual_box_payload(source)
    ledger = prepare_brep_layer_input_v2(payload, 1)
    record = dict(payload["direction_records"][0])
    record.update(
        {
            "is_closed_pcurve": True,
            "pcurve_branch_count": 2,
            "seam_branch_count": 2,
            "pcurve_branch_status": "seam_branches_unresolved",
            "trimmed_interior_status": "one_side_certified",
        }
    )
    records = [record, *payload["direction_records"][1:]]
    contract = validate_brep_direction_contract_v2(ledger, records)
    assert contract["accepted"] is False
    assert contract["reason"] == "pcurve_branch_unresolved"
