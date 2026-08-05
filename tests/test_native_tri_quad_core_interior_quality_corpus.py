from __future__ import annotations

import hashlib

import numpy as np

from core.layers.native_bl_atomic_certificate import canonical_bytes
from core.preprocessor.native_tri_quad.actual_mixed_bl_transaction import (
    run_native_tri_quad_actual_mixed_bl_transaction,
)
from core.preprocessor.native_tri_quad.independent_quality_readback import (
    audit_native_tri_quad_actual_mixed_bl_artifact,
    commit_native_tri_quad_producer_auditor_quality_gate,
)


SOURCE = b"tri-quad-interior-core-corpus-v1"
POINTS = np.asarray(
    [[0.0, 0.0, 0.0], [2.0, 0.0, 0.0], [2.0, 1.0, 0.0], [0.0, 1.0, 0.0],
     [1.0, 0.0, 0.0], [1.0, 1.0, 0.0],
     [3.0, 0.0, 0.0], [4.0, 0.0, 0.0], [3.5, 0.8660254037844386, 0.0]],
    dtype=np.float64,
)
TRIANGLES = np.asarray([[6, 7, 8]], dtype=np.int64)
QUADS = np.asarray([[0, 4, 5, 3], [4, 1, 2, 5]], dtype=np.int64)
WALL_LOOP = [
    {"edge_id": i, "v0": a, "v1": b, "feature": "wall", "patch": "outer",
     "physical_group": "fluid_wall", "component": "body-1", "provenance": "source"}
    for i, (a, b) in enumerate(((0, 1), (1, 2), (2, 3), (3, 0)), start=20)
]
CO_NORMALS = [[0.0, 0.0, 1.0]] * 4


def _digest(value: np.ndarray) -> str:
    return hashlib.sha256(canonical_bytes({
        "dtype": str(value.dtype), "shape": list(value.shape),
        "c_order_bytes_hex": value.tobytes(order="C").hex(),
    })).hexdigest()


def _face(face_id: str) -> dict[str, str]:
    return {"face_id": face_id, "feature": "wall", "patch": "core",
            "physical_group": "fluid", "component": "body-1", "provenance": "source"}


def _receipt() -> dict:
    return {
        "schema": "TriQuadAuthorityReceipt/v1",
        "source_sha256": hashlib.sha256(SOURCE).hexdigest(), "source_byte_count": len(SOURCE),
        "reader_id": "reader-v1", "issuer": "owner", "provenance": "source-ledger",
        "point_digest": _digest(POINTS), "triangle_digest": _digest(TRIANGLES),
        "quad_digest": _digest(QUADS), "product_identity": "tri_plus_quad",
        "tri_clone": False, "quad_relabel": False, "trust_policy": {"bundle": "local-test"},
        "triangles": [_face("t0")], "quads": [_face("q0"), _face("q1")],
        "mixed_lineage": [
            {"kind": "tri", "source_id": "t0", "output_ids": ["t0"], **_face("t0")},
            {"kind": "quad", "source_id": "q0", "output_ids": ["q0"], **_face("q0")},
            {"kind": "quad", "source_id": "q1", "output_ids": ["q1"], **_face("q1")},
        ],
        "wall_loop": [{"edge_id": row["edge_id"], **_face(str(row["edge_id"]))} for row in WALL_LOOP],
    }


def _produce(layers: int):
    return run_native_tri_quad_actual_mixed_bl_transaction(
        SOURCE, POINTS, TRIANGLES, QUADS, _receipt(), WALL_LOOP, CO_NORMALS,
        [] if layers == 0 else [0.1] * layers, layers, 1.0,
    )


def _audit(layers: int, produced: dict | None = None):
    return audit_native_tri_quad_actual_mixed_bl_artifact(
        POINTS, TRIANGLES, QUADS, _receipt(), WALL_LOOP, CO_NORMALS,
        [] if layers == 0 else [0.1] * layers, produced or _produce(layers), layers, 1.0,
    )


def _gate(layers: int, produced: dict, certificate: dict):
    return commit_native_tri_quad_producer_auditor_quality_gate(
        POINTS, TRIANGLES, QUADS, _receipt(), WALL_LOOP, CO_NORMALS,
        [] if layers == 0 else [0.1] * layers, produced, certificate, layers, 1.0,
    )


def test_core_interior_edge_is_nonempty_and_quality_gated_for_all_bl_modes():
    for layers in (0, 1, 3):
        produced = _produce(layers)
        certificate = _audit(layers, produced)
        assert certificate["accepted"] is True
        dihedral = certificate["quality"]["adjacent_face_normal_dihedral_degrees"]
        if layers == 0:
            assert dihedral["applicable"] is True
        else:
            assert dihedral["applicable"] is True
        assert dihedral["count"] == 1
        assert dihedral["max"] == 0.0
        committed = _gate(layers, produced, certificate)
        assert committed["accepted"] is True
        assert committed["committed"] is True


def test_folded_interior_core_refuses_at_gate():
    produced = _produce(1)
    produced["points"] = [list(point) for point in produced["points"]]
    produced["points"][2][2] = 2.0
    certificate = _audit(1, produced)
    if certificate["accepted"]:
        assert certificate["quality"]["adjacent_face_normal_dihedral_degrees"]["max"] > 50.0
        committed = _gate(1, produced, certificate)
        assert committed["accepted"] is False
        assert committed["reason"] == "adjacent_normal_non_orthogonality_failed"
        assert committed["actual_layers"] == 0
        assert committed["candidate_discarded"] is True
    else:
        assert certificate["candidate_discarded"] is True


def test_tangential_wall_displacement_refuses_before_commit():
    produced = _produce(1)
    produced["points"] = [list(point) for point in produced["points"]]
    produced["points"][9][0] += 0.02
    certificate = _audit(1, produced)
    assert certificate["accepted"] is False
    assert certificate["candidate_discarded"] is True

