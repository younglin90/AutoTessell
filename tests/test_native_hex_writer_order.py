from __future__ import annotations

import hashlib
import json
from pathlib import Path

import numpy as np

from core.generator.native_hex.mesher import _write_polymesh_hex
from core.generator.native_hex.output_source_binding import (
    HexMeasuredSourceBinding,
    write_hex_source_face_map,
)
from core.layers.native_bl import BLConfig, generate_native_bl
from core.utils.polymesh_reader import parse_foam_faces, parse_foam_labels


def _cube_case(tmp_path: Path) -> Path:
    case = tmp_path / "cube"
    points = np.asarray(
        [
            [0.0, 0.0, 0.0],
            [1.0, 0.0, 0.0],
            [1.0, 1.0, 0.0],
            [0.0, 1.0, 0.0],
            [0.0, 0.0, 1.0],
            [1.0, 0.0, 1.0],
            [1.0, 1.0, 1.0],
            [0.0, 1.0, 1.0],
        ],
        dtype=np.float64,
    )
    hexes = np.asarray([[0, 1, 2, 3, 4, 5, 6, 7]], dtype=np.int64)
    _write_polymesh_hex(points, hexes, case)
    evidence = HexMeasuredSourceBinding(
        status="pass_test_source_binding",
        source_brep_authoritative=True,
        physical_groups_authoritative=True,
        output_boundary_face_count=6,
        mapping_complete=True,
        physical_group_mapping_complete=True,
        strict_binding_complete=True,
        output_boundary_face_ids_sha256="0" * 64,
        output_to_source_face_sha256="1" * 64,
        output_physical_group_sha256="2" * 64,
        source_file_sha256="3" * 64,
        max_source_plane_distance=0.0,
        tolerance=1.0e-9,
        output_face_to_source_face=tuple(range(6)),
        output_physical_groups=tuple("wall" for _ in range(6)),
        missing_evidence=(),
    )
    handoff = write_hex_source_face_map(case, hexes, evidence)
    assert handoff["accepted"] is True
    return case


def _poly_hashes(case: Path) -> dict[str, str]:
    root = case / "constant" / "polyMesh"
    return {
        name: hashlib.sha256((root / name).read_bytes()).hexdigest()
        for name in ("points", "faces", "owner", "neighbour", "boundary")
    }


def test_native_hex_bl_emits_writer_order_ledger_for_generic_route(tmp_path: Path) -> None:
    case = _cube_case(tmp_path)
    result = generate_native_bl(
        case,
        BLConfig(
            num_layers=1,
            first_thickness=0.05,
            growth_ratio=1.2,
            wall_patch_names=["defaultWall"],
        ),
    )
    assert result.success, result
    ledger = json.loads((case / "native_hex_writer_order.json").read_text())
    poly = case / "constant" / "polyMesh"
    boundary_count = len(parse_foam_faces(poly / "faces")) - len(
        parse_foam_labels(poly / "neighbour")
    )
    rows = ledger["records"]
    assert ledger["schema"] == "autotessell/native-hex-writer-order/v2"
    assert ledger["source_map_valid"] is True
    assert len(rows) == boundary_count
    assert [row["writer_order"] for row in rows] == list(range(boundary_count))
    assert all(row["direct"] is True for row in rows)
    assert all(int(row["source_face"]) >= 0 for row in rows)
    assert len({int(row["output_face_id"]) for row in rows}) == boundary_count


def test_native_hex_bl_stale_source_map_refuses_before_mutation(tmp_path: Path) -> None:
    case = _cube_case(tmp_path)
    poly = case / "constant" / "polyMesh"
    before = _poly_hashes(case)
    with (poly / "points").open("ab") as stream:
        stream.write(b"\n")
    result = generate_native_bl(
        case,
        BLConfig(num_layers=1, first_thickness=0.05, growth_ratio=1.2),
    )
    assert result.success is False
    assert "source_map_baseline_digest_mismatch" in result.message
    assert _poly_hashes(case)["faces"] == before["faces"]
    assert not (case / "native_bl_state.json").exists()


def test_native_hex_bl_zero_layer_is_identity(tmp_path: Path) -> None:
    case = _cube_case(tmp_path)
    before = _poly_hashes(case)
    result = generate_native_bl(case, BLConfig(num_layers=0))
    assert result.success, result
    assert "BL=0 identity" in result.message
    assert _poly_hashes(case) == before
    assert not (case / "native_bl_state.json").exists()
    assert not (case / "native_hex_writer_order.json").exists()


def test_native_hex_bl_writer_order_refuses_without_source_handoff(tmp_path: Path) -> None:
    case = _cube_case(tmp_path)
    (case / "native_hex_source_face_map.json").unlink()
    result = generate_native_bl(
        case,
        BLConfig(num_layers=1, first_thickness=0.05, growth_ratio=1.2),
        engine_tag="native_hex",
    )
    assert result.success, result
    ledger = json.loads((case / "native_hex_writer_order.json").read_text())
    assert ledger["schema"] == "autotessell/native-hex-writer-order/v1"
    assert ledger["source_map_present"] is False
    assert all(int(row["source_face"]) == -1 for row in ledger["records"])
    assert all(row["direct"] is False for row in ledger["records"])


def test_native_hex_bl_lateral_faces_are_not_direct_cad_faces(tmp_path: Path) -> None:
    case = _cube_case(tmp_path)
    result = generate_native_bl(
        case,
        BLConfig(
            num_layers=1,
            first_thickness=0.05,
            growth_ratio=1.2,
            set_faces=[0],
        ),
    )
    assert result.success, result
    ledger = json.loads((case / "native_hex_writer_order.json").read_text())
    lateral = [
        row for row in ledger["records"] if row["patch"] == "bl_internal_domain"
    ]
    assert lateral
    assert all(row["direct"] is False for row in lateral)
    assert all(int(row["source_face"]) == -1 for row in lateral)
