from __future__ import annotations

from pathlib import Path

import pytest

pytest.importorskip("OCP")

from core.analyzer.readers.step import load_cad_native_with_provenance
from core.evaluator.native_hex_actual_xde_brep_evidence import write_actual_xde_hex_evidence
from core.generator.native_hex.xde_semantic_ledger import build_explicit_xde_hex_profile


def _write_explicit_xde_box(path: Path, dimensions: tuple[float, float, float] = (1.0, 1.0, 1.0)) -> None:
    from OCP.BRepPrimAPI import BRepPrimAPI_MakeBox
    from OCP.IFSelect import IFSelect_RetDone
    from OCP.STEPCAFControl import STEPCAFControl_Writer
    from OCP.STEPControl import STEPControl_AsIs
    from OCP.TCollection import TCollection_ExtendedString
    from OCP.TDataStd import TDataStd_Name
    from OCP.TDocStd import TDocStd_Document
    from OCP.TopAbs import TopAbs_FACE
    from OCP.TopExp import TopExp_Explorer
    from OCP.XCAFDoc import XCAFDoc_DocumentTool

    shape = BRepPrimAPI_MakeBox(*dimensions).Shape()
    document = TDocStd_Document(TCollection_ExtendedString("MDTV-XCAF"))
    shape_tool = XCAFDoc_DocumentTool.ShapeTool_s(document.Main())
    layer_tool = XCAFDoc_DocumentTool.LayerTool_s(document.Main())
    root = shape_tool.AddShape(shape, False)
    TDataStd_Name.Set_s(root, TCollection_ExtendedString("autotessell/component/box"))
    explorer = TopExp_Explorer(shape, TopAbs_FACE)
    face_id = 0
    while explorer.More():
        label = shape_tool.AddSubShape(root, explorer.Current())
        TDataStd_Name.Set_s(label, TCollection_ExtendedString(f"autotessell/feature/face-{face_id}"))
        for prefix in ("feature", "patch", "physical-group", "component"):
            layer_tool.SetLayer(label, TCollection_ExtendedString(f"autotessell/{prefix}/face-{face_id}"))
        face_id += 1
        explorer.Next()
    assert face_id == 6
    writer = STEPCAFControl_Writer()
    writer.SetNameMode(True)
    writer.SetLayerMode(True)
    assert writer.Transfer(document, STEPControl_AsIs)
    assert writer.Write(str(path)) == IFSelect_RetDone


@pytest.mark.parametrize("requested_layers", [0, 1, 3])
def test_actual_xde_hex_bl_matrix(tmp_path: Path, requested_layers: int) -> None:
    source = tmp_path / "explicit-box.step"
    _write_explicit_xde_box(source)
    cad = load_cad_native_with_provenance(source, ".step")
    profile = build_explicit_xde_hex_profile(cad)
    assert profile["accepted"] is True, profile
    result = write_actual_xde_hex_evidence(
        tmp_path / f"evidence-{requested_layers}", source,
        requested_layers=requested_layers, growth_ratio=1.2,
    )
    assert result["accepted"] is True, result
    assert result["authority_level"] == "L0_actual_stepcaf_xde_box"
    assert result["publication_eligible"] is False
    assert len(result["producer_runs"]) == 3
    producer = result["producer"]
    assert producer["actual_layers"] == requested_layers
    assert producer["topology"]["duplicate"] == 0
    assert producer["topology"]["non_manifold"] == 0
    assert producer["topology"]["inverted"] == 0
    assert producer["quality"]["minimum_volume"] > 0.0
    assert producer["quality"]["maximum_scaled_jacobian"] if "maximum_scaled_jacobian" in producer["quality"] else True
    assert producer["quality"]["maximum_skewness"] == 0.0
    assert producer["quality"]["maximum_non_orthogonality_degrees"] == 0.0
    assert producer["quality"]["maximum_aspect_ratio"] <= 3.0
    assert result["witness"]["accepted"] is True
    assert result["boundary_receipt"]["accepted"] is True
    assert result["boundary_receipt"]["status"] == "pass_native_hex_brep_boundary_receipt_v2"
    assert result["boundary_receipt"]["writer_order_bound"] is True
    assert len(result["boundary_receipt"]["receipt_sha256"]) == 64
    assert len({int(row["source_face"]) for row in producer["boundary_binding"]}) == 6
    assert all(bool(row["direct"]) for row in producer["boundary_binding"])
    root = Path(result["evidence_root"])
    assert root.joinpath("evidence.json").is_file()
    assert root.joinpath("source_ledger.tsv").is_file()
    assert root.joinpath("binding.tsv").is_file()
    assert root.joinpath("layers.tsv").is_file()


def test_actual_xde_hex_rejects_generic_xde_metadata_atomically(tmp_path: Path) -> None:
    from tests.test_cad_xde_physical_authority import _write_styled_box

    source = tmp_path / "generic-box.step"
    _write_styled_box(source)
    target = tmp_path / "rejected"
    result = write_actual_xde_hex_evidence(target, source, requested_layers=1)
    assert result["accepted"] is False
    assert result["candidate_discarded"] is True
    assert result["atomic_rollback"] is True
    assert not target.exists()


def test_actual_xde_hex_anisotropic_and_unit_growth_corpus(tmp_path: Path) -> None:
    source = tmp_path / "anisotropic-box.step"
    _write_explicit_xde_box(source, (1.0, 2.0, 3.0))
    result = write_actual_xde_hex_evidence(
        tmp_path / "anisotropic-evidence", source,
        requested_layers=3, growth_ratio=1.0,
    )
    assert result["accepted"] is True, result
    assert result["producer"]["actual_layers"] == 3
    assert result["producer"]["quality"]["minimum_volume"] > 0.0
    assert result["producer"]["quality"]["maximum_skewness"] == 0.0
    assert result["producer"]["quality"]["maximum_non_orthogonality_degrees"] == 0.0
    assert result["witness"]["accepted"] is True
    assert len(set(result["witness"]["witness_repeats"])) == 1
