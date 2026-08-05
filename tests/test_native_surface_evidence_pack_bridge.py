from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest

from core.evaluator.native_surface_evidence_pack_bridge import (
    write_actual_surface_evidence_pack_v2,
)


def _inputs():
    points = np.array(
        [
            [-0.5, 0.0, 0.0],
            [0.5, 0.0, 0.0],
            [0.0, 0.8660254038, 0.0],
            [-0.5, 0.0, -1.0],
            [0.5, 0.0, -1.0],
            [-0.5, 0.0, -2.0],
            [0.5, 0.0, -2.0],
            [-0.5, 0.0, -3.0],
            [0.5, 0.0, -3.0],
        ],
        dtype=float,
    )
    source = np.array([[0, 2, 1]], dtype=np.int64)
    edges = np.array([[11, 0, 1, 0]], dtype=np.int64)
    layer_ids = np.array([[[3, 4]], [[5, 6]], [[7, 8]]], dtype=np.int64)
    normals = np.array([[0.0, 0.0, -1.0]], dtype=float)
    authority = {
        "source_kind": "synthetic_surface",
        "source_sha256": "source-digest",
        "boundary_mapping_sha256": "boundary-digest",
        "physical_group_sha256": "group-digest",
        "provenance": "sealed-ledger",
    }
    source_rows = [
        {
            "source_wall_edge": 11,
            "source_face": 0,
            "side": "source",
            "layer": 0,
            "patch": "wall",
            "feature": "smooth",
            "physical_group": "fluid_wall",
            "component": "main",
            "provenance": "source-ledger",
        }
    ]
    edge_rows = [
        {
            "source_wall_edge": 11,
            "source_face": 0,
            "side": "wall",
            "patch": "wall",
            "feature": "smooth",
            "physical_group": "fluid_wall",
            "component": "main",
            "provenance": "writer-ledger",
        }
        for _ in range(3)
    ]
    return points, source, edges, layer_ids, normals, authority, edge_rows, source_rows


@pytest.mark.parametrize("requested_layers, expected_records", [(0, 0), (1, 1), (3, 3)])
def test_actual_surface_snapshot_bridge_bl_matrix(
    tmp_path: Path, requested_layers: int, expected_records: int
):
    points, source, edges, layer_ids, normals, authority, edge_rows, source_rows = _inputs()
    result = write_actual_surface_evidence_pack_v2(
        tmp_path / f"surface-{requested_layers}",
        points=points,
        source_triangles=source,
        wall_edges=edges,
        layer_point_ids=layer_ids,
        face_normals=normals,
        source_authority=authority,
        edge_provenance=edge_rows,
        source_provenance=source_rows,
        requested_layers=requested_layers,
    )
    assert result["accepted"] is True, result
    assert result["authority_level"] == "L0_synthetic"
    assert result["publication_eligible"] is False
    assert len(result["transaction_runs"]) == 3
    assert len(result["direct_layer_records"]) == expected_records
    root = Path(result["evidence_root"])
    assert root.joinpath("producer-runs.tsv").is_file()
    assert root.joinpath("layers.tsv").is_file()
    assert len([line for line in root.joinpath("producer-runs.tsv").read_text().splitlines() if line]) == 3
    assert len([line for line in root.joinpath("layers.tsv").read_text().splitlines() if line]) == expected_records
    assert result["transaction_runs"][0]["candidate_geometry_digest"] == result["transaction_runs"][2]["candidate_geometry_digest"]


def test_actual_surface_snapshot_bridge_refuses_tampered_edge_provenance(tmp_path: Path):
    points, source, edges, layer_ids, normals, authority, edge_rows, source_rows = _inputs()
    edge_rows[0]["feature"] = "tampered"
    result = write_actual_surface_evidence_pack_v2(
        tmp_path / "tampered",
        points=points,
        source_triangles=source,
        wall_edges=edges,
        layer_point_ids=layer_ids,
        face_normals=normals,
        source_authority=authority,
        edge_provenance=edge_rows,
        source_provenance=source_rows,
        requested_layers=1,
    )
    assert result["accepted"] is False
    assert result["reason"] == "writer_audit_refused:persisted_direct_layer_evidence_invalid"
    assert not (tmp_path / "tampered").exists()
