"""C++ authority contract tests for round 031 C31-A."""

from __future__ import annotations

import hashlib
import sys
from pathlib import Path

import pytest

sys.path.insert(0, "/tmp/autotessell_surface_bl_front_shared_build")
from native_brep_front_evidence_v2 import (  # noqa: E402
    prepare_brep_layer_input_v2,
    validate_brep_direction_contract_v2,
)

from core.analyzer.readers.step import load_cad_native_with_provenance
from core.layers.native_tet_brep_front_evidence_v2 import build_brep_front_evidence_v2
from tests.test_native_tet_brep_front_evidence_v2 import _explicit_owner_map
from tests.test_cad_xde_physical_authority import _write_styled_box


def _ledger(tmp_path: Path) -> dict:
    source = tmp_path / "styled-box.step"
    _write_styled_box(source)
    cad = load_cad_native_with_provenance(source, ".step")
    payload = build_brep_front_evidence_v2(
        cad,
        source_digest=hashlib.sha256(source.read_bytes()).hexdigest(),
        owner_face_by_edge=_explicit_owner_map(cad),
    )
    return prepare_brep_layer_input_v2(payload, 1)


def _records(ledger: dict) -> list[dict]:
    return [
        {
            "sector_id": sector["sector_id"],
            "edge_tangent": [1.0, 0.0, 0.0],
            "face_normal": [0.0, 0.0, 1.0],
            "surface_du": [1.0, 0.0, 0.0],
            "surface_dv": [0.0, 1.0, 0.0],
            "uv_point": [0.5, 0.5],
            "uv_inward": [0.0, 1.0],
            "domain_side": 1,
            "trimmed_interior_status": "one_side_certified",
            "pcurve_digest": "a" * 64,
            "surface_digest": "b" * 64,
            "certificate_digest": "c" * 64,
            "pcurve_branch_rank": 0,
            "pcurve_branch_count": 1,
            "seam_branch_count": 1,
            "pcurve_branch_status": "single_branch",
            "is_closed_pcurve": False,
            "period_shift": [0, 0],
            "uv_canonical": [0.5, 0.5],
            "effective_occurrence_reversed": False,
            "branch_digest": "d" * 64,
        }
        for sector in ledger["sectors"]
    ]


def test_cpp_direction_contract_requires_explicit_authority(tmp_path: Path) -> None:
    ledger = _ledger(tmp_path)
    result = validate_brep_direction_contract_v2(ledger, _records(ledger))
    assert result["accepted"] is True
    assert result["schema"] == "AuthoritativeBrepLayerSector/v2"
    assert result["sector_count"] == 24
    assert result["domain_side_is_explicit"] is True


@pytest.mark.parametrize(
    ("field", "value", "reason"),
    [
        ("domain_side", 0, "domain_side_invalid"),
        ("trimmed_interior_status", "ambiguous", "trimmed_interior_uncertain"),
        ("pcurve_digest", "short", "direction_digest_invalid"),
    ],
)
def test_cpp_direction_contract_fails_closed(tmp_path: Path, field, value, reason) -> None:
    ledger = _ledger(tmp_path)
    records = _records(ledger)
    records[0][field] = value
    result = validate_brep_direction_contract_v2(ledger, records)
    assert result["accepted"] is False
    assert result["reason"] == reason
