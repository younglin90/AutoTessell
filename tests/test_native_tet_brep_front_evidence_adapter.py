"""Actual OCP/XDE provenance adapter to the C++ BRep evidence contract."""

from __future__ import annotations

import hashlib
import sys
from pathlib import Path

sys.path.insert(0, "/tmp/autotessell_surface_bl_front_shared_build")
from native_brep_front_evidence import validate_brep_front_evidence  # noqa: E402

from core.analyzer.readers.step import load_cad_native_with_provenance
from core.layers.native_tet_brep_front_evidence import build_brep_front_evidence
from tests.test_cad_xde_physical_authority import _write_styled_box


def test_actual_cad_provenance_adapts_to_cpp_contract(tmp_path: Path) -> None:
    source = tmp_path / "styled-box.step"
    _write_styled_box(source)
    cad = load_cad_native_with_provenance(source, ".step")
    digest = hashlib.sha256(source.read_bytes()).hexdigest()
    first = build_brep_front_evidence(cad, source_digest=digest)
    second = build_brep_front_evidence(cad, source_digest=digest)
    assert first == second
    assert validate_brep_front_evidence(first)["accepted"] is True
    assert first["authority"] == {
        "face_ordinals": True,
        "orientation": True,
        "seam_connectivity": True,
        "physical_groups": False,
        "runtime_route": "default_off",
    }
    assert first["source_metadata"]["face_count"] == 6
    assert first["source_metadata"]["triangle_count"] == 12
    assert len(first["triangles"]) == 12
    assert len(first["edges"]) == 18
    assert all(edge["owner_face_id"] in edge["incident_faces"] for edge in first["edges"])


def test_incomplete_cad_authority_refuses_before_adapter_payload(tmp_path: Path) -> None:
    source = tmp_path / "styled-box.step"
    _write_styled_box(source)
    cad = load_cad_native_with_provenance(source, ".step")
    object.__setattr__(cad.provenance, "seam_connectivity_authoritative", False)
    try:
        build_brep_front_evidence(cad, source_digest="a" * 64)
    except ValueError as exc:
        assert "authority is incomplete" in str(exc)
    else:
        raise AssertionError("incomplete CAD authority was accepted")
