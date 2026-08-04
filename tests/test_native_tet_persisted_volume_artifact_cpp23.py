from __future__ import annotations

from pathlib import Path

import pytest


reader = pytest.importorskip("native_tet_persisted_volume_artifact")


def _authority() -> dict[str, object]:
    semantics = {
        "feature": "tetra-wall",
        "patch": "wall",
        "physical_group": "fluid-wall",
        "component": "fixture",
        "provenance": "fixture-ledger",
    }
    faces = [
        ([0, 2, 1], "face-z0"),
        ([0, 1, 3], "face-y0"),
        ([0, 3, 2], "face-x0"),
        ([1, 2, 3], "face-top"),
    ]
    source_faces = [
        {"source_face_id": source_id, "source_vertex_ids": vertices, **semantics}
        for vertices, source_id in faces
    ]
    return {
        "source_faces": source_faces,
        "cell_lineage": [{
            "entity_uid": "cell-0",
            "source_face_id": "face-z0",
            **semantics,
        }],
    }


def _write_tetra_poly_mesh(root: Path) -> None:
    root.mkdir()
    (root / "points").write_text(
        "4\n(\n(0 0 0)\n(1 0 0)\n(0 1 0)\n(0 0 1)\n)\n",
        encoding="utf-8",
    )
    (root / "faces").write_text(
        "4\n(\n3(0 2 1)\n3(0 1 3)\n3(0 3 2)\n3(1 2 3)\n)\n",
        encoding="utf-8",
    )
    (root / "owner").write_text("4\n(\n0\n0\n0\n0\n)\n", encoding="utf-8")
    (root / "neighbour").write_text("0\n(\n)\n", encoding="utf-8")
    (root / "boundary").write_text(
        "1\n(\nwall\n{\n type wall;\n nFaces 4;\n startFace 0;\n}\n)\n",
        encoding="utf-8",
    )


def test_persisted_reader_seals_bl0_volume_artifact_from_disk_only(tmp_path: Path) -> None:
    poly_mesh = tmp_path / "polyMesh"
    _write_tetra_poly_mesh(poly_mesh)
    result = reader.read_authoritative_volume_artifact(str(poly_mesh), _authority())

    assert result["accepted"] is True, result
    assert result["status"] == "native-tet-persisted-volume-artifact-sealed"
    assert result["artifact_serialization_sha256"]
    assert result["artifact_byte_size"] == len(result["artifact_bytes"])
    assert result["entity_uids"] == ["cell-0"]
    assert result["topology"]["duplicate"] == 0
    assert result["topology"]["non_manifold"] == 0
    assert result["topology"]["inverted"] == 0
    assert result["quality"]["positive_measure_min"] > 0.0
    assert result["boundary_layer"]["actual_layers"] == 0
    assert result["boundary_layer"]["layer_work"] == 0
    assert result["boundary_layer"]["rows"] == []


def test_persisted_reader_refuses_boundary_coverage_loss(tmp_path: Path) -> None:
    poly_mesh = tmp_path / "polyMesh"
    _write_tetra_poly_mesh(poly_mesh)
    authority = _authority()
    authority["source_faces"] = authority["source_faces"][:-1]
    refused = reader.read_authoritative_volume_artifact(str(poly_mesh), authority)

    assert refused["accepted"] is False
    assert refused["candidate_discarded"] is True
    assert refused["publication_eligible"] is False
