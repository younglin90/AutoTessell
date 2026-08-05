from __future__ import annotations

import hashlib

import numpy as np

from core.preprocessor.native_tri.authority_ingress_receipt import (
    _array_digest,
    validate_native_tri_authority_ingress,
)


def _receipt(points, triangles, orientation, source=b"tri-source", *, kind="stl"):
    return {
        "schema": "NativeTriAuthorityReceipt/v1",
        "source_kind": kind,
        "source_sha256": hashlib.sha256(source).hexdigest(),
        "source_byte_count": len(source),
        "reader_id": "tri-reader/v1",
        "issuer": "fixture-author",
        "provenance": "source-authored-fixture",
        "point_digest": _array_digest(np.ascontiguousarray(np.asarray(points, dtype=np.float64))),
        "triangle_digest": _array_digest(np.ascontiguousarray(np.asarray(triangles, dtype=np.int64))),
        "orientation_digest": _array_digest(np.ascontiguousarray(np.asarray(orientation, dtype=np.bool_))),
        "trust_policy": {"root": "fixture-root", "policy": "registered-test"},
        "faces": [
            {
                "face_id": i,
                "vertices": list(face),
                "feature": "flat",
                "patch": "wall",
                "physical_group": "fluid_wall",
                "component": "main",
                "provenance": "direct-source",
            }
            for i, face in enumerate(triangles)
        ],
        "wall_edges": [
            {
                "edge_id": "edge-0",
                "curve_id": "curve-wall",
                "endpoints": [0, 1],
                "owner_face": 0,
                "directed": True,
                "order_index": 0,
                "feature": "flat",
                "patch": "wall",
                "physical_group": "fluid_wall",
                "component": "main",
                "provenance": "direct-source",
            }
        ],
    }


def test_native_tri_authority_ingress_seals_open_wall_source_deterministically():
    points = np.array([[0.0, 0.0, 0.0], [1.0, 0.0, 0.0], [0.0, 1.0, 0.0]])
    triangles = np.array([[0, 1, 2]], dtype=np.int64)
    orientation = [False]
    receipt = _receipt(points, triangles, orientation)
    first = validate_native_tri_authority_ingress(b"tri-source", points, triangles, orientation, receipt)
    second = validate_native_tri_authority_ingress(b"tri-source", points, triangles, orientation, receipt)
    assert first == second
    assert first["accepted"] is True
    assert first["eligible_for_tri_bl"] is True
    assert first["boundary_edge_count"] == 1
    assert first["route_calls"] == 0
    assert first["publication_eligible"] is False


def test_closed_or_missing_wall_receipt_stays_nonrelease_and_drift_refuses():
    points = np.array([[0.0, 0.0, 0.0], [1.0, 0.0, 0.0], [0.0, 1.0, 0.0]])
    triangles = np.array([[0, 1, 2]], dtype=np.int64)
    receipt = _receipt(points, triangles, [False])
    receipt["wall_edges"] = []
    result = validate_native_tri_authority_ingress(b"tri-source", points, triangles, [False], receipt)
    assert result["accepted"] is True
    assert result["eligible_for_tri_bl"] is False
    assert result["reason"] == "tri_source_verified_wall_boundary_absent"

    drift = _receipt(points, triangles, [False])
    drift["source_sha256"] = "0" * 64
    result = validate_native_tri_authority_ingress(b"tri-source", points, triangles, [False], drift)
    assert result["accepted"] is False
    assert result["reason"] == "tri_receipt_source_sha256_mismatch"
    assert result["route_calls"] == 0


def test_label_cad_and_nonboundary_fail_closed():
    points = np.array([[0.0, 0.0, 0.0], [1.0, 0.0, 0.0], [0.0, 1.0, 0.0]])
    triangles = np.array([[0, 1, 2]], dtype=np.int64)
    receipt = _receipt(points, triangles, [False], kind="step")
    receipt.pop("brep_face_map", None)
    result = validate_native_tri_authority_ingress(b"tri-source", points, triangles, [False], receipt)
    assert result["accepted"] is False
    assert result["reason"] == "tri_cad_brep_map_missing"

    receipt = _receipt(points, triangles, [False])
    receipt["faces"][0]["patch"] = ""
    result = validate_native_tri_authority_ingress(b"tri-source", points, triangles, [False], receipt)
    assert result["accepted"] is False
    assert result["reason"] == "tri_face_semantic_label_incomplete"

    points = np.array([[0., 0., 0.], [1., 0., 0.], [0., 1., 0.], [1., 1., 0.]])
    triangles = np.array([[0, 1, 2], [1, 3, 2]], dtype=np.int64)
    receipt = _receipt(points, triangles, [False, False])
    receipt["wall_edges"][0]["endpoints"] = [0, 3]
    result = validate_native_tri_authority_ingress(b"tri-source", points, triangles, [False, False], receipt)
    assert result["accepted"] is False
    assert result["reason"] == "tri_wall_edge_not_source_boundary"
