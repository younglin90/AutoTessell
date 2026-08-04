from __future__ import annotations

import numpy as np


def _module():
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


def test_cpp_writer_emits_writer_owned_v2_direct_identity_records() -> None:
    points, triangles, normals, authority = _inputs()
    result = _module().generate_authoritative(
        points, triangles, normals, 1, 0.1, 1.0, 1.0e-14, authority
    )

    assert result["accepted"] is True
    assert result["status"] == "authoritative_candidate_writer_output"
    assert result["authoritative_writer"] is True
    ledger = result["ledger"]
    assert ledger["schema"] == "native-tet-bl-writer-ledger/v2"
    assert ledger["writer_owned"] is True
    assert ledger["actual_layers"] == 1
    assert ledger["source_faces"][0]["source_face_id"] == "face-wall-0"
    assert ledger["source_faces"][0]["patch"] == "inlet"
    assert ledger["boundary_children"][0]["children"][0]["output_face_id"] == "wall-face-face-wall-0"
    assert ledger["interface_children"][0]["children"][0]["output_face_id"] == "front-face-face-wall-0"
    assert ledger["edge_children"][0]["children"][0]["output_edge_id"] == "edge-edge-0-layer-1"
    assert ledger["inverse"]["tet_to_prism"]["cell-0"] == "prism-face-wall-0-1"
    assert ledger["graph_digest_pending_python_canonicalization"] is True
    assert result["publication_eligible"] is False


def test_cpp_writer_v2_is_byte_deterministic_for_direct_ids() -> None:
    inputs = _inputs()
    first = _module().generate_authoritative(
        inputs[0], inputs[1], inputs[2], 1, 0.1, 1.0, 1.0e-14, inputs[3]
    )
    second = _module().generate_authoritative(
        inputs[0], inputs[1], inputs[2], 1, 0.1, 1.0, 1.0e-14, inputs[3]
    )

    assert first["ledger"] == second["ledger"]
    np.testing.assert_array_equal(first["points"], second["points"])
    np.testing.assert_array_equal(first["tets"], second["tets"])

