"""Actual CAD/B-Rep output binding for the native Hex release route."""

from __future__ import annotations

from dataclasses import replace
from hashlib import sha256
from pathlib import Path

import pytest

from core.analyzer.readers.step import load_cad_native_with_provenance
from core.evaluator.strict_volume_topology import audit_strict_volume_topology
from core.generator.native_hex.mesher import generate_native_hex

_FIXTURE = Path("tests/benchmarks/box.step")


def _ocp_available() -> bool:
    try:
        from OCP.STEPControl import STEPControl_Reader  # noqa: F401
        return True
    except ImportError:
        return False


pytestmark = pytest.mark.skipif(not _ocp_available(), reason="OCP not installed")


def test_box_step_written_hex_has_measured_brep_binding_and_group_patches(tmp_path: Path) -> None:
    cad = load_cad_native_with_provenance(_FIXTURE, ".step")
    provenance = cad.provenance
    groups = tuple(f"brep-face-{index}" for index in range(provenance.face_count))
    authoritative = replace(
        provenance,
        physical_group_names=groups,
        physical_groups_authoritative=True,
    )
    source_vertices = cad.vertices[provenance.canonical_vertex_source_ids]
    source_faces = provenance.oriented_canonical_faces

    result = generate_native_hex(
        source_vertices,
        source_faces,
        tmp_path,
        target_edge_length=0.25,
        seed_density=8,
        snap_boundary=True,
        source_path=_FIXTURE,
        source_vertices=source_vertices,
        source_faces=source_faces,
        source_provenance=authoritative,
    )

    assert result.success
    assert result.source_output_binding is not None
    binding = result.source_output_binding
    assert binding.status == "pass_measured_native_hex_source_binding"
    assert binding.strict_binding_complete
    assert binding.mapping_complete
    assert binding.physical_group_mapping_complete
    assert binding.output_boundary_face_count == 96
    assert binding.max_source_plane_distance == 0.0
    assert binding.source_file_sha256 == sha256(_FIXTURE.read_bytes()).hexdigest()
    assert set(binding.output_physical_groups) == set(groups)

    strict = audit_strict_volume_topology(tmp_path)
    assert strict.valid
    assert strict.n_duplicate_faces == 0
    assert strict.n_nonmanifold_faces == 0
    assert strict.n_nonmanifold_cell_edges == 0
    assert strict.n_open_cell_edges == 0
    assert strict.n_inverted_cells == 0
    boundary = (tmp_path / "constant" / "polyMesh" / "boundary").read_text()
    for group in groups:
        assert group in boundary


def test_non_cube_stepped_brep_source_binding_is_measured_and_repeatable(tmp_path: Path) -> None:
    from OCP.BRepAlgoAPI import BRepAlgoAPI_Fuse
    from OCP.BRepBuilderAPI import BRepBuilderAPI_Transform
    from OCP.BRepPrimAPI import BRepPrimAPI_MakeBox
    from OCP.STEPControl import STEPControl_AsIs, STEPControl_Writer
    from OCP.gp import gp_Trsf, gp_Vec

    source_path = tmp_path / "stepped_brep.step"
    first = BRepPrimAPI_MakeBox(2.0, 1.0, 1.0).Shape()
    second = BRepPrimAPI_MakeBox(1.0, 1.0, 1.0).Shape()
    transform = gp_Trsf()
    transform.SetTranslation(gp_Vec(0.0, 1.0, 0.0))
    second = BRepBuilderAPI_Transform(second, transform, True).Shape()
    shape = BRepAlgoAPI_Fuse(first, second).Shape()
    writer = STEPControl_Writer()
    assert writer.Transfer(shape, STEPControl_AsIs) == 1
    assert writer.Write(str(source_path)) == 1

    cad = load_cad_native_with_provenance(source_path, ".step")
    provenance = cad.provenance
    groups = tuple(f"stepped-face-{index}" for index in range(provenance.face_count))
    authoritative = replace(
        provenance,
        physical_group_names=groups,
        physical_groups_authoritative=True,
    )
    source_vertices = cad.vertices[provenance.canonical_vertex_source_ids]
    source_faces = provenance.oriented_canonical_faces
    hashes: list[str] = []
    for repeat in range(3):
        result = generate_native_hex(
            source_vertices,
            source_faces,
            tmp_path / f"stepped-case-{repeat}",
            target_edge_length=0.25,
            seed_density=10,
            snap_boundary=True,
            source_path=source_path,
            source_vertices=source_vertices,
            source_faces=source_faces,
            source_provenance=authoritative,
        )
        assert result.success, result.message
        binding = result.source_output_binding
        assert binding is not None
        assert binding.status == "pass_measured_native_hex_source_binding"
        assert binding.strict_binding_complete
        assert binding.mapping_complete
        assert binding.physical_group_mapping_complete
        assert binding.max_source_plane_distance == 0.0
        assert binding.source_file_sha256 == sha256(source_path.read_bytes()).hexdigest()
        assert set(binding.output_physical_groups) == set(groups)
        strict = audit_strict_volume_topology(tmp_path / f"stepped-case-{repeat}")
        assert strict.valid
        assert strict.n_duplicate_faces == 0
        assert strict.n_nonmanifold_faces == 0
        assert strict.n_nonmanifold_cell_edges == 0
        assert strict.n_open_cell_edges == 0
        assert strict.n_inverted_cells == 0
        hashes.append(strict.artifact_sha256)
    assert hashes == [hashes[0]] * 3
