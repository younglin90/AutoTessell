from __future__ import annotations

import hashlib
import math

import numpy as np

from core.layers.native_bl_atomic_certificate import canonical_bytes
from core.preprocessor.native_tri_quad.actual_mixed_bl_transaction import (
    run_native_tri_quad_actual_mixed_bl_transaction,
)
from core.preprocessor.native_tri_quad.independent_quality_readback import (
    audit_native_tri_quad_actual_mixed_bl_artifact,
    commit_native_tri_quad_producer_auditor_quality_gate,
)


DIHEDRAL_DEGREES = list(range(19)) + [30]
SOURCE = b"tri-quad-distribution-quality-matrix-accordion-v1"


def _build_points() -> np.ndarray:
    alphas = [0.0]
    for index, delta in enumerate(DIHEDRAL_DEGREES):
        alphas.append(alphas[-1] + (delta if index % 2 == 0 else -delta))
    # Twenty interior junctions need twenty-one quad normals; the final
    # boundary vertex repeats the last slope so the ribbon has 22 top points.
    alphas.append(alphas[-1])
    points = []
    for index in range(22):
        points.append([float(index), 0.0, 0.0])
    for alpha in alphas:
        points.append([float(len(points) - 22), 1.0, math.tan(math.radians(alpha))])
    points.extend([[0.0, 0.0, 5.0], [1.0, 0.0, 5.0], [0.5, 0.8660254037844386, 5.0]])
    return np.asarray(points, dtype=np.float64)


POINTS = _build_points()
TRIANGLES = np.asarray([[44, 45, 46]], dtype=np.int64)
QUADS = np.asarray(
    [[index, index + 1, 22 + index + 1, 22 + index] for index in range(21)],
    dtype=np.int64,
)
WALL_EDGES = (
    [(index, index + 1) for index in range(21)]
    + [(21, 43)]
    + [(22 + index, 22 + index - 1) for index in range(21, 0, -1)]
    + [(22, 0)]
)
WALL_LOOP = [
    {"edge_id": index, "v0": v0, "v1": v1, "feature": "wall",
     "patch": "accordion", "physical_group": "fluid_wall", "component": "ribbon-1",
     "provenance": "source"}
    for index, (v0, v1) in enumerate(WALL_EDGES, start=100)
]
CO_NORMALS = [[0.0, 0.0, 1.0]] * len(WALL_LOOP)
REFERENCE_NORMAL = [0.01, 0.0, math.sqrt(1.0 - 0.01**2)]
for _row in WALL_LOOP:
    _row["reference_normal"] = list(REFERENCE_NORMAL)


def _digest(value: np.ndarray) -> str:
    return hashlib.sha256(canonical_bytes({
        "dtype": str(value.dtype), "shape": list(value.shape),
        "c_order_bytes_hex": value.tobytes(order="C").hex(),
    })).hexdigest()


def _face(face_id: str) -> dict[str, str]:
    return {"face_id": face_id, "feature": "wall", "patch": "accordion",
            "physical_group": "fluid_wall", "component": "ribbon-1",
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
        "trust_policy": {"bundle": "local-test"},
        "triangles": [_face("t0")],
        "quads": [_face(f"q{index}") for index in range(len(QUADS))],
        "mixed_lineage": (
            [{"kind": "tri", "source_id": "t0", "output_ids": ["t0"], **_face("t0")}]
            + [{"kind": "quad", "source_id": f"q{index}", "output_ids": [f"q{index}"],
                **_face(f"q{index}")} for index in range(len(QUADS))]
        ),
        "wall_loop": [{"edge_id": row["edge_id"], **_face(str(row["edge_id"]))}
                      for row in WALL_LOOP],
    }


def _produce(layers: int) -> dict:
    return run_native_tri_quad_actual_mixed_bl_transaction(
        SOURCE, POINTS, TRIANGLES, QUADS, _receipt(), WALL_LOOP, CO_NORMALS,
        [] if layers == 0 else [0.05] * layers, layers, 1.0,
    )


def _audit(layers: int, produced: dict) -> dict:
    return audit_native_tri_quad_actual_mixed_bl_artifact(
        POINTS, TRIANGLES, QUADS, _receipt(), WALL_LOOP, CO_NORMALS,
        [] if layers == 0 else [0.05] * layers, produced, layers, 1.0,
    )


def test_multiedge_distribution_matrix_is_actual_and_gated_for_bl0_bl1_bl3():
    expected = {"count": 20, "p50": 9.0, "p95": 18.0, "p99": 30.0, "max": 30.0}
    for layers in (0, 1, 3):
        produced = _produce(layers)
        assert produced["accepted"] is True
        certificate = _audit(layers, produced)
        assert certificate["accepted"] is True
        dihedral = certificate["quality"]["adjacent_face_normal_dihedral_degrees"]
        assert dihedral["count"] == expected["count"]
        for key in ("p50", "p95", "p99", "max"):
            assert math.isclose(dihedral[key], expected[key], rel_tol=0.0, abs_tol=1e-12)
        assert dihedral["min"] == 0.0
        distributions = certificate["quality"]["distributions"]
        assert distributions["retained_triangle"]["count"] == 1
        assert distributions["paired_core_quad"]["count"] == 21
        assert distributions["strip_quad"]["count"] == len(WALL_LOOP) * layers
        assert distributions["aggregate"]["count"] == 22 + len(WALL_LOOP) * layers
        for row in distributions.values():
            assert row["ordered_sample_digest"]
            assert row["skewness"]["p50"] <= row["skewness"]["p95"] <= row["skewness"]["p99"] <= row["skewness"]["max"]
        if layers == 0:
            assert distributions["strip_quad"]["applicable"] is False
            assert distributions["strip_quad"]["count"] == 0
        else:
            leakage = certificate["quality"]["wall_front_tangential_leakage"]
            assert leakage["count"] == len(WALL_LOOP) * layers
            assert leakage["min"] > 0.0
            assert leakage["max"] < 0.015
        committed = commit_native_tri_quad_producer_auditor_quality_gate(
            POINTS, TRIANGLES, QUADS, _receipt(), WALL_LOOP, CO_NORMALS,
            [] if layers == 0 else [0.05] * layers, produced, certificate, layers, 1.0,
        )
        assert committed["accepted"] is True
        assert committed["committed"] is True


def test_multiedge_certificate_digest_and_legacy_schema_are_rejected():
    produced = _produce(1)
    certificate = _audit(1, produced)
    certificate["quality"]["distributions"]["aggregate"]["skewness"]["p99"] = 99.0
    result = commit_native_tri_quad_producer_auditor_quality_gate(
        POINTS, TRIANGLES, QUADS, _receipt(), WALL_LOOP, CO_NORMALS, [0.05],
        produced, certificate, 1, 1.0,
    )
    assert result["accepted"] is False
    assert result["candidate_discarded"] is True

    legacy = _audit(1, produced)
    legacy["auditor_schema"] = "TriQuadIndependentQualityCertificate/v3"
    result = commit_native_tri_quad_producer_auditor_quality_gate(
        POINTS, TRIANGLES, QUADS, _receipt(), WALL_LOOP, CO_NORMALS, [0.05],
        produced, legacy, 1, 1.0,
    )
    assert result["accepted"] is False
    assert result["candidate_discarded"] is True


def test_folded_inner_face_refuses_quality_gate():
    produced = _produce(1)
    produced["points"] = [list(point) for point in produced["points"]]
    produced["points"][22 + 2][2] += 2.0
    certificate = _audit(1, produced)
    assert certificate["accepted"] is False or certificate["candidate_discarded"] is True


def test_three_fresh_process_replays_are_byte_identical_per_bl_mode():
    for layers in (0, 1, 3):
        certificates = [_audit(layers, _produce(layers)) for _ in range(3)]
        assert all(c["accepted"] is True for c in certificates)
        assert len({c["independent_certificate_digest"] for c in certificates}) == 1
        assert len({canonical_bytes(c) for c in certificates}) == 1
        commits = [
            commit_native_tri_quad_producer_auditor_quality_gate(
                POINTS, TRIANGLES, QUADS, _receipt(), WALL_LOOP, CO_NORMALS,
                [] if layers == 0 else [0.05] * layers,
                _produce(layers), certificates[0], layers, 1.0,
            )
            for _ in range(3)
        ]
        assert all(c["accepted"] is True and c["committed"] is True for c in commits)
        assert len({canonical_bytes(c) for c in commits}) == 1
