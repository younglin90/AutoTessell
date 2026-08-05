from __future__ import annotations

import math

import numpy as np

from core.evaluator.native_surface_bl_front_optimizer import (
    propose_surface_wall_edge_target_field,
)
from core.evaluator.native_surface_bl_front_target_field_transaction import (
    transact_surface_wall_edge_target_field,
)


def _hexagon_fixture():
    points = np.asarray(
        [
            [math.cos(2.0 * math.pi * i / 6.0), math.sin(2.0 * math.pi * i / 6.0), 0.0]
            for i in range(6)
        ],
        dtype=np.float64,
    )
    triangles = np.asarray(
        [[0, 1, 2], [0, 2, 3], [0, 3, 4], [0, 4, 5]],
        dtype=np.int64,
    )
    edges = np.asarray(
        [
            [100, 0, 1, 0],
            [101, 1, 2, 0],
            [102, 2, 3, 1],
            [103, 3, 4, 2],
            [104, 4, 5, 3],
            [105, 5, 0, 3],
        ],
        dtype=np.int64,
    )
    normals = np.tile(np.asarray([[0.0, 0.0, 1.0]], dtype=np.float64), (4, 1))
    certificate = {
        "source_kind": "authoritative-stl-ledger",
        "raw_sha256": "a" * 64,
        "brep_hash": "b" * 64,
        "authority": "source-ledger-v1",
        "provenance": "direct-source-ledger",
    }
    provenance = [
        {
            "source_edge": str(int(row[0])),
            "source_face": str(int(row[3])),
            "wall_edge": f"wall-{int(row[0])}",
            "output_face": f"out-{int(row[0])}",
            "feature": "feature",
            "patch": "p",
            "physical_group": "g",
            "component": "hexagon",
            "provenance": "direct",
        }
        for row in edges
    ]
    return points, triangles, edges, normals, certificate, provenance


def _dodecagon_with_interior_fixture():
    n = 12
    points = np.asarray(
        [[0.0, 0.0, 0.0]]
        + [
            [
                2.0 * math.cos(2.0 * math.pi * i / n),
                2.0 * math.sin(2.0 * math.pi * i / n),
                0.0,
            ]
            for i in range(n)
        ],
        dtype=np.float64,
    )
    triangles = np.asarray(
        [[0, i + 1, ((i + 1) % n) + 1] for i in range(n)],
        dtype=np.int64,
    )
    edges = np.asarray(
        [[100 + i, i + 1, ((i + 1) % n) + 1, i] for i in range(n)],
        dtype=np.int64,
    )
    normals = np.tile(np.asarray([[0.0, 0.0, 1.0]], dtype=np.float64), (n, 1))
    certificate = {
        "source_kind": "authoritative-stl-ledger",
        "raw_sha256": "a" * 64,
        "brep_hash": "b" * 64,
        "authority": "source-ledger-v1",
        "provenance": "direct-source-ledger",
    }
    provenance = [
        {
            "source_edge": str(int(row[0])),
            "source_face": str(int(row[3])),
            "wall_edge": f"wall-{int(row[0])}",
            "output_face": f"out-{int(row[0])}",
            "feature": "feature",
            "patch": "p",
            "physical_group": "g",
            "component": "dodecagon",
            "provenance": "direct",
        }
        for row in edges
    ]
    return points, triangles, edges, normals, certificate, provenance


def _target(
    points: np.ndarray,
    triangles: np.ndarray,
    edges: np.ndarray,
    normals: np.ndarray,
    certificate: dict[str, str],
    provenance: list[dict[str, str]],
    layers: int = 1,
    first_height: float = 0.6,
    clearance_cap: float = 1.0,
):
    return propose_surface_wall_edge_target_field(
        points,
        edges,
        normals,
        ["p"] * len(normals),
        ["feature"] * len(normals),
        ["g"] * len(normals),
        np.full(len(edges), clearance_cap, dtype=np.float64),
        layers,
        first_height,
        1.0,
        certificate,
        provenance,
        triangle_conditioned_aspect_limit=2.0,
        source_triangles=triangles,
        curved_strip_frame_mode=True,
    )


def test_planar_cavity_replacement_passes_strict_quality_and_source_coverage():
    points, triangles, edges, normals, certificate, provenance = _hexagon_fixture()
    target = _target(points, triangles, edges, normals, certificate, provenance)
    assert target["accepted"] is True, target
    transaction = transact_surface_wall_edge_target_field(
        points,
        triangles,
        edges,
        normals,
        target,
        certificate,
        provenance,
        1,
        planar_cavity_replacement=True,
    )
    assert transaction["accepted"] is True, transaction
    assert transaction["transaction_mode"] == "planar_cavity"
    assert transaction["source_triangles_unchanged"] is False
    assert transaction["source_faces_removed"] == [0, 1, 2, 3]
    assert transaction["source_faces_retained"] == []
    assert transaction["source_face_coverage_complete"] is True
    assert transaction["topology_invalid"] == 0
    assert transaction["topology_inverted"] == 0
    assert transaction["topology_duplicate"] == 0
    assert transaction["topology_non_manifold"] == 0
    assert transaction["quality"]["max_skewness"] <= 0.50 + 1.0e-12
    assert transaction["quality"]["max_triangle_aspect_ratio"] <= 10.0 + 1.0e-12
    assert transaction["quality"]["max_non_orthogonality_degrees"] <= 75.0 + 1.0e-12
    assert len(transaction["generated_faces"]) == 16
    assert len(transaction["provenance"]) == len(transaction["generated_faces"])
    for row in transaction["provenance"]:
        assert row["replacement_role"] in {"boundary_layer_strip", "child_front_core"}
        assert row["source_face_ids"]
        assert row["feature"] == "feature"
        assert row["patch"] == "p"
        assert row["physical_group"] == "g"
        assert row["component"] == "hexagon"
        assert row["provenance"] == "direct"
    core_rows = [row for row in transaction["provenance"] if row["replacement_role"] == "child_front_core"]
    assert core_rows
    assert all(row["source_face_ids"] == [0, 1, 2, 3] for row in core_rows)


def test_planar_cavity_replacement_is_repeatable_under_edge_reordering():
    points, triangles, edges, normals, certificate, provenance = _hexagon_fixture()
    first_target = _target(points, triangles, edges, normals, certificate, provenance)
    first = transact_surface_wall_edge_target_field(
        points, triangles, edges, normals, first_target, certificate, provenance, 1,
        planar_cavity_replacement=True,
    )
    permutation = np.asarray([5, 2, 0, 4, 1, 3], dtype=np.int64)
    reordered_edges = edges[permutation]
    reordered_provenance = [provenance[int(index)] for index in permutation]
    second_target = _target(
        points, triangles, reordered_edges, normals, certificate, reordered_provenance
    )
    second = transact_surface_wall_edge_target_field(
        points,
        triangles,
        reordered_edges,
        normals,
        second_target,
        certificate,
        reordered_provenance,
        1,
        planar_cavity_replacement=True,
    )
    assert first["accepted"] is True, first
    assert second["accepted"] is True, second
    assert first_target["frame_cycle_edge_ids"] == second_target["frame_cycle_edge_ids"]
    assert first["candidate_digest"] == second["candidate_digest"]
    assert first["output_digest"] == second["output_digest"]
    assert first["generated_faces"] == second["generated_faces"]


def test_planar_cavity_bl0_is_identity_without_cavity_writer():
    points, triangles, edges, normals, certificate, provenance = _hexagon_fixture()
    target = propose_surface_wall_edge_target_field(
        points,
        edges,
        normals,
        ["p"] * len(normals),
        ["feature"] * len(normals),
        ["g"] * len(normals),
        np.ones(len(edges), dtype=np.float64),
        0,
        0.6,
        1.0,
        certificate,
        provenance,
    )
    result = transact_surface_wall_edge_target_field(
        points,
        triangles,
        edges,
        normals,
        target,
        certificate,
        provenance,
        0,
        planar_cavity_replacement=True,
    )
    assert target["accepted"] is True
    assert result["accepted"] is True
    assert result["actual_layers"] == 0
    assert result["generated_faces"] == []
    assert result["receipt_consumed"] is False
    assert result["source_triangles_unchanged"] is True


def test_planar_cavity_refuses_source_triangle_digest_tamper_atomically():
    points, triangles, edges, normals, certificate, provenance = _hexagon_fixture()
    target = _target(points, triangles, edges, normals, certificate, provenance)
    tampered_triangles = triangles.copy()
    tampered_triangles[0, 2] = 3
    result = transact_surface_wall_edge_target_field(
        points,
        tampered_triangles,
        edges,
        normals,
        target,
        certificate,
        provenance,
        1,
        planar_cavity_replacement=True,
    )
    assert result["accepted"] is False
    assert result["reason"] == "target_frame_triangle_digest_mismatch"
    assert result["actual_layers"] == 0
    assert result["generated_faces"] == []
    assert result["candidate_discarded"] is True


def test_planar_cavity_refuses_non_planar_source_without_partial_output():
    points, triangles, edges, normals, certificate, provenance = _hexagon_fixture()
    target = _target(points, triangles, edges, normals, certificate, provenance)
    warped = points.copy()
    warped[3, 2] = 0.02
    result = transact_surface_wall_edge_target_field(
        warped,
        triangles,
        edges,
        normals,
        target,
        certificate,
        provenance,
        1,
        planar_cavity_replacement=True,
    )
    assert result["accepted"] is False
    assert result["reason"] in {
        "planar_cavity_source_not_planar_or_positive",
        "planar_cavity_child_front_not_inside",
        "planar_cavity_front_crosses_source",
    }
    assert result["actual_layers"] == 0
    assert result["generated_faces"] == []
    assert result["provenance"] == []



def test_planar_cavity_replacement_supports_three_actual_layers_and_repeats():
    points, triangles, edges, normals, certificate, provenance = _dodecagon_with_interior_fixture()
    target = _target(
        points, triangles, edges, normals, certificate, provenance,
        layers=3, first_height=0.1, clearance_cap=3.0,
    )
    first = transact_surface_wall_edge_target_field(
        points, triangles, edges, normals, target, certificate, provenance, 3,
        planar_cavity_replacement=True,
    )
    second = transact_surface_wall_edge_target_field(
        points, triangles, edges, normals, target, certificate, provenance, 3,
        planar_cavity_replacement=True,
    )
    assert target["accepted"] is True, target
    assert first["accepted"] is True, first
    assert first["actual_layers"] == 3
    assert first["source_triangles_unchanged"] is False
    assert first["source_face_coverage_complete"] is True
    assert first["topology_invalid"] == 0
    assert first["topology_inverted"] == 0
    assert first["topology_duplicate"] == 0
    assert first["topology_non_manifold"] == 0
    assert len(first["generated_vertices"]) == 36
    assert len(first["generated_faces"]) == 84
    assert len(first["provenance"]) == 84
    strip = [
        row for row in first["provenance"]
        if row["replacement_role"] == "boundary_layer_strip"
    ]
    assert len(strip) == 72
    assert {int(row["layer"]) for row in strip} == {1, 2, 3}
    core = [
        row for row in first["provenance"]
        if row["replacement_role"] == "child_front_core"
    ]
    assert len(core) == 12
    assert all(row["source_face_ids"] == list(range(12)) for row in core)
    assert first["quality"]["max_skewness"] <= 0.50 + 1.0e-12
    assert first["quality"]["max_triangle_aspect_ratio"] <= 10.0 + 1.0e-12
    assert first["quality"]["max_non_orthogonality_degrees"] <= 75.0 + 1.0e-12
    assert first["output_digest"] == second["output_digest"]
    assert first["generated_faces"] == second["generated_faces"]
