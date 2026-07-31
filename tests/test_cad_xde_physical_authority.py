"""XDE metadata authority without promoting display metadata to BC semantics."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import numpy as np
import pytest

from core.analyzer.readers.step import load_cad_native, load_cad_native_with_provenance


def _xde_available() -> bool:
    try:
        from OCP.STEPCAFControl import STEPCAFControl_Reader  # noqa: F401

        return True
    except ImportError:
        return False


pytestmark = pytest.mark.skipif(not _xde_available(), reason="OCP XDE not installed")


def _write_styled_box(path: Path) -> None:
    from OCP.BRepPrimAPI import BRepPrimAPI_MakeBox
    from OCP.IFSelect import IFSelect_RetDone
    from OCP.Quantity import Quantity_Color, Quantity_TOC_RGB
    from OCP.STEPCAFControl import STEPCAFControl_Writer
    from OCP.STEPControl import STEPControl_AsIs
    from OCP.TCollection import TCollection_ExtendedString
    from OCP.TDataStd import TDataStd_Name
    from OCP.TDocStd import TDocStd_Document
    from OCP.TopAbs import TopAbs_FACE
    from OCP.TopExp import TopExp_Explorer
    from OCP.XCAFDoc import XCAFDoc_ColorSurf, XCAFDoc_DocumentTool

    shape = BRepPrimAPI_MakeBox(1.0, 2.0, 3.0).Shape()
    document = TDocStd_Document(TCollection_ExtendedString("MDTV-XCAF"))
    shape_tool = XCAFDoc_DocumentTool.ShapeTool_s(document.Main())
    color_tool = XCAFDoc_DocumentTool.ColorTool_s(document.Main())
    layer_tool = XCAFDoc_DocumentTool.LayerTool_s(document.Main())
    root = shape_tool.AddShape(shape, False)
    TDataStd_Name.Set_s(root, TCollection_ExtendedString("styled-box"))

    explorer = TopExp_Explorer(shape, TopAbs_FACE)
    face_index = 0
    while explorer.More():
        face_label = shape_tool.AddSubShape(root, explorer.Current())
        TDataStd_Name.Set_s(face_label, TCollection_ExtendedString(f"face-name-{face_index}"))
        layer_tool.SetLayer(face_label, TCollection_ExtendedString(f"boundary-{face_index % 2}"))
        color_tool.SetColor(
            face_label,
            Quantity_Color(0.1 + 0.1 * face_index, 0.2, 0.3, Quantity_TOC_RGB),
            XCAFDoc_ColorSurf,
        )
        face_index += 1
        explorer.Next()
    assert face_index == 6

    writer = STEPCAFControl_Writer()
    writer.SetNameMode(True)
    writer.SetLayerMode(True)
    writer.SetColorMode(True)
    assert writer.Transfer(document, STEPControl_AsIs)
    assert writer.Write(str(path)) == IFSelect_RetDone


def _write_named_assembly(path: Path) -> None:
    from OCP.BRepPrimAPI import BRepPrimAPI_MakeBox
    from OCP.gp import gp_Trsf, gp_Vec
    from OCP.IFSelect import IFSelect_RetDone
    from OCP.STEPCAFControl import STEPCAFControl_Writer
    from OCP.STEPControl import STEPControl_AsIs
    from OCP.TCollection import TCollection_ExtendedString
    from OCP.TDataStd import TDataStd_Name
    from OCP.TDocStd import TDocStd_Document
    from OCP.TopLoc import TopLoc_Location
    from OCP.XCAFDoc import XCAFDoc_DocumentTool

    document = TDocStd_Document(TCollection_ExtendedString("MDTV-XCAF"))
    shape_tool = XCAFDoc_DocumentTool.ShapeTool_s(document.Main())
    first_part = shape_tool.AddShape(BRepPrimAPI_MakeBox(1.0, 1.0, 1.0).Shape(), False)
    second_part = shape_tool.AddShape(BRepPrimAPI_MakeBox(2.0, 1.0, 1.0).Shape(), False)
    TDataStd_Name.Set_s(first_part, TCollection_ExtendedString("part-A"))
    TDataStd_Name.Set_s(second_part, TCollection_ExtendedString("part-B"))
    assembly = shape_tool.NewShape()
    TDataStd_Name.Set_s(assembly, TCollection_ExtendedString("assembly-root"))
    first_component = shape_tool.AddComponent(assembly, first_part, TopLoc_Location())
    transform = gp_Trsf()
    transform.SetTranslation(gp_Vec(3.0, 0.0, 0.0))
    second_component = shape_tool.AddComponent(assembly, second_part, TopLoc_Location(transform))
    TDataStd_Name.Set_s(first_component, TCollection_ExtendedString("instance-A"))
    TDataStd_Name.Set_s(second_component, TCollection_ExtendedString("instance-B"))
    shape_tool.UpdateAssemblies()
    assert shape_tool.IsAssembly_s(assembly)

    writer = STEPCAFControl_Writer()
    writer.SetNameMode(True)
    assert writer.Transfer(document, STEPControl_AsIs)
    assert writer.Write(str(path)) == IFSelect_RetDone


def _assert_xde_rejection_preserves_legacy_arrays(path: Path, match: str) -> None:
    """The optional XDE payload must never alter the established STEP stream."""
    before_vertices, before_faces = load_cad_native(path, ".step")
    with pytest.raises(ValueError, match=match):
        load_cad_native_with_provenance(path, ".step")
    after_vertices, after_faces = load_cad_native(path, ".step")
    assert np.array_equal(after_vertices, before_vertices)
    assert np.array_equal(after_faces, before_faces)


def test_explicit_xde_layers_are_authoritative_grouping_not_physical_bc(
    tmp_path: Path,
) -> None:
    path = tmp_path / "styled-box.step"
    _write_styled_box(path)
    legacy_vertices, legacy_faces = load_cad_native(path, ".step")
    result = load_cad_native_with_provenance(path, ".step")
    provenance = result.provenance

    assert np.array_equal(result.vertices, legacy_vertices)
    assert np.array_equal(result.faces, legacy_faces)
    assert provenance.face_count == 6
    assert provenance.xde_layer_authoritative
    assert provenance.xde_layer_coverage_count == 6
    assert all(len(names) == 1 for names in provenance.xde_layer_names)
    assert {name for names in provenance.xde_layer_names for name in names} == {
        "boundary-0",
        "boundary-1",
    }
    assert provenance.xde_color_display_metadata_authoritative
    assert all(color is not None for color in provenance.xde_surface_colors)
    assert provenance.face_names == (None,) * 6
    assert not provenance.physical_groups_authoritative
    assert provenance.physical_group_names == (None,) * 6
    assert not provenance.xde_assembly_identity_authoritative


def test_named_xde_assembly_paths_are_identity_only(tmp_path: Path) -> None:
    path = tmp_path / "named-assembly.step"
    _write_named_assembly(path)
    legacy_vertices, legacy_faces = load_cad_native(path, ".step")
    result = load_cad_native_with_provenance(path, ".step")
    provenance = result.provenance

    assert np.array_equal(result.vertices, legacy_vertices)
    assert np.array_equal(result.faces, legacy_faces)
    assert provenance.face_count == 12
    assert provenance.xde_assembly_identity_authoritative
    assert all(path is not None for path in provenance.xde_assembly_paths)
    assert set(provenance.xde_assembly_paths) == {
        ("assembly-root", "instance-A", "part-A"),
        ("assembly-root", "instance-B", "part-B"),
    }
    assert not provenance.xde_layer_authoritative
    assert provenance.xde_layer_coverage_count == 0
    assert not provenance.physical_groups_authoritative


def test_xde_metadata_hash_repeats_three_times(tmp_path: Path) -> None:
    path = tmp_path / "styled-box.step"
    _write_styled_box(path)
    reports = [load_cad_native_with_provenance(path, ".step").provenance for _ in range(3)]

    assert len({report.xde_metadata_sha256 for report in reports}) == 1
    assert len({report.ordered_face_ordinal_sha256 for report in reports}) == 1
    assert len({report.seam_connectivity_sha256 for report in reports}) == 1


def test_xde_unmapped_face_metadata_fails_before_payload(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from OCP.BRepPrimAPI import BRepPrimAPI_MakeBox
    from OCP.TopAbs import TopAbs_FACE
    from OCP.TopExp import TopExp_Explorer
    from OCP.XCAFDoc import XCAFDoc_ShapeTool

    path = tmp_path / "styled-box.step"
    _write_styled_box(path)
    unrelated_faces = TopExp_Explorer(
        BRepPrimAPI_MakeBox(4.0, 5.0, 6.0).Shape(), TopAbs_FACE
    )
    unrelated_face = unrelated_faces.Current()
    original_get_shape = XCAFDoc_ShapeTool.GetShape_s
    replaced = False

    def get_shape_with_unmapped_face(self: Any, label: Any) -> Any:
        nonlocal replaced
        shape = original_get_shape(label)
        if not replaced and shape.ShapeType() == TopAbs_FACE:
            replaced = True
            return unrelated_face
        return shape

    monkeypatch.setattr(XCAFDoc_ShapeTool, "GetShape_s", get_shape_with_unmapped_face)
    _assert_xde_rejection_preserves_legacy_arrays(
        path, "XDE shape does not map to the B-Rep face stream"
    )


def test_conflicting_xde_face_layers_fail_before_payload(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from OCP.TCollection import TCollection_ExtendedString
    from OCP.XCAFDoc import XCAFDoc_LayerTool, XCAFDoc_ShapeTool

    path = tmp_path / "styled-box.step"
    _write_styled_box(path)
    original_subshapes = XCAFDoc_ShapeTool.GetSubShapes_s
    original_get_layer = XCAFDoc_LayerTool.GetLayer
    recovered_layers = 0

    def duplicate_first_subshape(self: Any, label: Any, labels: Any) -> bool:
        result = original_subshapes(label, labels)
        if labels.Length():
            labels.Append(labels.Value(1))
        return bool(result)

    def get_conflicting_layer(self: Any, label: Any, value: Any) -> bool:
        nonlocal recovered_layers
        result = original_get_layer(self, label, value)
        if result:
            recovered_layers += 1
            if recovered_layers == 7:
                value.Clear()
                value.AssignCat(TCollection_ExtendedString("conflicting-layer"))
        return bool(result)

    monkeypatch.setattr(XCAFDoc_ShapeTool, "GetSubShapes_s", duplicate_first_subshape)
    monkeypatch.setattr(XCAFDoc_LayerTool, "GetLayer", get_conflicting_layer)
    _assert_xde_rejection_preserves_legacy_arrays(path, "conflicting XDE face layers")


def test_conflicting_xde_face_colors_fail_before_payload(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from OCP.Quantity import Quantity_TOC_RGB
    from OCP.XCAFDoc import XCAFDoc_ColorTool, XCAFDoc_ShapeTool

    path = tmp_path / "styled-box.step"
    _write_styled_box(path)
    original_subshapes = XCAFDoc_ShapeTool.GetSubShapes_s
    original_get_color = XCAFDoc_ColorTool.GetColor
    recovered_colors = 0

    def duplicate_first_subshape(self: Any, label: Any, labels: Any) -> bool:
        result = original_subshapes(label, labels)
        if labels.Length():
            labels.Append(labels.Value(1))
        return bool(result)

    def get_conflicting_color(
        self: Any, shape: Any, color_type: Any, color: Any
    ) -> bool:
        nonlocal recovered_colors
        result = original_get_color(self, shape, color_type, color)
        if result:
            recovered_colors += 1
            if recovered_colors == 7:
                color.SetValues(0.9, 0.8, 0.7, Quantity_TOC_RGB)
        return bool(result)

    monkeypatch.setattr(XCAFDoc_ShapeTool, "GetSubShapes_s", duplicate_first_subshape)
    monkeypatch.setattr(XCAFDoc_ColorTool, "GetColor", get_conflicting_color)
    _assert_xde_rejection_preserves_legacy_arrays(path, "conflicting XDE surface colors")


def test_ambiguous_xde_assembly_path_fails_before_payload(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from OCP.TopAbs import TopAbs_FACE
    from OCP.XCAFDoc import XCAFDoc_ShapeTool

    path = tmp_path / "named-assembly.step"
    _write_named_assembly(path)
    original_get_shape = XCAFDoc_ShapeTool.GetShape_s
    first_component_shape: Any | None = None

    def get_shape_with_ambiguous_component(self: Any, label: Any) -> Any:
        nonlocal first_component_shape
        shape = original_get_shape(label)
        if not shape.IsNull() and shape.ShapeType() != TopAbs_FACE:
            if first_component_shape is None:
                first_component_shape = shape
            else:
                return first_component_shape
        return shape

    monkeypatch.setattr(
        XCAFDoc_ShapeTool, "GetShape_s", get_shape_with_ambiguous_component
    )
    _assert_xde_rejection_preserves_legacy_arrays(
        path, "ambiguous XDE assembly path for B-Rep face"
    )


def test_missing_xde_component_reference_fails_before_payload(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from OCP.XCAFDoc import XCAFDoc_ShapeTool

    path = tmp_path / "named-assembly.step"
    _write_named_assembly(path)

    def missing_reference(self: Any, component: Any, referred: Any) -> bool:
        return False

    monkeypatch.setattr(XCAFDoc_ShapeTool, "GetReferredShape_s", missing_reference)
    _assert_xde_rejection_preserves_legacy_arrays(
        path, "XDE component has no referred shape"
    )


def test_blank_existing_step_corpus_remains_semantically_unknown() -> None:
    for path in sorted(Path("tests/benchmarks").glob("*.step")):
        provenance = load_cad_native_with_provenance(path, ".step").provenance
        assert not provenance.xde_layer_authoritative
        assert provenance.xde_layer_coverage_count == 0
        assert not provenance.xde_color_display_metadata_authoritative
        assert not provenance.xde_assembly_identity_authoritative
        assert not provenance.physical_groups_authoritative
