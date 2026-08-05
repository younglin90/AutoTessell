from __future__ import annotations

import json
from pathlib import Path

from core.generator.native_tet.writer_ledger import (
    _digest_payload,
    validate_native_tet_writer_ledger,
)


def _payload() -> dict[str, object]:
    payload: dict[str, object] = {
        "schema": "native-tet-bl-writer-ledger/v1",
        "source_sha256": "a" * 64,
        "source_authority_status": "SOURCE_VERIFIED",
        "writer_owned_id_capsule": True,
        "requested_layers": 1,
        "actual_layers": 1,
        "records": [{
            "source_face_id": "face-0",
            "source_vertex_ids": [0, 1, 2],
            "source_edge_ids": [],
            "children": {
                "boundary_faces": [{
                    "output_face_id": "wall-0",
                    "disk_face_id": 0,
                    "vertex_ids": [0, 1, 2],
                    "layer": 0,
                    "role": "wall_boundary",
                }],
                "front_faces": [],
                "cells": ["cell-0"],
            },
            "layer_count": 1,
            "feature": "wall",
            "patch": "wall",
            "physical_group": "fluid-wall",
            "component": "tetra",
            "provenance": "writer",
        }],
    }
    payload["graph_sha256"] = _digest_payload(payload)
    return payload


def test_writer_ledger_validator_accepts_digest_bound_inverse_graph(tmp_path: Path) -> None:
    path = tmp_path / "ledger.json"
    path.write_text(json.dumps(_payload(), sort_keys=True), encoding="utf-8")

    result = validate_native_tet_writer_ledger(
        path, source_sha256="a" * 64, requested_layers=1
    )

    assert result["accepted"] is True
    assert result["source_face_count"] == 1
    assert result["child_id_count"] == 1


def test_writer_ledger_validator_refuses_tamper(tmp_path: Path) -> None:
    path = tmp_path / "ledger.json"
    payload = _payload()
    payload["records"][0]["children"]["boundary_faces"][0]["disk_face_id"] = 9
    path.write_text(json.dumps(payload, sort_keys=True), encoding="utf-8")

    result = validate_native_tet_writer_ledger(
        path, source_sha256="a" * 64, requested_layers=1
    )

    assert result["accepted"] is False
    assert "writer_ledger_graph_digest_mismatch" in result["errors"]
