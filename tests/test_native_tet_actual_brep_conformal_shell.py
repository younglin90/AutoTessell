from __future__ import annotations

from hashlib import sha256
from pathlib import Path

import numpy as np
import pytest

pytest.importorskip("OCP")
from OCP.BRepBuilderAPI import BRepBuilderAPI_MakeFace, BRepBuilderAPI_MakeSolid, BRepBuilderAPI_MakePolygon, BRepBuilderAPI_Sewing
from OCP.STEPControl import STEPControl_AsIs, STEPControl_Writer
from OCP.TopoDS import TopoDS
from OCP.gp import gp_Pnt

from core.analyzer.readers.step import load_cad_native_with_provenance
from core.evaluator.native_l2_evidence_audit import audit_native_tet_polymesh_persisted_evidence
from core.evaluator.native_tet_brep_conformal_shell_evidence import write_actual_brep_conformal_tet_shell_evidence
from core.layers.native_tet_brep_front_evidence_v2 import build_brep_front_evidence_v2


def _write_regular_tetra(path: Path) -> None:
    root = 2.0**-0.5
    points = [
        gp_Pnt(1.0, 0.0, -root),
        gp_Pnt(-1.0, 0.0, -root),
        gp_Pnt(0.0, 1.0, root),
        gp_Pnt(0.0, -1.0, root),
    ]
    face_specs = ((0, 2, 1), (0, 1, 3), (0, 3, 2), (1, 2, 3))
    faces = []
    for spec in face_specs:
        polygon = BRepBuilderAPI_MakePolygon()
        for index in spec:
            polygon.Add(points[index])
        polygon.Close()
        faces.append(BRepBuilderAPI_MakeFace(polygon.Wire()).Face())
    sewing = BRepBuilderAPI_Sewing(1.0e-7)
    for face in faces:
        sewing.Add(face)
    sewing.Perform()
    shell = TopoDS.Shell_s(sewing.SewedShape())
    solid = BRepBuilderAPI_MakeSolid(shell).Solid()
    writer = STEPControl_Writer()
    writer.Transfer(solid, STEPControl_AsIs)
    assert int(writer.Write(str(path))) == 1


def _mapping_and_owner(source: Path):
    cad = load_cad_native_with_provenance(source, ".step")
    digest = sha256(source.read_bytes()).hexdigest()
    edge_ids = cad.provenance.triangle_brep_edge_ids
    face_ids = cad.provenance.triangle_face_ordinals
    owner = {}
    mapping = []
    for triangle, face_id, mapped_edges in zip(cad.faces.tolist(), face_ids.tolist(), edge_ids.tolist(), strict=True):
        face = int(face_id)
        edge = next(int(value) for value in mapped_edges if int(value) >= 0)
        for value in mapped_edges:
            if int(value) >= 0:
                owner.setdefault(int(value), face)
        mapping.append(
            {
                "source_face": face,
                "source_edge": edge,
                "wall_edge": f"wall-{edge}",
                "output_face": f"out-face-{face}",
                "patch": f"patch-{face}",
                "feature": f"feature-{face}",
                "physical_group": f"group-{face}",
                "component": f"component-{face}",
                "provenance": f"brep-face-{face}",
                "direct": True,
                "selected_for_bl": face == min(int(x) for x in face_ids),
            }
        )
    evidence = build_brep_front_evidence_v2(cad, source_digest=digest, owner_face_by_edge=owner)
    return mapping, owner, evidence


@pytest.mark.parametrize("requested_layers", [0, 1, 3])
def test_actual_brep_tet_shell_bl_matrix_is_sealed(tmp_path: Path, requested_layers: int) -> None:
    source = tmp_path / "regular_tetra.step"
    _write_regular_tetra(source)
    mapping, owner, _ = _mapping_and_owner(source)
    result = write_actual_brep_conformal_tet_shell_evidence(
        tmp_path / f"evidence-bl{requested_layers}",
        source,
        explicit_mapping=mapping,
        owner_face_by_edge=owner,
        requested_layers=requested_layers,
    )
    assert result["accepted"] is True, result
    audit = result["audit"]
    manifest = (tmp_path / f"evidence-bl{requested_layers}" / "evidence.atne").read_text()
    assert "authority_level=L0_actual_brep_fixture" in manifest
    for field in ("authority_canonical_positions_digest", "authority_face_ordinal_digest", "authority_orientation_digest", "authority_seam_digest", "authority_mapping_digest"):
        assert any(line.startswith(field + "=") and len(line.split("=", 1)[1]) == 64 for line in manifest.splitlines())
    semantics = {f"face-{row['source_face']}": row for row in mapping}
    for binding in result["producer"]["boundary_binding"]:
        expected = semantics[binding["source_face"]]
        for field in ("feature", "patch", "physical_group", "component", "provenance"):
            assert binding[field] == expected[field]
    assert audit["repeatable_three_runs"] is True
    assert audit["topology"]["duplicate"] == 0
    assert audit["topology"]["non_manifold"] == 0
    assert audit["topology"]["inverted"] == 0
    assert audit["topology"]["self_intersection"] == 0
    assert audit["quality"]["max_tangent_aspect"] <= 5.0
    assert audit["quality"]["max_skewness"] <= 0.25 + 1.0e-9
    if requested_layers == 0:
        assert audit["wall_front_status"] == "not_applicable_bl0"
        assert result["producer"]["actual_layers"] == 0
    else:
        assert audit["requested_layers"] == requested_layers
        assert audit["actual_layers"] == requested_layers
        assert audit["quality"]["max_wall_front_orthogonality_degrees"] <= 25.0
        assert result["producer"]["quality"]["max_aspect_ratio"] < 5.0
        assert len(result["producer"]["layer_records"]) == requested_layers


def test_actual_brep_tet_shell_rejects_incomplete_mapping_atomically(tmp_path: Path) -> None:
    source = tmp_path / "regular_tetra.step"
    _write_regular_tetra(source)
    mapping, owner, _ = _mapping_and_owner(source)
    mapping[0] = {**mapping[0], "physical_group": ""}
    target = tmp_path / "rejected"
    result = write_actual_brep_conformal_tet_shell_evidence(
        target,
        source,
        explicit_mapping=mapping,
        owner_face_by_edge=owner,
        requested_layers=1,
    )
    assert result["accepted"] is False
    assert result["candidate_discarded"] is True
    assert result["atomic_rollback"] is True
    assert not target.exists()


def test_actual_brep_tet_shell_audit_detects_output_tamper(tmp_path: Path) -> None:
    source = tmp_path / "regular_tetra.step"
    _write_regular_tetra(source)
    mapping, owner, _ = _mapping_and_owner(source)
    target = tmp_path / "evidence"
    result = write_actual_brep_conformal_tet_shell_evidence(
        target,
        source,
        explicit_mapping=mapping,
        owner_face_by_edge=owner,
        requested_layers=1,
    )
    assert result["accepted"] is True, result
    points = target / "output/case/constant/polyMesh/points"
    points.write_text(points.read_text().replace("1 ", "1.000001 ", 1))
    tampered = audit_native_tet_polymesh_persisted_evidence(str(target))
    assert tampered["accepted"] is False
    assert "digest" in tampered["reason"]