from __future__ import annotations

import math
from collections import defaultdict

import numpy as np

import core.evaluator.native_surface_bl_front_target_field_transaction as transaction_module
from core.evaluator.native_surface_bl_front_optimizer import (
    propose_surface_wall_edge_target_field,
)
from core.evaluator.native_surface_bl_front_target_field_transaction import (
    transact_surface_wall_edge_target_field,
)


def _square_with_center_fixture():
    points = np.asarray(
        [
            [-1.0, -1.0, 0.0],
            [1.0, -1.0, 0.0],
            [1.0, 1.0, 0.0],
            [-1.0, 1.0, 0.0],
            [0.0, 0.0, 0.0],
        ],
        dtype=np.float64,
    )
    triangles = np.asarray(
        [[4, 0, 1], [4, 1, 2], [4, 2, 3], [4, 3, 0]],
        dtype=np.int64,
    )
    edges = np.asarray(
        [[100, 0, 1, 0], [101, 1, 2, 1], [102, 2, 3, 2], [103, 3, 0, 3]],
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
            "patch": "wall",
            "physical_group": "fluid-wall",
            "component": "square",
            "provenance": "direct",
        }
        for row in edges
    ]
    return points, triangles, edges, normals, certificate, provenance


def test_strict_uniform_midpoint_subdivision_has_actual_quality_and_lineage_receipt():
    points, triangles, edges, normals, certificate, provenance = _square_with_center_fixture()
    target = propose_surface_wall_edge_target_field(
        points,
        edges,
        normals,
        ["wall"] * len(edges),
        ["feature"] * len(edges),
        ["fluid-wall"] * len(edges),
        np.full(len(edges), 3.0, dtype=np.float64),
        1,
        math.sqrt(0.5),
        1.0,
        certificate,
        provenance,
        triangle_conditioned_aspect_limit=0.0,
        source_triangles=triangles,
        curved_strip_frame_mode=True,
        strict_quality=True,
    )
    assert target["accepted"] is True, target
    assert target["strict_quality"] is True

    runs = [
        transact_surface_wall_edge_target_field(
            points,
            triangles,
            edges,
            normals,
            target,
            certificate,
            provenance,
            1,
            planar_cavity_replacement=True,
            strict_quality=True,
        )
        for _ in range(3)
    ]
    first = runs[0]
    assert all(run["accepted"] is True for run in runs), runs
    assert all(run["output_digest"] == first["output_digest"] for run in runs)
    assert first["actual_layers"] == 1
    assert first["subdivision_factor"] == 2
    assert first["phase_offset"] in {-0.5, -1.0 / 3.0, 0.0, 1.0 / 3.0, 0.5}
    assert len(first["generated_vertices"]) == 12
    assert len(first["generated_faces"]) == 24
    assert len(first["generated_vertex_lineage"]) == 8
    assert len(first["interval_ledger"]) == 16
    assert first["source_face_coverage_complete"] is True
    assert first["source_triangles_unchanged"] is False
    assert first["topology_invalid"] == 0
    assert first["topology_inverted"] == 0
    assert first["topology_duplicate"] == 0
    assert first["topology_non_manifold"] == 0

    quality = first["quality"]
    assert quality["max_skewness"] <= 0.30 + 1.0e-12
    assert quality["max_triangle_aspect_ratio"] <= 1.428571428571429 + 1.0e-12
    assert quality["max_non_orthogonality_degrees"] <= 30.0 + 1.0e-12
    audit = quality["independent_long_double_audit"]
    assert audit["accepted"] is True
    assert audit["metric_kernel"] == "independent_long_double_no_strip_triangle_quality"
    assert audit["invalid"] == 0
    assert audit["inverted"] == 0
    assert audit["duplicate"] == 0
    assert audit["non_manifold"] == 0
    assert audit["max_skewness"] <= 0.30 + 1.0e-12
    assert audit["max_aspect_ratio"] <= 10.0 / 7.0 + 1.0e-12
    assert audit["max_non_orthogonality_degrees"] <= 30.0 + 1.0e-12
    assert len(first["quality_witness"]) == 24
    assert all(row["accepted"] is True for row in first["quality_witness"])

    lineage_ids = set()
    for row in first["generated_vertex_lineage"]:
        lineage_ids.add(row["id"])
        assert row["source_edge_id"] in {100, 101, 102, 103}
        assert row["source_face_id"] in {0, 1, 2, 3}
        assert row["layer"] in {0, 1}
        assert row["parameter"] == 0.5
        assert row["lineage_role"] == "subdivided_front_vertex"
        assert len(row["parent_vertex_ids"]) == 2
        assert row["target_receipt_digest"]
    assert len(lineage_ids) == 8

    groups = defaultdict(list)
    for row in first["interval_ledger"]:
        groups[(row["source_edge_id"], row["layer"])].append(row)
        assert row["subdivision_factor"] == 2
        assert row["source_wall_edge"] == str(row["source_edge_id"])
    assert set(groups) == {
        (edge_id, layer)
        for edge_id in (100, 101, 102, 103)
        for layer in (0, 1)
    }
    for rows in groups.values():
        rows.sort(key=lambda row: row["interval_index"])
        assert [(row["t0"], row["t1"]) for row in rows] == [
            (0.0, 0.5),
            (0.5, 1.0),
        ]


def test_strict_transaction_refuses_rational_interval_tamper(monkeypatch):
    points, triangles, edges, normals, certificate, provenance = _square_with_center_fixture()
    target = propose_surface_wall_edge_target_field(
        points,
        edges,
        normals,
        ["wall"] * len(edges),
        ["feature"] * len(edges),
        ["fluid-wall"] * len(edges),
        np.full(len(edges), 3.0, dtype=np.float64),
        1,
        math.sqrt(0.5),
        1.0,
        certificate,
        provenance,
        triangle_conditioned_aspect_limit=0.0,
        source_triangles=triangles,
        curved_strip_frame_mode=True,
        strict_quality=True,
    )
    original = transaction_module.write_authoritative_surface_wall_edge_planar_cavity

    def tampered_writer(*args, **kwargs):
        result = dict(original(*args, **kwargs))
        intervals = [dict(row) for row in result["interval_ledger"]]
        intervals[0]["t0_numerator"] = 1
        result["interval_ledger"] = intervals
        return result

    monkeypatch.setattr(
        transaction_module,
        "write_authoritative_surface_wall_edge_planar_cavity",
        tampered_writer,
    )
    result = transaction_module.transact_surface_wall_edge_target_field(
        points,
        triangles,
        edges,
        normals,
        target,
        certificate,
        provenance,
        1,
        planar_cavity_replacement=True,
        strict_quality=True,
    )
    assert result["accepted"] is False, result
    assert result["reason"] == "writer_interval_ledger_invalid"
    assert result["generated_faces"] == []
    assert result["candidate_discarded"] is True


def _regular_hex_with_center_fixture():
    n = 6
    points = np.asarray(
        [[0.0, 0.0, 0.0]]
        + [
            [2.0 * math.cos(2.0 * math.pi * i / n),
             2.0 * math.sin(2.0 * math.pi * i / n), 0.0]
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
        "source_sha256": "c" * 64,
        "boundary_mapping_sha256": "d" * 64,
        "physical_group_sha256": "e" * 64,
    }
    provenance = [
        {
            "source_edge": str(int(row[0])),
            "source_face": str(int(row[3])),
            "wall_edge": f"wall-{int(row[0])}",
            "output_face": f"out-{int(row[0])}",
            "feature": "feature",
            "patch": "wall",
            "physical_group": "fluid-wall",
            "component": "regular-hex",
            "provenance": "direct",
        }
        for row in edges
    ]
    return points, triangles, edges, normals, certificate, provenance


def test_regular_hex_strict_actual_1to2_zipper_has_equilateral_audit():
    points, triangles, edges, normals, certificate, provenance = (
        _regular_hex_with_center_fixture()
    )
    target = propose_surface_wall_edge_target_field(
        points,
        edges,
        normals,
        ["wall"] * len(edges),
        ["feature"] * len(edges),
        ["fluid-wall"] * len(edges),
        np.full(len(edges), 3.0, dtype=np.float64),
        1,
        1.0,
        1.0,
        certificate,
        provenance,
        triangle_conditioned_aspect_limit=0.0,
        source_triangles=triangles,
        curved_strip_frame_mode=True,
        strict_quality=True,
    )
    assert target["accepted"] is True, target
    runs = [
        transaction_module.transact_surface_wall_edge_target_field(
            points,
            triangles,
            edges,
            normals,
            target,
            certificate,
            provenance,
            1,
            planar_cavity_replacement=True,
            strict_quality=True,
        )
        for _ in range(3)
    ]
    first = runs[0]
    assert all(run["accepted"] is True for run in runs), runs
    assert len({run["output_digest"] for run in runs}) == 1
    assert first["actual_layers"] == 1
    assert first["subdivision_factor"] == 2
    assert len(first["generated_vertices"]) == 12
    assert len(first["generated_faces"]) == 24
    assert len(first["generated_vertex_lineage"]) == 6
    assert len(first["interval_ledger"]) == 12
    assert len(first["count_ledger"]) == 12
    assert first["source_face_coverage_complete"] is True
    assert first["source_triangles_unchanged"] is False
    assert first["topology_invalid"] == 0
    assert first["topology_inverted"] == 0
    assert first["topology_duplicate"] == 0
    assert first["topology_non_manifold"] == 0

    counts = {
        (row["source_edge_id"], row["layer"]): row["count"]
        for row in first["count_ledger"]
    }
    assert set(counts) == {
        (edge_id, layer)
        for edge_id in range(100, 106)
        for layer in (0, 1)
    }
    assert all(counts[(edge_id, 0)] == 2 for edge_id in range(100, 106))
    assert all(counts[(edge_id, 1)] == 1 for edge_id in range(100, 106))

    roles = [row["replacement_role"] for row in first["provenance"]]
    assert roles.count("boundary_layer_zipper") == 18
    assert roles.count("child_front_core") == 6
    audit = first["quality"]["independent_long_double_audit"]
    assert audit["accepted"] is True
    assert audit["metric_kernel"] == "independent_long_double_no_strip_triangle_quality"
    assert audit["max_skewness"] <= 1.0e-12
    assert audit["max_aspect_ratio"] <= 1.0 + 1.0e-12
    assert audit["max_non_orthogonality_degrees"] <= 1.0e-10
    assert audit["p95_skewness"] <= 0.10
    assert audit["p95_aspect_ratio"] <= 1.12
    assert audit["p95_non_orthogonality_degrees"] <= 10.0
    assert audit["p99_skewness"] <= 0.20
    assert audit["p99_aspect_ratio"] <= 1.25
    assert audit["p99_non_orthogonality_degrees"] <= 20.0
