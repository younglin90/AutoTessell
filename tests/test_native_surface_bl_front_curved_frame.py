from __future__ import annotations

import numpy as np

from core.evaluator.native_surface_bl_front_optimizer import (
    propose_surface_wall_edge_target_field,
)
from core.evaluator.native_surface_bl_front_target_field_transaction import (
    transact_surface_wall_edge_target_field,
)


def _square_fixture():
    points = np.asarray(
        [[0.0, 0.0, 0.0], [1.0, 0.0, 0.0], [1.0, 1.0, 0.0], [0.0, 1.0, 0.0]],
        dtype=np.float64,
    )
    triangles = np.asarray([[0, 1, 2], [0, 2, 3]], dtype=np.int64)
    edges = np.asarray(
        [[100, 0, 1, 0], [101, 1, 2, 0], [102, 2, 3, 1], [103, 0, 3, 1]],
        dtype=np.int64,
    )
    normals = np.asarray([[0.0, 0.0, 1.0], [0.0, 0.0, 1.0]], dtype=np.float64)
    authority = {
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
    return points, triangles, edges, normals, authority, provenance


def test_curved_frame_receipt_is_deterministic_and_binds_source_triangles():
    points, triangles, edges, normals, authority, provenance = _square_fixture()
    kwargs = dict(
        points=points,
        edges=edges,
        face_normals=normals,
        patch_names=["wall", "wall"],
        feature_names=["feature", "feature"],
        physical_groups=["fluid", "fluid"],
        clearance_caps=np.ones(4),
        requested_layers=1,
        first_height=0.6,
        growth_ratio=1.0,
        source_certificate=authority,
        edge_provenance=provenance,
        triangle_conditioned_aspect_limit=2.0,
        source_triangles=triangles,
        curved_strip_frame_mode=True,
    )
    first = propose_surface_wall_edge_target_field(**kwargs)
    second = propose_surface_wall_edge_target_field(**kwargs)
    assert first["accepted"] is True, first
    assert second == first
    assert first["receipt_version"] == "target_field_receipt_v3_directed_frame"
    assert first["source_triangle_count"] == 2
    assert first["frame_cycle_edge_ids"] == [100, 101, 102, 103]
    assert first["frame_closure_residual"] <= 1.0e-12
    assert first["frame_min_side_dot"] > 0.99
    assert first["quality"]["max_endpoint_height_skew"] == 0.0
    assert first["quality"]["max_metric_aspect"] <= 2.0 + 1.0e-12
    assert all(row["direction_mode"] == "directed_parallel_transport_frame" for row in first["target_edges"])


def test_curved_frame_transaction_refuses_existing_writer_topology_atomically():
    points, triangles, edges, normals, authority, provenance = _square_fixture()
    target = propose_surface_wall_edge_target_field(
        points,
        edges,
        normals,
        ["wall", "wall"],
        ["feature", "feature"],
        ["fluid", "fluid"],
        np.ones(4),
        1,
        0.6,
        1.0,
        authority,
        provenance,
        triangle_conditioned_aspect_limit=2.0,
        source_triangles=triangles,
        curved_strip_frame_mode=True,
    )
    assert target["accepted"] is True, target
    transaction = transact_surface_wall_edge_target_field(
        points, triangles, edges, normals, target, authority, provenance, 1
    )
    assert transaction["accepted"] is False
    assert transaction["reason"] == "final_surface_topology_failed"
    assert transaction["actual_layers"] == 0
    assert transaction["generated_faces"] == []
    assert transaction["candidate_discarded"] is True
    assert transaction["source_triangles_unchanged"] is True


def test_curved_frame_hemisphere_refuses_with_measured_quality_witness():
    from pathlib import Path

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
    import hashlib

    source_sha = hashlib.sha256(path.read_bytes()).hexdigest()
    authority = {
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
    result = propose_surface_wall_edge_target_field(
        points,
        edges,
        normals,
        ["wall"] * len(normals),
        ["feature"] * len(normals),
        ["fluid-wall"] * len(normals),
        np.ones(len(edges)),
        1,
        0.01,
        1.2,
        authority,
        provenance,
        triangle_conditioned_aspect_limit=1.5,
        source_triangles=triangles,
        curved_strip_frame_mode=True,
    )
    assert result["accepted"] is False
    assert result["reason"] == "curved_frame_preflight_quality_failure"
    assert result["actual_layers"] == 0
    assert result["target_vertices"] == []
    assert result["target_edges"] == []
    witness = result["preflight_quality"]
    assert witness["chosen_skewness"] > 0.50
    assert witness["chosen_aspect_ratio"] < 10.0
    assert witness["chosen_non_orthogonality"] < 75.0
    assert witness["choice0_signed_area"] > 0.0
    assert witness["choice1_signed_area"] > 0.0
