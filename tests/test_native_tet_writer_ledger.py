from __future__ import annotations

import hashlib
import json
from pathlib import Path
from types import SimpleNamespace

from core.generator.native_tet.capsule import emit_native_tet_bl_capsule
from tests.test_native_l2_native_tet_polymesh_evidence import _write_polymesh


def test_capsule_emits_structured_writer_owned_lineage(tmp_path: Path) -> None:
    case = tmp_path / "case"
    poly = case / "constant" / "polyMesh"
    _write_polymesh(poly)
    (case / "constant" / "polyMesh_pre_bl").mkdir(parents=True)
    _write_polymesh(case / "constant" / "polyMesh_pre_bl")
    source = case / "source.stl"
    source.write_bytes(b"sealed source")
    (case / "native_bl_lineage.json").write_text(
        '{"records":[{"source_face":0,"source_vertices":[0,2,1],'
        '"patch_index":0,"layer_point_ids":[[0,2,1],[0,2,1]],'
        '"prism_cell_ids":[0]}]}',
        encoding="utf-8",
    )
    result = SimpleNamespace(direct_id_map={
        "schema": "native-tet-bl-direct-id-map/v1",
        "records": [{
            "source_face": 0,
            "source_vertices": [0, 2, 1],
            "patch_index": 0,
            "wall_face_ids": [0],
            "front_face_ids": [1],
            "final_cell_ids": [0, 1, 2],
            "layer_count": 1,
        }],
    })
    ok, message = emit_native_tet_bl_capsule(
        case,
        authority={
            "source_path": "source.stl",
            "source_sha256": hashlib.sha256(b"sealed source").hexdigest(),
            "source_authority_status": "SOURCE_VERIFIED",
            "wall_edge_eligible": True,
            "provisional": False,
            "feature": "wall",
            "patch": "wall",
            "physical_group": "fluid-wall",
            "component": "tetra",
            "provenance": "direct-id",
        },
        subdivided=result,
        requested_layers=1,
        growth_ratio=1.0,
        first_thickness=0.1,
        quality_aspect_cap=100.0,
    )

    assert ok, message
    payload = json.loads((case / "native_tet_bl_writer_ledger.json").read_text())
    assert payload["schema"] == "native-tet-bl-writer-ledger/v1"
    record = payload["records"][0]
    assert record["source_face_id"] == "face-0"
    assert record["children"]["boundary_faces"][0]["disk_face_id"] == 0
    assert record["children"]["front_faces"][0]["disk_face_id"] == 1
    assert record["children"]["cells"] == ["cell-0", "cell-1", "cell-2"]
    assert len(payload["graph_sha256"]) == 64
