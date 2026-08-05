from __future__ import annotations

import json
from pathlib import Path

import numpy as np

from core.generator.native_hex.mesher import _write_polymesh_hex
from core.generator.native_hex.occt_xde_ingress import (
    canonical_semantic_ledger_digest,
)
from core.generator.native_hex.output_source_binding import (
    HexMeasuredSourceBinding,
    validate_native_hex_source_face_map,
    write_hex_source_face_map,
)
from core.layers.native_bl import BLConfig, generate_native_bl


def _case(tmp_path: Path) -> tuple[Path, np.ndarray, HexMeasuredSourceBinding]:
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
    return case, hexes, evidence


def _certificate() -> dict[str, object]:
    rows = [
        {
            "source_face": index,
            "feature": f"face-{index}",
            "patch": f"wall-{index}",
            "physical_group": f"group-{index}",
            "component": f"component-{index}",
            "provenance": f"source-{index}",
        }
        for index in range(6)
    ]
    return {
        "accepted": True,
        "certificate_sha256": "4" * 64,
        "face_stream_sha256": "5" * 64,
        "triangulation_stream_sha256": "6" * 64,
        "semantic_ledger_sha256": canonical_semantic_ledger_digest(rows),
        "occt_provisioning_manifest_sha256": "8" * 64,
        "occt_version": "7.8.1",
        "occt_abi": "occt-7.8.1",
    }


def test_v3_source_map_binds_accepted_occt_certificate(tmp_path: Path) -> None:
    case, hexes, evidence = _case(tmp_path)
    handoff = write_hex_source_face_map(
        case,
        hexes,
        evidence,
        ingress_certificate=_certificate(),
    )
    assert handoff["accepted"] is True
    payload = json.loads((case / "native_hex_source_face_map.json").read_text())
    assert payload["schema"] == "autotessell/native-hex-source-face-map/v3"
    assert payload["ingress_certificate_sha256"] == "4" * 64
    assert payload["ingress_face_stream_sha256"] == "5" * 64
    assert payload["ingress_triangulation_stream_sha256"] == "6" * 64
    assert payload["ingress_semantic_ledger_sha256"] == _certificate()["semantic_ledger_sha256"]
    assert payload["ingress_occt_provisioning_manifest_sha256"] == "8" * 64
    validated = validate_native_hex_source_face_map(case)
    assert validated["accepted"] is True, validated
    assert validated["schema"].endswith("/v3")
    assert validated["ingress_certificate_sha256"] == "4" * 64
    result = generate_native_bl(
        case,
        BLConfig(num_layers=1, first_thickness=0.05, growth_ratio=1.2),
    )
    assert result.success, result
    ledger = json.loads((case / "native_hex_writer_order.json").read_text())
    assert ledger["source_map_valid"] is True
    assert ledger["ingress_certificate_sha256"] == "4" * 64
    assert ledger["semantic_ledger_sha256"] == _certificate()["semantic_ledger_sha256"]
    assert ledger["provisioning_manifest_sha256"] == "8" * 64


def test_non_authoritative_occt_certificate_is_not_written(tmp_path: Path) -> None:
    case, hexes, evidence = _case(tmp_path)
    certificate = _certificate()
    certificate["accepted"] = False
    handoff = write_hex_source_face_map(
        case,
        hexes,
        evidence,
        ingress_certificate=certificate,
    )
    assert handoff == {
        "accepted": False,
        "reason": "ingress_certificate_not_authoritative",
    }
    assert not (case / "native_hex_source_face_map.json").exists()
