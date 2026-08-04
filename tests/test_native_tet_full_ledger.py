from __future__ import annotations

from copy import deepcopy

from core.generator.native_tet.full_ledger import (
    _graph_digest,
    validate_native_tet_full_ledger,
)


def _payload() -> dict[str, object]:
    payload: dict[str, object] = {
        "schema": "native-tet-bl-writer-ledger/v2",
        "source_sha256": "a" * 64,
        "semantic_ledger_sha256": "b" * 64,
        "bl_config_sha256": "c" * 64,
        "quality_policy_sha256": "d" * 64,
        "artifact_tree_sha256": "e" * 64,
        "writer_owned": True,
        "actual_layers": 1,
        "source_faces": [{
            "source_face_id": "f0",
            "source_vertex_ids": [0, 1, 2],
            "source_edge_ids": ["e0", "e1", "e2"],
        }],
        "boundary_children": [{
            "source_face_id": "f0",
            "children": [{"output_face_id": "b0", "disk_face_id": 0, "vertex_ids": [0, 1, 2]}],
        }],
        "interface_children": [{
            "source_face_id": "f0",
            "children": [{"output_face_id": "i0", "disk_face_id": 1, "vertex_ids": [3, 4, 5]}],
        }],
        "edge_children": [
            {"source_edge_id": edge, "children": [{"output_edge_id": f"{edge}-l1"}]}
            for edge in ("e0", "e1", "e2")
        ],
        "prisms": [{
            "prism_parent_id": "p0",
            "source_face_id": "f0",
            "layer": 1,
            "vertex_ids": [0, 1, 2, 3, 4, 5],
            "child_tet_ids": ["c0", "c1", "c2"],
        }],
        "cells": [
            {
                "output_cell_id": cell,
                "disk_cell_id": index,
                "prism_parent_id": "p0",
                "layer": 1,
                "local_tet_index": index,
                "vertex_ids": [0, 1, 2, 3],
                "signed_volume": 0.1,
            }
            for index, cell in enumerate(("c0", "c1", "c2"))
        ],
        "inverse": {
            "boundary_face_to_source": {"b0": "f0"},
            "tet_to_prism": {"c0": "p0", "c1": "p0", "c2": "p0"},
        },
    }
    payload["graph_sha256"] = _graph_digest(payload)
    return payload


def test_full_ledger_accepts_face_edge_prism_cell_inverse_graph() -> None:
    result = validate_native_tet_full_ledger(
        _payload(), source_sha256="a" * 64, requested_layers=1
    )

    assert result["accepted"] is True
    assert result["source_edge_count"] == 3
    assert result["prism_count"] == 1
    assert result["cell_count"] == 3


def test_full_ledger_refuses_missing_tet_inverse() -> None:
    payload = deepcopy(_payload())
    del payload["inverse"]["tet_to_prism"]["c2"]
    payload["graph_sha256"] = _graph_digest(payload)

    result = validate_native_tet_full_ledger(
        payload, source_sha256="a" * 64, requested_layers=1
    )

    assert result["accepted"] is False
    assert "tet_inverse_coverage_mismatch" in result["errors"]
