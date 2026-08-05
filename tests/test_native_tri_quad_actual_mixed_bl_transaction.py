from __future__ import annotations

import hashlib

import numpy as np

from core.layers.native_bl_atomic_certificate import canonical_bytes
from core.preprocessor.native_tri_quad.actual_mixed_bl_transaction import (
    run_native_tri_quad_actual_mixed_bl_transaction,
)


SOURCE = b"tri-quad-actual-mixed-open-source-v1"
POINTS = np.asarray(
    [[0.0, 0.0, 0.0], [1.0, 0.0, 0.0], [0.0, 1.0, 0.0], [1.0, 1.0, 0.0],
     [2.0, 0.0, 0.0], [3.0, 0.0, 0.0], [2.5, 0.8660254037844386, 0.0]],
    dtype=np.float64,
)
TRIANGLES = np.asarray([[4, 5, 6]], dtype=np.int64)
QUADS = np.asarray([[0, 1, 3, 2]], dtype=np.int64)
WALL_LOOP = [
    {"edge_id": i, "v0": a, "v1": b, "feature": "wall", "patch": "wall-1",
     "physical_group": "fluid_wall", "component": "body-1", "provenance": "source",
     "source_face": "t0" if i < 2 else "q0"}
    for i, (a, b) in enumerate(((0, 1), (1, 3), (3, 2), (2, 0)), start=10)
]
CO_NORMALS = [[0.0, 0.0, 1.0]] * 4


def _digest(value: np.ndarray) -> str:
    return hashlib.sha256(canonical_bytes({
        "dtype": str(value.dtype), "shape": list(value.shape),
        "c_order_bytes_hex": value.tobytes(order="C").hex(),
    })).hexdigest()


def _face(face_id: str) -> dict[str, str]:
    return {"face_id": face_id, "feature": "wall", "patch": "wall-1",
            "physical_group": "fluid_wall", "component": "body-1",
            "provenance": "source"}


def _receipt() -> dict:
    return {
        "schema": "TriQuadAuthorityReceipt/v1",
        "source_sha256": hashlib.sha256(SOURCE).hexdigest(),
        "source_byte_count": len(SOURCE), "reader_id": "reader-v1",
        "issuer": "owner", "provenance": "source-ledger",
        "point_digest": _digest(POINTS), "triangle_digest": _digest(TRIANGLES),
        "quad_digest": _digest(QUADS), "product_identity": "tri_plus_quad",
        "tri_clone": False, "quad_relabel": False,
        "trust_policy": {"bundle": "local-test"}, "triangles": [_face("t0")],
        "quads": [_face("q0")],
        "mixed_lineage": [
            {"kind": "tri", "source_id": "t0", "output_ids": ["t0"], **_face("t0")},
            {"kind": "quad", "source_id": "q0", "output_ids": ["q0"], **_face("q0")},
        ],
        "wall_loop": [{"edge_id": row["edge_id"], **_face(str(row["edge_id"]))} for row in WALL_LOOP],
    }


def _run(layers: int, *, heights=None, wall_loop=WALL_LOOP, co_normals=CO_NORMALS):
    return run_native_tri_quad_actual_mixed_bl_transaction(
        SOURCE, POINTS, TRIANGLES, QUADS, _receipt(), wall_loop, co_normals,
        heights if heights is not None else [0.1] * layers, layers, 1.0,
    )


def test_bl0_is_exact_mixed_identity_and_does_not_publish():
    result = _run(0, heights=[])
    assert result["accepted"] is True
    assert result["reason"] == "disabled_identity"
    assert result["points"] == POINTS.tolist()
    assert result["triangles"] == TRIANGLES.tolist()
    assert result["quads"] == QUADS.tolist()
    assert result["strip_quads"] == []
    assert result["actual_layers"] == 0
    assert result["publication_eligible"] is False
    assert result["runtime_route"] == "private_default_off"


def test_bl1_emits_independent_strip_lineage_and_quality_rows():
    result = _run(1)
    assert result["accepted"] is True
    assert result["requested_layers"] == result["actual_layers"] == 1
    assert len(result["points"]) == len(POINTS) + 4
    assert len(result["strip_quads"]) == 4
    assert {row["layer"] for row in result["strip_map"]} == {1}
    assert {row["source_wall_edge"] for row in result["strip_map"]} == {10, 11, 12, 13}
    assert len(result["triangle_map"]) == 1 and len(result["quad_map"]) == 1
    assert max(row["aspect_ratio"] for row in result["quality"]["rows"]) <= 10.0
    assert all(row["wall_front_non_orthogonality"] == 0.0 for row in result["quality"]["rows"])
    assert result["candidate_discarded"] is False
    assert result["publication_eligible"] is False


def test_bl3_emits_three_complete_layers_with_direct_ids():
    result = _run(3, heights=[0.1, 0.1, 0.1])
    assert result["accepted"] is True
    assert result["actual_layers"] == 3
    assert len(result["points"]) == len(POINTS) + 12
    assert len(result["strip_quads"]) == 12
    assert {row["layer"] for row in result["strip_map"]} == {1, 2, 3}
    assert all(row["feature"] == "wall" and row["physical_group"] == "fluid_wall"
               for row in result["strip_map"])


def test_bad_schedule_rolls_back_without_candidate():
    result = _run(1, heights=[0.0])
    assert result["accepted"] is False
    assert result["actual_layers"] == 0
    assert result["candidate_discarded"] is True
    assert result["strip_quads"] == []


def test_conflicting_vertex_conormal_rolls_back():
    normals = [[0.0, 0.0, 1.0], [0.0, 0.0, 1.0], [0.0, 0.0, -1.0], [0.0, 0.0, 1.0]]
    result = _run(1, co_normals=normals)
    assert result["accepted"] is False
    assert result["reason"] == "wall_conormal_vertex_conflict"
    assert result["candidate_discarded"] is True


def test_authority_tamper_is_rejected_before_transaction():
    result = run_native_tri_quad_actual_mixed_bl_transaction(
        SOURCE, POINTS, TRIANGLES, QUADS,
        {**_receipt(), "quad_digest": "0" * 64}, WALL_LOOP, CO_NORMALS, [0.1], 1, 1.0,
    )
    assert result["accepted"] is False
    assert result["reason"].startswith("authority_ingress:")
    assert result["candidate_discarded"] is True

