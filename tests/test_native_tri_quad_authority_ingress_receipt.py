from __future__ import annotations

import hashlib

import numpy as np

from core.layers.native_bl_atomic_certificate import canonical_bytes
from core.preprocessor.native_tri_quad.authority_ingress_receipt import (
    validate_native_tri_quad_authority_ingress,
)


SOURCE = b"tri-quad-authoritative-source-v1"
POINTS = np.asarray([[0.0, 0.0, 0.0], [1.0, 0.0, 0.0], [0.0, 1.0, 0.0], [1.0, 1.0, 0.0]], dtype=np.float64)
TRIANGLES = np.asarray([[0, 1, 2]], dtype=np.int64)
QUADS = np.asarray([[0, 1, 3, 2]], dtype=np.int64)


def _digest(value: np.ndarray) -> str:
    return hashlib.sha256(canonical_bytes({
        "dtype": str(value.dtype), "shape": list(value.shape),
        "c_order_bytes_hex": value.tobytes(order="C").hex(),
    })).hexdigest()


def _face(face_id: str) -> dict[str, str]:
    return {"face_id": face_id, "feature": "wall", "patch": "wall-1",
            "physical_group": "fluid_wall", "component": "body-1",
            "provenance": "authoritative-source"}


def _receipt(*, wall: bool = True, tri_clone: bool = False, quad_relabel: bool = False) -> dict:
    result = {
        "schema": "TriQuadAuthorityReceipt/v1",
        "source_sha256": hashlib.sha256(SOURCE).hexdigest(),
        "source_byte_count": len(SOURCE), "reader_id": "test-reader-v1",
        "issuer": "test-authority", "provenance": "raw-source-ledger",
        "point_digest": _digest(POINTS), "triangle_digest": _digest(TRIANGLES),
        "quad_digest": _digest(QUADS), "product_identity": "tri_plus_quad",
        "tri_clone": tri_clone, "quad_relabel": quad_relabel,
        "trust_policy": {"source": "exact", "output": "direct-id-only"},
        "triangles": [_face("t0")], "quads": [_face("q0")],
        "mixed_lineage": [
            {"kind": "tri", "source_id": "t0", "output_ids": ["t0"], **_face("t0")},
            {"kind": "quad", "source_id": "q0", "output_ids": ["q0"], **_face("q0")},
        ],
    }
    if wall:
        result["wall_loop"] = [{"edge_id": "e0", **_face("e0")}]
    return result


def _call(receipt: dict):
    return validate_native_tri_quad_authority_ingress(SOURCE, POINTS, TRIANGLES, QUADS, receipt)


def test_mixed_authority_receipt_seals_with_wall_boundary():
    result = _call(_receipt())
    assert result["accepted"] is True
    assert result["status"] == "tri_quad_authority_ingress_sealed"
    assert result["eligible_for_tri_quad_bl"] is True
    assert result["triangle_count"] == 1 and result["quad_count"] == 1
    assert result["lineage_count"] == 2
    assert result["route_calls"] == 0 and result["publication_eligible"] is False


def test_source_can_be_verified_but_bl_is_ineligible_without_wall_loop():
    result = _call(_receipt(wall=False))
    assert result["accepted"] is True
    assert result["eligible_for_tri_quad_bl"] is False
    assert result["reason"] == "tri_quad_mixed_source_verified_wall_boundary_absent"


def test_product_identity_rejects_clone_or_relabel_routes():
    assert _call(_receipt(tri_clone=True))["reason"] == "tri_quad_product_identity_invalid"
    assert _call(_receipt(quad_relabel=True))["reason"] == "tri_quad_product_identity_invalid"


def test_digest_mismatch_is_refused_before_native_route():
    receipt = _receipt()
    receipt["quad_digest"] = "0" * 64
    result = _call(receipt)
    assert result["accepted"] is False
    assert result["reason"] == "tri_quad_receipt_quad_digest_mismatch"
    assert result["candidate_discarded"] is True
    assert result["route_calls"] == 0


def test_direct_lineage_is_required():
    receipt = _receipt()
    receipt.pop("mixed_lineage")
    result = _call(receipt)
    assert result["accepted"] is False
    assert result["reason"] == "tri_quad_direct_lineage_missing"

