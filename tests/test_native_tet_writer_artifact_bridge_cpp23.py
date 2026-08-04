from __future__ import annotations

import numpy as np



def _writer():
    import native_tet_bl_writer

    return native_tet_bl_writer


def _inputs():
    points = np.asarray(
        [[0.0, 0.0, 0.0], [1.0, 0.0, 0.0], [0.0, 1.0, 0.0]],
        dtype=np.float64,
    )
    triangles = np.asarray([[0, 1, 2]], dtype=np.int64)
    normals = np.asarray([[0.0, 0.0, 1.0]] * 3, dtype=np.float64)
    authority = {
        "source_sha256": "a" * 64,
        "semantic_ledger_sha256": "b" * 64,
        "bl_config_sha256": "c" * 64,
        "quality_policy_sha256": "d" * 64,
        "artifact_tree_sha256": "e" * 64,
        "source_faces": [{
            "source_face_id": "face-wall-0",
            "source_vertex_ids": [0, 1, 2],
            "source_edge_ids": ["edge-0", "edge-1", "edge-2"],
            "feature": "wall",
            "patch": "inlet",
            "physical_group": "fluid-wall",
            "component": "component-0",
            "provenance": "fixture-source",
        }],
        "source_edges": [
            {"source_edge_id": "edge-0", "vertex_ids": [0, 1]},
            {"source_edge_id": "edge-1", "vertex_ids": [1, 2]},
            {"source_edge_id": "edge-2", "vertex_ids": [2, 0]},
        ],
    }
    return points, triangles, normals, authority


def test_writer_bridge_uses_graph_serializer_face_ids_and_removes_pending_marker() -> None:
    points, triangles, normals, authority = _inputs()
    result = _writer().generate_authoritative_artifact(
        points, triangles, normals, 1, 0.1, 1.0, 1.0e-14, authority
    )

    assert result["accepted"] is True
    assert result["status"] == "authoritative_candidate_artifact_bridge"
    assert result["authoritative_artifact_bridge"] is True
    assert result["collision_surface_source"] == "writer_owned_graph_faces"
    assert result["ledger"]["graph_binding"] == "direct_writer_vertex_cycle"
    assert "graph_digest_pending_python_canonicalization" not in result["ledger"]
    assert result["ledger"]["graph_sha256"] == result["artifact"]["graph_sha256"]
    boundary_child = result["ledger"]["boundary_children"][0]["children"][0]
    interface_child = result["ledger"]["interface_children"][0]["children"][0]
    assert boundary_child["graph_face_id"].startswith("face-")
    assert interface_child["graph_face_id"].startswith("face-")
    assert boundary_child["disk_face_id"] == result["artifact"]["disk_face_ids"][boundary_child["graph_face_id"]]


def test_writer_bridge_bl0_does_no_artifact_work() -> None:
    points, triangles, normals, authority = _inputs()
    result = _writer().generate_authoritative_artifact(
        points, triangles, normals, 0, 0.0, 1.0, 1.0e-14, authority
    )

    assert result["accepted"] is True
    assert result["status"] == "bl0_identity_artifact_bridge"
    assert result["artifact_bridge_work_performed"] is False
    assert result["writer_sidecar_emitted"] is False

