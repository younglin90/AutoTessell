from __future__ import annotations

import json

import numpy as np

import core.evaluator.native_surface_bl_front_target_field_transaction as transaction
from core.evaluator.native_surface_bl_front_target_field_transaction import (
    transact_surface_wall_edge_target_field,
)


def _inputs():
    points = np.asarray(
        [
            [0.0, 0.0, 0.0],
            [1.0, 0.0, 0.0],
            [0.0, 1.0, 0.0],
        ],
        dtype=np.float64,
    )
    triangles = np.asarray([[0, 1, 2]], dtype=np.int64)
    edges = np.asarray([[11, 0, 1, 0]], dtype=np.int64)
    normals = np.asarray([[0.0, 0.0, 1.0]], dtype=np.float64)
    certificate = {
        "source_kind": "authoritative-stl-ledger",
        "raw_sha256": "a" * 64,
        "brep_hash": "b" * 64,
        "authority": "source-ledger-v1",
        "provenance": "direct-source-ledger",
    }
    provenance = [
        {
            "source_edge": "11",
            "source_face": "0",
            "wall_edge": "wall-11",
            "output_face": "out-11",
            "feature": "smooth",
            "patch": "wall",
            "physical_group": "fluid-wall",
            "component": "fixture",
            "provenance": "direct",
        }
    ]
    return points, triangles, edges, normals, certificate, provenance


def _receipt(height: float = 0.8) -> dict:
    direction = {"direction_x": 0.0, "direction_y": 0.0, "direction_z": 1.0}
    vertex_rows = [
        {
            "vertex": vertex,
            "sector": "smooth|wall|fluid-wall",
            "layer": 1,
            "requested_height": height,
            "accepted_height": height,
            "predecessor_layer": 0,
            "source_edge_ids": [11],
            **direction,
        }
        for vertex in (0, 1)
    ]
    edge_row = {
        "source_edge_id": 11,
        "source_face_id": 0,
        "source_vertex_a": 0,
        "source_vertex_b": 1,
        "sector": "smooth|wall|fluid-wall",
        "layer": 1,
        "predecessor_layer": 0,
        "requested_height": height,
        "accepted_height": height,
        "accepted_height_a": height,
        "accepted_height_b": height,
        "tangential_target": 1.0,
        "metric_aspect": max(1.0, 1.0 / height),
        "height_skew": 0.0,
        "source_edge": "11",
        "source_face": "0",
        "wall_edge": "wall-11",
        "output_face": "out-11",
        "component": "fixture",
        "provenance": "direct",
        **direction,
    }
    return {
        "accepted": True,
        "status": "target_field_receipt_sealed",
        "receipt_sealed": True,
        "source_authority_bound": True,
        "authority_checked": True,
        "target_field": True,
        "runtime_route": "default_off",
        "publication_eligible": False,
        "route_calls": 0,
        "requested_layers": 1,
        "actual_layers": 1,
        "target_vertices": vertex_rows,
        "target_edges": [edge_row],
        "quality": {
            "max_metric_aspect": max(1.0, 1.0 / height),
            "max_endpoint_height_skew": 0.0,
        },
    }


def _call(receipt: dict, layers: int = 1):
    points, triangles, edges, normals, certificate, provenance = _inputs()
    return transact_surface_wall_edge_target_field(
        points,
        triangles,
        edges,
        normals,
        receipt,
        certificate,
        provenance,
        layers,
    )


def test_bl0_is_authority_checked_identity_and_never_calls_writer(monkeypatch):
    points, triangles, edges, normals, certificate, provenance = _inputs()

    def forbidden(*_args, **_kwargs):
        raise AssertionError("BL0 must bypass the writer")

    monkeypatch.setattr(transaction, "write_authoritative_surface_wall_edge_strip", forbidden)
    result = transact_surface_wall_edge_target_field(
        points,
        triangles,
        edges,
        normals,
        {"tampered": True},
        certificate,
        provenance,
        0,
    )
    assert result["accepted"] is True
    assert result["status"] == "surface_bl_front_target_field_transaction_bl0_identity"
    assert result["receipt_consumed"] is False
    assert result["generated_faces"] == []
    assert result["output_digest"] == result["source_digest"]


def test_positive_transaction_accepts_shared_direct_id_strip_deterministically():
    first = _call(_receipt(0.8))
    second = _call(_receipt(0.8))
    assert json.dumps(first, sort_keys=True) == json.dumps(second, sort_keys=True)
    assert first["accepted"] is True, first
    assert first["status"] == "surface_bl_front_target_field_transaction_sealed"
    assert first["actual_layers"] == 1
    assert first["source_authority_bound"] is True
    assert first["direct_lineage"] is True
    assert first["shared_front"] is True
    assert len(first["generated_vertices"]) == 2
    assert len(first["generated_faces"]) == 3
    assert first["topology_invalid"] == 0
    assert first["topology_inverted"] == 0
    assert first["topology_duplicate"] == 0
    assert first["topology_non_manifold"] == 0
    assert first["quality"]["max_skewness"] <= 0.50
    assert first["quality"]["max_triangle_aspect_ratio"] <= 10.0
    assert first["quality"]["max_non_orthogonality"] <= 75.0


def test_target_metric_pass_does_not_waive_final_triangle_quality():
    result = _call(_receipt(0.1))
    assert result["accepted"] is False
    assert result["status"] == "refused_rollback"
    assert result["reason"] == "strip_diagonal_no_quality_admissible"
    assert result["actual_layers"] == 0
    assert result["generated_vertices"] == []
    assert result["generated_faces"] == []
    assert result["provenance"] == []
    assert result["candidate_discarded"] is True
    assert result["receipt_consumed"] is True


def test_tampered_height_and_source_id_refuse_before_writer():
    tampered_height = _receipt(0.8)
    tampered_height["target_edges"][0]["accepted_height_a"] = 0.7
    first = _call(tampered_height)
    assert first["accepted"] is False
    assert first["reason"] == "target_edge_vertex_height_mismatch"
    assert first["generated_faces"] == []

    tampered_source = _receipt(0.8)
    tampered_source["target_edges"][0]["source_vertex_a"] = 2
    second = _call(tampered_source)
    assert second["accepted"] is False
    assert second["reason"] == "target_edge_source_id_mismatch"
    assert second["generated_faces"] == []


def test_receipt_digest_tamper_refuses_atomically():
    receipt = _receipt(0.8)
    receipt["receipt_digest"] = "0" * 64
    result = _call(receipt)
    assert result["accepted"] is False
    assert result["reason"] == "target_receipt_digest_mismatch"
    assert result["generated_faces"] == []
    assert result["actual_layers"] == 0
