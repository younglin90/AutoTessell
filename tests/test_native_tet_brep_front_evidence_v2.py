"""Actual CAD edge identity and incidence contract for the default-off v2 path."""

from __future__ import annotations

import hashlib
import sys
from pathlib import Path

import pytest

sys.path.insert(0, "/tmp/autotessell_surface_bl_front_shared_build")
from native_brep_front_evidence_v2 import (  # noqa: E402
    classify_brep_contact_v2,
    validate_brep_front_evidence_v2,
)

from core.analyzer.readers.step import load_cad_native_with_provenance
from core.layers.native_tet_brep_front_evidence_v2 import (
    build_brep_front_evidence_v2,
)
from tests.test_cad_xde_physical_authority import _write_styled_box


def _explicit_owner_map(cad) -> dict[int, int]:
    incident_faces: dict[int, set[int]] = {}
    for triangle_id, mapped in enumerate(cad.provenance.triangle_brep_edge_ids.tolist()):
        face_id = int(cad.provenance.triangle_face_ordinals[triangle_id])
        for edge_id in mapped:
            if int(edge_id) >= 0:
                incident_faces.setdefault(int(edge_id), set()).add(face_id)
    return {edge_id: min(faces) for edge_id, faces in incident_faces.items()}


def test_actual_brep_v2_has_real_edges_and_cpp_contract(tmp_path: Path) -> None:
    source = tmp_path / "styled-box.step"
    _write_styled_box(source)
    cad = load_cad_native_with_provenance(source, ".step")
    payload = build_brep_front_evidence_v2(
        cad,
        source_digest=hashlib.sha256(source.read_bytes()).hexdigest(),
        owner_face_by_edge=_explicit_owner_map(cad),
    )
    validation = validate_brep_front_evidence_v2(payload)
    assert validation["accepted"] is True
    assert validation["actual_edge_count"] == 12
    assert len(payload["edges"]) == 12
    assert len(payload["triangles"]) == 12
    assert any(-1 in triangle["brep_edge_ids"] for triangle in payload["triangles"])
    assert payload["authority"]["physical_groups"] is False
    assert payload["source_metadata"]["topological_edge_count"] == 12


def test_v2_contact_policy_requires_owner_and_incident_triangle(tmp_path: Path) -> None:
    source = tmp_path / "styled-box.step"
    _write_styled_box(source)
    cad = load_cad_native_with_provenance(source, ".step")
    payload = build_brep_front_evidence_v2(
        cad,
        source_digest="b" * 64,
        owner_face_by_edge=_explicit_owner_map(cad),
    )
    edge = payload["edges"][0]
    groups = {group["face_id"]: group["triangle_ids"] for group in edge["incident_triangles_by_face"]}
    owner = edge["owner_face_id"]
    owner_triangle = groups[owner][0]
    other_faces = [face for face in groups if face != owner]
    assert classify_brep_contact_v2(payload, edge["brep_edge_id"], owner_triangle, "base_touch")["permitted"]
    if other_faces:
        other_triangle = groups[other_faces[0]][0]
        assert classify_brep_contact_v2(
            payload, edge["brep_edge_id"], other_triangle, "seam_touch"
        )["permitted"]
        assert not classify_brep_contact_v2(
            payload, edge["brep_edge_id"], owner_triangle, "seam_touch"
        )["permitted"]
    bad = dict(payload)
    bad["non_manifold_edge_count"] = 1
    assert validate_brep_front_evidence_v2(bad)["accepted"] is False


def test_v2_requires_explicit_owner_for_each_actual_edge(tmp_path: Path) -> None:
    source = tmp_path / "styled-box.step"
    _write_styled_box(source)
    cad = load_cad_native_with_provenance(source, ".step")
    owners = _explicit_owner_map(cad)
    owners.pop(next(iter(owners)))
    with pytest.raises(ValueError, match="explicit owner is missing"):
        build_brep_front_evidence_v2(cad, source_digest="c" * 64, owner_face_by_edge=owners)
