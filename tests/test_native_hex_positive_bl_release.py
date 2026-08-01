from __future__ import annotations

import hashlib
import tempfile
from pathlib import Path

import numpy as np

from core.evaluator.strict_volume_topology import audit_strict_volume_topology
from core.generator.polymesh_writer import write_generic_polymesh
from core.generator.tier_layers_post import _run_native_hex_bl
from core.utils.polymesh_reader import parse_foam_boundary


def _manifest(root: Path) -> dict[str, str]:
    poly = root / "constant" / "polyMesh"
    return {
        path.relative_to(poly).as_posix(): hashlib.sha256(path.read_bytes()).hexdigest()
        for path in sorted(poly.iterdir())
        if path.is_file()
    }


def _run(root: Path) -> tuple[str, dict[str, str]]:
    points = np.array(
        [
            [0, 0, 0], [1, 0, 0], [1, 1, 0], [0, 1, 0],
            [0, 0, 1], [1, 0, 1], [1, 1, 1], [0, 1, 1],
        ],
        dtype=np.float64,
    )
    faces = [
        [0, 3, 2, 1], [4, 5, 6, 7], [0, 1, 5, 4],
        [3, 7, 6, 2], [0, 4, 7, 3], [1, 2, 6, 5],
    ]
    write_generic_polymesh(
        points, [faces], root, patch_name="wall", patch_type="wall", strict=True
    )
    ok, message, selected = _run_native_hex_bl(
        root,
        num_layers=2,
        growth_ratio=1.2,
        first_thickness=0.05,
        params={
            "post_layers_hex_inward_shell": True,
            "post_layers_wall_patch_names": ["wall"],
        },
    )
    assert ok, message
    assert selected == 6
    assert "requested_layers=2" in message
    assert "actual_layers=2" in message
    assert "min_signed_volume=" in message
    strict = audit_strict_volume_topology(root)
    assert strict.valid, strict.as_dict()
    assert strict.n_duplicate_faces == 0
    assert strict.n_nonmanifold_faces == 0
    assert strict.n_nonmanifold_cell_edges == 0
    assert strict.n_open_cell_edges == 0
    assert strict.n_inverted_cells == 0
    return message, _manifest(root)


def test_native_hex_positive_boundary_layer_release_artifact() -> None:
    with tempfile.TemporaryDirectory(prefix="autotess_native_hex_bl_") as first:
        first_root = Path(first)
        first_message, first_manifest = _run(first_root)
        assert "actual_layers=2" in first_message
        with tempfile.TemporaryDirectory(prefix="autotess_native_hex_bl_") as second:
            second_message, second_manifest = _run(Path(second))
    assert "actual_layers=2" in second_message
    assert first_manifest == second_manifest


def test_native_hex_step_and_stepped_brep_positive_bl_is_source_bound(
    tmp_path: Path,
) -> None:
    from dataclasses import replace

    from core.analyzer.readers.step import load_cad_native_with_provenance
    from core.generator.native_hex.mesher import generate_native_hex
    from OCP.BRepAlgoAPI import BRepAlgoAPI_Fuse
    from OCP.BRepBuilderAPI import BRepBuilderAPI_Transform
    from OCP.BRepPrimAPI import BRepPrimAPI_MakeBox
    from OCP.STEPControl import STEPControl_AsIs, STEPControl_Writer
    from OCP.gp import gp_Trsf, gp_Vec

    first = BRepPrimAPI_MakeBox(2.0, 1.0, 1.0).Shape()
    second = BRepPrimAPI_MakeBox(1.0, 1.0, 1.0).Shape()
    transform = gp_Trsf()
    transform.SetTranslation(gp_Vec(0.0, 1.0, 0.0))
    second = BRepBuilderAPI_Transform(second, transform, True).Shape()
    shape = BRepAlgoAPI_Fuse(first, second).Shape()
    source_path = tmp_path / "stepped_positive_bl.step"
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
    artifact_hashes: list[str] = []
    for repeat in range(3):
        case = tmp_path / f"stepped-positive-{repeat}"
        result = generate_native_hex(
            source_vertices,
            source_faces,
            case,
            target_edge_length=0.25,
            seed_density=10,
            snap_boundary=True,
            source_path=source_path,
            source_vertices=source_vertices,
            source_faces=source_faces,
            source_provenance=authoritative,
        )
        assert result.success, result.message
        names = [str(patch["name"]) for patch in parse_foam_boundary(
            case / "constant" / "polyMesh" / "boundary"
        )]
        ok, message, selected = _run_native_hex_bl(
            case,
            num_layers=1,
            growth_ratio=1.2,
            first_thickness=0.001,
            params={
                "post_layers_hex_inward_shell": True,
                "post_layers_hex_general_inward_shell": True,
                "post_layers_wall_patch_names": names,
            },
        )
        assert ok, message
        assert selected > 0
        assert "actual_layers=1" in message
        strict = audit_strict_volume_topology(case)
        assert strict.valid, strict.as_dict()
        assert strict.n_duplicate_faces == 0
        assert strict.n_nonmanifold_faces == 0
        assert strict.n_nonmanifold_cell_edges == 0
        assert strict.n_open_cell_edges == 0
        assert strict.n_inverted_cells == 0
        boundary_text = (case / "constant" / "polyMesh" / "boundary").read_text()
        assert all(group in boundary_text for group in groups)
        artifact_hashes.append(strict.artifact_sha256)
    assert artifact_hashes == [artifact_hashes[0]] * 3
