from __future__ import annotations

import hashlib

import numpy as np

from core.preprocessor.native_quad.authority_ingress_receipt import (
    _digest,
    validate_strict_quad_authority_ingress,
)


def _receipt(points, triangles, source=b"quad-source"):
    return {
        "schema": "StrictQuadAuthorityReceipt/v1",
        "source_sha256": hashlib.sha256(source).hexdigest(),
        "source_byte_count": len(source),
        "reader_id": "quad-reader/v1",
        "issuer": "fixture-author",
        "provenance": "source-authored-fixture",
        "point_digest": _digest(np.asarray(points, dtype=np.float64)),
        "triangle_digest": _digest(np.asarray(triangles, dtype=np.int64)),
        "fixed_pair_digest": "fixed-pair-sha",
        "trust_policy": {"root": "fixture-root"},
        "faces": [
            {
                "face_id": i,
                "feature": "flat",
                "patch": "wall",
                "physical_group": "fluid_wall",
                "component": "main",
                "provenance": "direct",
            }
            for i in range(len(triangles))
        ],
        "fixed_pairs": [
            {
                "pair_id": 0,
                "triangle_ids": [0, 1],
                "quad_vertices": [0, 1, 3, 2],
                "feature": "flat",
                "patch": "wall",
                "physical_group": "fluid_wall",
                "component": "main",
                "provenance": "fixed-pair-plan",
            }
        ],
        "wall_loop": [
            {
                "edge_id": "wall-0",
                "endpoints": [0, 1],
                "directed": True,
                "patch": "wall",
                "feature": "flat",
                "physical_group": "fluid_wall",
                "component": "main",
                "provenance": "direct",
            }
        ],
    }


def test_strict_quad_fixed_pair_ingress_is_deterministic_and_separate():
    points = np.array([[0., 0., 0.], [1., 0., 0.], [0., 1., 0.], [1., 1., 0.]])
    triangles = np.array([[0, 1, 2], [1, 3, 2]], dtype=np.int64)
    receipt = _receipt(points, triangles)
    first = validate_strict_quad_authority_ingress(b"quad-source", points, triangles, receipt)
    second = validate_strict_quad_authority_ingress(b"quad-source", points, triangles, receipt)
    assert first == second
    assert first["accepted"] is True
    assert first["eligible_for_strict_quad_bl"] is True
    assert first["fixed_pair_count"] == 1
    assert first["runtime_route"] == "private_default_off"


def test_closed_or_missing_wall_is_nonrelease_and_digest_drift_refuses():
    points = np.array([[0., 0., 0.], [1., 0., 0.], [0., 1., 0.], [1., 1., 0.]])
    triangles = np.array([[0, 1, 2], [1, 3, 2]], dtype=np.int64)
    receipt = _receipt(points, triangles)
    receipt["wall_loop"] = []
    result = validate_strict_quad_authority_ingress(b"quad-source", points, triangles, receipt)
    assert result["accepted"] is True
    assert result["eligible_for_strict_quad_bl"] is False
    assert result["reason"] == "strict_quad_source_verified_wall_boundary_absent"

    drift = _receipt(points, triangles)
    drift["triangle_digest"] = "0" * 64
    result = validate_strict_quad_authority_ingress(b"quad-source", points, triangles, drift)
    assert result["accepted"] is False
    assert result["reason"] == "strict_quad_receipt_triangle_digest_mismatch"


def test_fixed_pair_reuse_or_missing_semantics_refuse():
    points = np.array([[0., 0., 0.], [1., 0., 0.], [0., 1., 0.], [1., 1., 0.]])
    triangles = np.array([[0, 1, 2], [1, 3, 2]], dtype=np.int64)
    receipt = _receipt(points, triangles)
    receipt["fixed_pairs"][0]["triangle_ids"] = [0, 0]
    result = validate_strict_quad_authority_ingress(b"quad-source", points, triangles, receipt)
    assert result["accepted"] is False
    assert result["reason"] == "strict_quad_fixed_pair_triangle_reuse"

    receipt = _receipt(points, triangles)
    receipt["faces"][0]["patch"] = ""
    result = validate_strict_quad_authority_ingress(b"quad-source", points, triangles, receipt)
    assert result["accepted"] is False
    assert result["reason"] == "strict_quad_semantic_label_incomplete"
