"""C++ authoritative wall-edge sector ledger tests for round 030 C30-A."""

from __future__ import annotations

import hashlib
import sys
from pathlib import Path

sys.path.insert(0, "/tmp/autotessell_surface_bl_front_shared_build")
from native_brep_front_evidence_v2 import (  # noqa: E402
    prepare_brep_layer_input_v2,
    validate_brep_front_evidence_v2,
)

from core.analyzer.readers.step import load_cad_native_with_provenance
from core.layers.native_tet_brep_front_evidence_v2 import build_brep_front_evidence_v2
from tests.test_native_tet_brep_front_evidence_v2 import _explicit_owner_map
from tests.test_cad_xde_physical_authority import _write_styled_box


def _payload(tmp_path: Path) -> dict:
    source = tmp_path / "styled-box.step"
    _write_styled_box(source)
    cad = load_cad_native_with_provenance(source, ".step")
    return build_brep_front_evidence_v2(
        cad,
        source_digest=hashlib.sha256(source.read_bytes()).hexdigest(),
        owner_face_by_edge=_explicit_owner_map(cad),
    )


def test_cpp_layer_input_emits_actual_edge_face_segment_sectors(tmp_path: Path) -> None:
    payload = _payload(tmp_path)
    assert validate_brep_front_evidence_v2(payload)["accepted"] is True
    result = prepare_brep_layer_input_v2(payload, 1)
    assert result["accepted"] is True
    assert result["status"] == "brep_layer_input_ready"
    assert result["sector_count"] == 24
    assert result["candidate_generation"] == "cxx_authoritative_brep_layer_input"
    assert all(
        sector["source_digest"] == payload["source_digest"]
        and sector["brep_edge_id"] >= 0
        and sector["incident_face_id"] >= 0
        and sector["segment_id"] >= 0
        for sector in result["sectors"]
    )


def test_layer_input_bl0_is_authoritative_without_generation(tmp_path: Path) -> None:
    payload = _payload(tmp_path)
    result = prepare_brep_layer_input_v2(payload, 0)
    assert result["accepted"] is True
    assert result["requested_layers"] == 0
    assert result["sector_count"] == 24


def test_layer_input_rejects_non_manifold_edge_incidence(tmp_path: Path) -> None:
    payload = _payload(tmp_path)
    bad = dict(payload)
    bad["edges"] = [dict(payload["edges"][0], incident_triangles_by_face=[
        *payload["edges"][0]["incident_triangles_by_face"],
        {"face_id": payload["edges"][0]["incident_triangles_by_face"][0]["face_id"], "triangle_ids": []},
    ])] + payload["edges"][1:]
    result = prepare_brep_layer_input_v2(bad, 1)
    assert result["accepted"] is False
    assert result["reason"] == "non_manifold_brep_edge_incidence"
