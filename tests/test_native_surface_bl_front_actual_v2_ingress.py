"""Actual styled STEP BRepFrontEvidence/v2 ingress evidence."""

from __future__ import annotations

import hashlib
from pathlib import Path

import numpy as np

from core.analyzer.readers.step import load_cad_native_with_provenance
from core.evaluator.native_surface_bl_front_actual_v2_ingress import validate_actual_brep_v2_ingress
from core.layers.native_tet_brep_front_evidence_v2 import build_brep_front_evidence_v2
from tests.test_cad_xde_physical_authority import _write_styled_box
from tests.test_native_tet_brep_front_evidence_v2 import _explicit_owner_map


def test_actual_styled_step_v2_is_deterministic_with_explicit_mapping(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("AUTOTESSELL_EXT_BUILD_DIR", "/tmp/autotessell_surface_bl_front_shared_build")
    source = tmp_path / "styled-box.step"
    _write_styled_box(source)
    raw_digest = hashlib.sha256(source.read_bytes()).hexdigest()
    cad = load_cad_native_with_provenance(source, ".step")
    evidence = build_brep_front_evidence_v2(cad, source_digest=raw_digest, owner_face_by_edge=_explicit_owner_map(cad))
    evidence = dict(evidence, direction_records=[dict(record, domain_side_authority=True) for record in evidence["direction_records"]])
    mapping = [
        {
            "source_edge": int(edge["brep_edge_id"]),
            "source_face": int(edge["owner_face_id"]),
            "wall_edge": f"wall-{edge['brep_edge_id']}",
            "output_face": f"output-{edge['brep_edge_id']}",
            "patch": "wall",
            "feature": "cad-face",
            "physical_group": "fluid-wall",
            "component": "styled-box",
            "provenance": "explicit-user-map",
            "mapping_source": "explicit_user",
            "direct": True,
        }
        for edge in evidence["edges"]
    ]
    for layers in (0, 1, 3):
        first = validate_actual_brep_v2_ingress(np.asarray(evidence["canonical_positions"], dtype=np.float64), evidence, mapping, layers, raw_digest, "mapping-digest")
        second = validate_actual_brep_v2_ingress(np.asarray(evidence["canonical_positions"], dtype=np.float64), evidence, mapping, layers, raw_digest, "mapping-digest")
        assert first["receipt_digest"] == second["receipt_digest"] and first["status"] == second["status"]
        assert first["accepted"] is True
        assert first["actual_layers"] == layers
        assert first["runtime_route"] == "default_off"
        assert first["optimizer_ingress"]["source_certificate"]["authority"] == "actual-brep-front-evidence-v2-explicit-mapping"


def test_actual_v2_missing_explicit_mapping_is_incomplete(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("AUTOTESSELL_EXT_BUILD_DIR", "/tmp/autotessell_surface_bl_front_shared_build")
    source = tmp_path / "styled-box.step"
    _write_styled_box(source)
    raw_digest = hashlib.sha256(source.read_bytes()).hexdigest()
    cad = load_cad_native_with_provenance(source, ".step")
    evidence = build_brep_front_evidence_v2(cad, source_digest=raw_digest, owner_face_by_edge=_explicit_owner_map(cad))
    result = validate_actual_brep_v2_ingress(np.asarray(evidence["canonical_positions"], dtype=np.float64), evidence, [], 1, raw_digest, "mapping-digest")
    assert result["accepted"] is False
    assert result["reason"] == "authority_mapping_coverage_incomplete"
    assert result["actual_layers"] == 0
