"""Default-off C++ geometric actual-edge witness contract."""

from __future__ import annotations

import hashlib
import sys
from pathlib import Path

sys.path.insert(0, "/tmp/autotessell_surface_bl_front_shared_build")
from native_brep_front_evidence_v2 import (  # noqa: E402
    witness_brep_contact_v2,
)

from core.analyzer.readers.step import load_cad_native_with_provenance
from core.layers.native_tet_brep_front_evidence_v2 import (
    build_brep_front_evidence_v2,
)
from tests.test_cad_xde_physical_authority import _write_styled_box
from tests.test_native_tet_brep_front_evidence_v2 import _explicit_owner_map


def _payload(tmp_path: Path) -> dict:
    source = tmp_path / "styled-box.step"
    _write_styled_box(source)
    cad = load_cad_native_with_provenance(source, ".step")
    return build_brep_front_evidence_v2(
        cad,
        source_digest=hashlib.sha256(source.read_bytes()).hexdigest(),
        owner_face_by_edge=_explicit_owner_map(cad),
    )


def test_cpp_witness_accepts_owner_and_adjacent_seam(tmp_path: Path) -> None:
    payload = _payload(tmp_path)
    edge = payload["edges"][0]
    p0, p1 = [payload["canonical_positions"][index] for index in edge["canonical_endpoints"]]
    third = [p0[0] + 0.17, p0[1] + 0.23, p0[2] + 0.31]
    owner = edge["owner_face_id"]
    owner_result = witness_brep_contact_v2(payload, edge["brep_edge_id"], owner, [p0, p1, third])
    assert owner_result["geometric_class"] == "base_touch"
    assert owner_result["witness"] is True
    assert owner_result["permitted"] is True
    other_faces = [face for face in edge["incident_faces"] if face != owner]
    assert other_faces
    seam_result = witness_brep_contact_v2(payload, edge["brep_edge_id"], other_faces[0], [p0, p1, third])
    assert seam_result["geometric_class"] == "seam_touch"
    assert seam_result["permitted"] is True


def test_cpp_witness_refuses_coplanar_nonadjacent_and_endpoint_mismatch(tmp_path: Path) -> None:
    payload = _payload(tmp_path)
    edge = payload["edges"][0]
    p0, p1 = [payload["canonical_positions"][index] for index in edge["canonical_endpoints"]]
    owner = edge["owner_face_id"]
    coplanar_source = next(
        triangle for triangle in payload["triangles"]
        if triangle["brep_face_id"] == owner and edge["brep_edge_id"] in triangle["brep_edge_ids"]
    )
    third_id = next(value for value in coplanar_source["canonical_vertices"] if value not in edge["canonical_endpoints"])
    coplanar_third = payload["canonical_positions"][third_id]
    coplanar = witness_brep_contact_v2(payload, edge["brep_edge_id"], owner, [p0, p1, coplanar_third])
    assert coplanar["geometric_class"] == "coplanar_positive_area"
    assert coplanar["permitted"] is False
    nonadjacent = witness_brep_contact_v2(payload, edge["brep_edge_id"], 5, [p0, p1, [0.17, 0.23, 0.31]])
    assert nonadjacent["geometric_class"] == "forbidden_non_adjacent_face"
    assert nonadjacent["permitted"] is False
    mismatch = witness_brep_contact_v2(payload, edge["brep_edge_id"], owner, [p0, [9.0, 9.0, 9.0], [1.0, 2.0, 3.0]])
    assert mismatch["witness"] is False
    assert mismatch["permitted"] is False
