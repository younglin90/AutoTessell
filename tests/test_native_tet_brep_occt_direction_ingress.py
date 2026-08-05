"""Actual OCP edge/p-curve/surface ingress evidence for round 032 C32-A."""

from __future__ import annotations

import hashlib
from pathlib import Path
import sys

sys.path.insert(0, "tests")
sys.path.insert(0, "/tmp/autotessell_surface_bl_front_shared_build")

import numpy as np
from native_brep_front_evidence_v2 import (
    prepare_brep_layer_input_v2,
    validate_brep_direction_contract_v2,
)

from core.analyzer.readers.step import load_cad_native_with_provenance
from core.layers.native_tet_brep_front_evidence_v2 import build_brep_front_evidence_v2
from test_native_tet_brep_front_evidence_v2 import _explicit_owner_map
from test_cad_xde_physical_authority import _write_styled_box


def test_actual_occt_direction_ingress_has_24_edge_face_records(tmp_path: Path) -> None:
    source = tmp_path / "styled-box.step"
    _write_styled_box(source)
    source_digest = hashlib.sha256(source.read_bytes()).hexdigest()
    cad = load_cad_native_with_provenance(
        source,
        ".step",
        mesh_domain_side_by_face={face_id: 1 for face_id in range(cad_face_count(source))},
    )
    records = cad.provenance.brep_edge_face_direction_records
    assert records is not None
    assert len(records) == 24
    assert all(record["domain_side_authoritative"] for record in records)
    assert all(record["trimmed_interior_status"] == "one_side_certified" for record in records)
    assert all(
        all(
            {probe["plus"], probe["minus"]} == {"TopAbs_IN", "TopAbs_OUT"}
            and probe["plus_restriction"] not in {"TopAbs_ON", "TopAbs_UNKNOWN"}
            and probe["minus_restriction"] not in {"TopAbs_ON", "TopAbs_UNKNOWN"}
            for probe in record["probe_results"]
        )
        for record in records
    )
    assert max(float(record["surface_residual"]) for record in records) < 1.0e-6
    assert all(np.linalg.norm(record["edge_tangent"]) > 0.0 for record in records)

    payload = build_brep_front_evidence_v2(
        cad,
        source_digest=source_digest,
        owner_face_by_edge=_explicit_owner_map(cad),
    )
    assert len(payload["direction_records"]) == 24
    assert payload["direction_authority"] is True
    ledger = prepare_brep_layer_input_v2(payload, 1)
    contract = validate_brep_direction_contract_v2(ledger, payload["direction_records"])
    assert contract["accepted"] is True
    assert all(record["source_digest"] == source_digest for record in payload["direction_records"])


def cad_face_count(source: Path) -> int:
    cad = load_cad_native_with_provenance(source, ".step")
    return cad.provenance.face_count
