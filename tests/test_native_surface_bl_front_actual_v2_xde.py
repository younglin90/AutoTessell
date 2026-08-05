from __future__ import annotations

from pathlib import Path
import json

import numpy as np
import pytest

pytest.importorskip("OCP")

from core.evaluator.native_surface_bl_front_actual_v2_xde_evidence import (
    write_actual_xde_folded_evidence,
)
from core.evaluator.native_surface_bl_front_readback import verify_actual_xde_folded_evidence
from core.utils.native_extensions import import_native_extension


def _write_explicit_xde_folded(path: Path) -> None:
    from OCP.BRep import BRep_Builder
    from OCP.BRepBuilderAPI import (
        BRepBuilderAPI_MakeEdge,
        BRepBuilderAPI_MakeFace,
        BRepBuilderAPI_MakeWire,
    )
    from OCP.IFSelect import IFSelect_RetDone
    from OCP.STEPCAFControl import STEPCAFControl_Writer
    from OCP.STEPControl import STEPControl_AsIs
    from OCP.TCollection import TCollection_ExtendedString
    from OCP.TDataStd import TDataStd_Name
    from OCP.TDocStd import TDocStd_Document
    from OCP.TopoDS import TopoDS_Shell
    from OCP.XCAFDoc import XCAFDoc_DocumentTool
    from OCP.gp import gp_Pnt

    points = [gp_Pnt(*row) for row in (
        (0, 0, 0), (1, 0, 0), (0, 1, 0), (0, 0, 1),
    )]

    def edge(a, b):
        return BRepBuilderAPI_MakeEdge(a, b).Edge()

    def face(edges):
        wire = BRepBuilderAPI_MakeWire()
        for item in edges:
            wire.Add(item)
        return BRepBuilderAPI_MakeFace(wire.Wire()).Face()

    shared = edge(points[0], points[1])
    face0 = face([shared, edge(points[1], points[2]), edge(points[2], points[0])])
    face1 = face([shared, edge(points[1], points[3]), edge(points[3], points[0])])
    builder = BRep_Builder()
    shell = TopoDS_Shell()
    builder.MakeShell(shell)
    builder.Add(shell, face0)
    builder.Add(shell, face1)

    document = TDocStd_Document(TCollection_ExtendedString("MDTV-XCAF"))
    shape_tool = XCAFDoc_DocumentTool.ShapeTool_s(document.Main())
    layer_tool = XCAFDoc_DocumentTool.LayerTool_s(document.Main())
    root = shape_tool.AddShape(shell, False)
    TDataStd_Name.Set_s(root, TCollection_ExtendedString("autotessell/component/folded"))
    for face_id, source_face in enumerate((face0, face1)):
        label = shape_tool.AddSubShape(root, source_face)
        TDataStd_Name.Set_s(label, TCollection_ExtendedString(f"autotessell/feature/face-{face_id}"))
        for prefix in ("feature", "patch", "physical-group", "component"):
            layer_tool.SetLayer(
                label,
                TCollection_ExtendedString(f"autotessell/{prefix}/face-{face_id}"),
            )
    writer = STEPCAFControl_Writer()
    writer.SetNameMode(True)
    writer.SetLayerMode(True)
    assert writer.Transfer(document, STEPControl_AsIs)
    assert writer.Write(str(path)) == IFSelect_RetDone


@pytest.mark.parametrize(("layers", "growth"), ((0, 1.0), (1, 1.0), (3, 1.2)))
def test_actual_xde_folded_bl_matrix(tmp_path: Path, layers: int, growth: float) -> None:
    source = tmp_path / "folded.step"
    _write_explicit_xde_folded(source)
    result = write_actual_xde_folded_evidence(
        tmp_path / f"evidence-{layers}", source,
        requested_layers=layers, first_height=0.2, growth_ratio=growth,
    )
    assert result["accepted"] is True, result
    assert result["authority_level"] == "L1_actual_stepcaf_xde_two_face_folded"
    assert result["publication_eligible"] is False
    assert len(set(result["run_digests"])) == 1
    assert result["readback"]["matches"] is True
    assert result["readback"]["fingerprint_matches"] is True
    producer = result["producer"]
    assert producer["actual_layers"] == layers
    assert producer["quality"]["collision_predicate"] == "long-double-aabb-sat-filtered-v1"
    assert producer["quality"]["collision_uncertain"] == 0
    assert producer["quality"]["duplicate"] == 0
    assert producer["quality"]["non_manifold"] == 0
    assert producer["quality"]["inverted"] == 0
    assert producer["quality"]["minimum_metric_triangle_quality"] >= 0.20
    assert len({row["source_edge"] for row in producer["provenance"]}) == 1
    root = Path(result["evidence_root"])
    assert root.joinpath("evidence.json").is_file()
    assert root.joinpath("source_ledger.json").is_file()
    assert root.joinpath("lineage.json").is_file()
    assert root.joinpath("readback.json").is_file()
    verifier = verify_actual_xde_folded_evidence(root)
    assert verifier["accepted"] is True, verifier
    assert verifier["recomputed_topology"]["non_manifold"] == 0
    tampered = tmp_path / f"tampered-{layers}"
    tampered.mkdir()
    manifest = json.loads(root.joinpath("evidence.json").read_text())
    manifest["producer"]["quality"]["minimum_metric_triangle_quality"] = 0.0
    tampered.joinpath("evidence.json").write_text(json.dumps(manifest))
    rejected = verify_actual_xde_folded_evidence(tampered)
    assert rejected["accepted"] is False
    manifest = json.loads(root.joinpath("evidence.json").read_text())
    manifest.pop("source_sha256")
    tampered.joinpath("evidence.json").write_text(json.dumps(manifest))
    assert verify_actual_xde_folded_evidence(tampered)["accepted"] is False
    manifest = json.loads(root.joinpath("evidence.json").read_text())
    manifest["producer"]["points"][0][0] += 0.125
    tampered.joinpath("evidence.json").write_text(json.dumps(manifest))
    assert verify_actual_xde_folded_evidence(tampered)["accepted"] is False
    if layers == 0:
        assert producer["status"] == "disabled_identity"


def test_actual_xde_folded_rejects_non_two_face_xde_atomically(tmp_path: Path) -> None:
    from tests.test_native_hex_actual_xde_brep_producer import _write_explicit_xde_box

    source = tmp_path / "box.step"
    _write_explicit_xde_box(source)
    result = write_actual_xde_folded_evidence(
        tmp_path / "rejected", source, requested_layers=1,
    )
    assert result["accepted"] is False
    assert result["candidate_discarded"] is True
    assert result["atomic_rollback"] is True
    assert not (tmp_path / "rejected").exists()


def test_filtered_collision_kernel_detects_overlap_and_clear_case() -> None:
    kernel = import_native_extension("native_surface_bl_folded_plate")

    positions = np.asarray([
        [0.0, 0.0, 0.0], [1.0, 0.0, 0.0], [0.0, 1.0, 0.0],
        [0.2, 0.2, 0.0], [1.2, 0.2, 0.0], [0.2, 1.2, 0.0],
        [2.0, 0.0, 0.0], [3.0, 0.0, 0.0], [2.0, 1.0, 0.0],
    ], dtype=np.float64)
    triangles = np.asarray([[0, 1, 2], [3, 4, 5], [6, 7, 8]], dtype=np.int64)
    rows = [
        {"source_face": "0", "source_edge": "e0"},
        {"source_face": "1", "source_edge": "e1"},
        {"source_face": "2", "source_edge": "e2"},
    ]
    result = kernel.audit_filtered_collision(positions, triangles, rows)
    assert result["collision"] is True
    assert result["candidate_count"] >= 1
    assert result["tested_count"] >= 1
    assert result["uncertain_count"] >= 1


def test_actual_xde_conflicting_semantics_and_filtered_gap_corpus(tmp_path: Path) -> None:
    from dataclasses import replace

    from core.analyzer.readers.step import load_cad_native_with_provenance
    from core.generator.native_surface_xde_folded_ledger import build_explicit_xde_folded_profile

    source = tmp_path / "folded.step"
    _write_explicit_xde_folded(source)
    cad = load_cad_native_with_provenance(source, ".step")
    layers = list(cad.provenance.xde_layer_names)
    layers[0] = tuple(layers[0]) + ("autotessell/patch/conflict",)
    conflicting = replace(cad.provenance, xde_layer_names=tuple(layers))
    profile = build_explicit_xde_folded_profile(replace(cad, provenance=conflicting))
    assert profile["accepted"] is False
    assert profile["reason"] == "folded_xde_explicit_semantic_mapping_incomplete"

    kernel = import_native_extension("native_surface_bl_folded_plate")

    def audit(rows):
        positions = np.asarray([
            [0.0, 0.0, 0.0], [1.0, 0.0, 0.0], [0.0, 1.0, 0.0],
            [1.0, 0.0, 0.0], [2.0, 0.0, 0.0], [1.0, 1.0, 0.0],
        ])
        triangles = np.asarray([[0, 1, 2], [3, 4, 5]], dtype=np.int64)
        return kernel.audit_filtered_collision(positions, triangles, rows)

    contact = audit([
        {"source_face": "0", "source_edge": "a"},
        {"source_face": "1", "source_edge": "b"},
    ])
    assert contact["collision"] is True
    assert contact["uncertain_count"] >= 1

    separated = kernel.audit_filtered_collision(
        np.asarray([
            [0.0, 0.0, 0.0], [1.0, 0.0, 0.0], [0.0, 1.0, 0.0],
            [2.0, 0.0, 0.0], [3.0, 0.0, 0.0], [2.0, 1.0, 0.0],
        ]),
        np.asarray([[0, 1, 2], [3, 4, 5]], dtype=np.int64),
        [{"source_face": "0", "source_edge": "a"}, {"source_face": "1", "source_edge": "b"}],
    )
    assert separated["collision"] is False


def test_actual_curved_and_three_face_xde_inputs_refuse(tmp_path: Path) -> None:
    from OCP.BRepBuilderAPI import BRepBuilderAPI_MakePolygon, BRepBuilderAPI_MakeFace
    from OCP.BRepPrimAPI import BRepPrimAPI_MakeCylinder
    from OCP.IFSelect import IFSelect_RetDone
    from OCP.STEPCAFControl import STEPCAFControl_Writer
    from OCP.STEPControl import STEPControl_AsIs
    from OCP.TCollection import TCollection_ExtendedString
    from OCP.TDataStd import TDataStd_Name
    from OCP.TDocStd import TDocStd_Document
    from OCP.TopoDS import TopoDS_Compound
    from OCP.XCAFDoc import XCAFDoc_DocumentTool
    from OCP.BRep import BRep_Builder
    from OCP.gp import gp_Pnt
    from core.analyzer.readers.step import load_cad_native_with_provenance
    from core.generator.native_surface_xde_folded_ledger import build_explicit_xde_folded_profile

    def write_shape(path, shape):
        doc = TDocStd_Document(TCollection_ExtendedString("MDTV-XCAF"))
        tool = XCAFDoc_DocumentTool.ShapeTool_s(doc.Main())
        label = tool.AddShape(shape, False)
        TDataStd_Name.Set_s(label, TCollection_ExtendedString("autotessell/component/adverse"))
        writer = STEPCAFControl_Writer()
        assert writer.Transfer(doc, STEPControl_AsIs)
        assert writer.Write(str(path)) == IFSelect_RetDone

    curved = tmp_path / "curved.step"
    write_shape(curved, BRepPrimAPI_MakeCylinder(1.0, 1.0).Shape())
    curved_cad = load_cad_native_with_provenance(curved, ".step")
    curved_profile = build_explicit_xde_folded_profile(curved_cad)
    assert curved_profile["accepted"] is False
    assert curved_profile["reason"] == "folded_xde_requires_two_brep_faces"

    compound = TopoDS_Compound()
    builder = BRep_Builder()
    builder.MakeCompound(compound)
    for offset in (0.0, 2.0, 4.0):
        polygon = BRepBuilderAPI_MakePolygon()
        polygon.Add(gp_Pnt(offset, 0, 0))
        polygon.Add(gp_Pnt(offset + 1, 0, 0))
        polygon.Add(gp_Pnt(offset, 1, 0))
        polygon.Close()
        builder.Add(compound, BRepBuilderAPI_MakeFace(polygon.Wire()).Face())
    three_face = tmp_path / "three-face.step"
    write_shape(three_face, compound)
    three_cad = load_cad_native_with_provenance(three_face, ".step")
    three_profile = build_explicit_xde_folded_profile(three_cad)
    assert three_profile["accepted"] is False
    assert three_profile["reason"] == "folded_xde_requires_two_brep_faces"
