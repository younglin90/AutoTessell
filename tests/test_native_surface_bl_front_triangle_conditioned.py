from __future__ import annotations

import hashlib
from pathlib import Path

import numpy as np

from core.evaluator.native_surface_bl_front_optimizer import (
    propose_surface_wall_edge_target_field,
)
from core.evaluator.native_surface_bl_front_target_field_transaction import (
    transact_surface_wall_edge_target_field,
)


def _authority(edges: np.ndarray):
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
            "component": "fixture",
            "provenance": "direct",
        }
        for row in edges
    ]
    return certificate, provenance


def _planar_fixture():
    points = np.asarray(
        [[0.0, 0.0, 0.0], [1.0, 0.0, 0.0], [2.0, 0.0, 0.0]],
        dtype=np.float64,
    )
    edges = np.asarray([[10, 0, 1, 0], [11, 1, 2, 0]], dtype=np.int64)
    normals = np.asarray([[0.0, 0.0, 1.0]], dtype=np.float64)
    return points, edges, normals


def test_triangle_conditioned_receipt_uses_shared_predecessor_length_interval():
    points, edges, normals = _planar_fixture()
    certificate, provenance = _authority(edges)
    result = propose_surface_wall_edge_target_field(
        points,
        edges,
        normals,
        ["wall"],
        ["feature"],
        ["fluid-wall"],
        np.asarray([1.0, 1.0]),
        1,
        0.01,
        1.0,
        certificate,
        provenance,
        max_metric_aspect=10.0,
        triangle_conditioned_aspect_limit=1.5,
    )
    assert result["accepted"] is True, result
    assert result["triangle_conditioned"] is True
    assert result["receipt_version"] == "target_field_receipt_v2_triangle_conditioned"
    assert result["quality"]["metric_aspect_limit"] == 1.5
    assert result["quality"]["max_metric_aspect"] <= 1.5 + 1.0e-12
    assert result["target_edges"][0]["accepted_height"] >= 2.0 / 3.0


def test_triangle_conditioned_clearance_refuses_extra_layers_atomically():
    points, edges, normals = _planar_fixture()
    certificate, provenance = _authority(edges)
    result = propose_surface_wall_edge_target_field(
        points,
        edges,
        normals,
        ["wall"],
        ["feature"],
        ["fluid-wall"],
        np.asarray([1.0, 1.0]),
        3,
        0.01,
        1.0,
        certificate,
        provenance,
        triangle_conditioned_aspect_limit=1.5,
    )
    assert result["accepted"] is False
    assert result["reason"] in {
        "aspect_or_clearance_infeasible",
        "shared_vertex_target_infeasible",
        "clearance_budget_exhausted",
    }
    assert result["actual_layers"] == 0
    assert result["target_vertices"] == []
    assert result["target_edges"] == []


def test_hemisphere_conditioning_reduces_target_metric_but_final_writer_stays_authoritative():
    from core.layers.native_tet_surface_edge_ledger import build_stl_edge_ledger
    from tests.test_native_surface_bl_front_actual_stl import _surface

    path = Path("tests/benchmarks/hemisphere_open.stl")
    points, triangles, normals, vertex_ids = _surface(path)
    ledger = build_stl_edge_ledger(path)
    selected = [edge for edge in ledger["edges"] if edge["incidence"] == 1]
    edges = np.asarray(
        [
            [
                int(edge["edge_id"][:15], 16),
                vertex_ids[tuple(edge["endpoint_a"])],
                vertex_ids[tuple(edge["endpoint_b"])],
                edge["incident_facets"][0],
            ]
            for edge in selected
        ],
        dtype=np.int64,
    )
    source_sha = hashlib.sha256(open(path, "rb").read()).hexdigest()
    certificate = {
        "source_kind": "authoritative-stl-ledger",
        "raw_sha256": source_sha,
        "brep_hash": hashlib.sha256(("authoritative-stl-ledger" + source_sha).encode()).hexdigest(),
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
            "component": "hemisphere",
            "provenance": "direct",
        }
        for row in edges
    ]
    target = propose_surface_wall_edge_target_field(
        points,
        edges,
        normals,
        ["wall"] * len(normals),
        ["feature"] * len(normals),
        ["fluid-wall"] * len(normals),
        np.full(len(edges), 1.0),
        1,
        0.01,
        1.2,
        certificate,
        provenance,
        triangle_conditioned_aspect_limit=1.5,
    )
    assert target["accepted"] is True, target
    assert target["quality"]["max_metric_aspect"] <= 1.5 + 1.0e-12
    transaction = transact_surface_wall_edge_target_field(
        points,
        triangles,
        edges,
        normals,
        target,
        certificate,
        provenance,
        1,
    )
    assert transaction["accepted"] is False
    assert transaction["reason"] == "strip_diagonal_no_quality_admissible"
    assert transaction["actual_layers"] == 0
    assert transaction["generated_faces"] == []
    assert transaction["candidate_discarded"] is True
