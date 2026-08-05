"""Tests for the default-off C++23 sector-owned BL target-field receipt."""

from __future__ import annotations

import numpy as np

from core.evaluator.native_surface_bl_front_optimizer import (
    propose_surface_wall_edge_target_field,
)


def _authority(edges: np.ndarray):
    return {
        "source_kind": "authoritative-stl-ledger",
        "raw_sha256": "a" * 64,
        "brep_hash": "b" * 64,
        "authority": "source-ledger-v1",
        "provenance": "direct-source-ledger",
    }, [
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


def _collinear_fixture():
    points = np.asarray(
        [[0.0, 0.0, 0.0], [1.0, 0.0, 0.0], [2.0, 0.0, 0.0]],
        dtype=np.float64,
    )
    edges = np.asarray([[10, 0, 1, 0], [11, 1, 2, 0]], dtype=np.int64)
    normals = np.asarray([[0.0, 0.0, 1.0]], dtype=np.float64)
    return points, edges, normals


def test_bl0_is_authority_checked_identity_without_clearance():
    points, edges, normals = _collinear_fixture()
    cert, provenance = _authority(edges)
    result = propose_surface_wall_edge_target_field(
        points, edges, normals, ["wall"], ["feature"], ["fluid-wall"],
        None, 0, 0.0, 1.0, cert, provenance,
    )
    assert result["accepted"] is True
    assert result["status"] == "disabled_identity"
    assert result["target_field"] is False
    assert result["generated_vertices"] == []
    assert result["generated_faces"] == []
    assert result["target_vertices"] == []
    assert result["target_edges"] == []
    assert result["source_authority_bound"] is True


def test_positive_receipt_is_deterministic_and_metric_bounded():
    points, edges, normals = _collinear_fixture()
    cert, provenance = _authority(edges)
    kwargs = dict(
        points=points, edges=edges, face_normals=normals,
        patch_names=["wall"], feature_names=["feature"],
        physical_groups=["fluid-wall"],
        clearance_caps=np.asarray([1.0, 1.0], dtype=np.float64),
        requested_layers=2, first_height=0.1, growth_ratio=1.2,
        source_certificate=cert, edge_provenance=provenance,
        max_metric_aspect=10.0,
    )
    first = propose_surface_wall_edge_target_field(**kwargs)
    second = propose_surface_wall_edge_target_field(**kwargs)
    assert first == second
    assert first["accepted"] is True, first
    assert first["actual_layers"] == 2
    assert first["runtime_route"] == "default_off"
    assert first["publication_eligible"] is False
    assert len(first["target_edges"]) == 4
    assert len(first["target_vertices"]) == 6
    assert first["quality"]["max_metric_aspect"] <= 10.0 + 1.0e-12
    assert first["quality"]["max_endpoint_height_skew"] <= 0.50 + 1.0e-12
    for row in first["target_edges"]:
        assert row["accepted_height"] > 0.0
        assert row["metric_aspect"] <= 10.0 + 1.0e-12
        assert row["predecessor_layer"] == row["layer"] - 1
        assert row["shared_front"] is True


def test_missing_clearance_refuses_positive_boundary_layer():
    points, edges, normals = _collinear_fixture()
    cert, provenance = _authority(edges)
    result = propose_surface_wall_edge_target_field(
        points, edges, normals, ["wall"], ["feature"], ["fluid-wall"],
        None, 1, 0.1, 1.2, cert, provenance,
    )
    assert result["accepted"] is False
    assert result["reason"] in {"clearance_uncertified", "invalid_target_field_options"}
    assert result["target_vertices"] == []
    assert result["target_edges"] == []


def test_first_height_is_projected_to_aspect_safe_height():
    points, edges, normals = _collinear_fixture()
    cert, provenance = _authority(edges)
    result = propose_surface_wall_edge_target_field(
        points, edges, normals, ["wall"], ["feature"], ["fluid-wall"],
        np.asarray([1.0, 1.0]), 1, 0.01, 1.0, cert, provenance,
        max_metric_aspect=10.0,
    )
    assert result["accepted"] is True, result
    assert result["reason"] == "sector_owned_adaptive_target_field_passed"
    assert result["actual_layers"] == 1
    assert result["generated_vertices"] == []
    assert len(result["target_edges"]) == 2
    assert result["target_edges"][0]["requested_height"] == 0.01
    assert result["target_edges"][0]["accepted_height"] >= 0.1
    assert result["quality"]["max_metric_aspect"] <= 10.0 + 1.0e-12


def test_ridge_sector_direction_conflict_refuses_without_averaging():
    points = np.asarray(
        [[0.0, 0.0, 0.0], [1.0, 0.0, 0.0], [0.0, 1.0, 0.0]],
        dtype=np.float64,
    )
    edges = np.asarray([[20, 0, 1, 0], [21, 0, 2, 0]], dtype=np.int64)
    normals = np.asarray([[0.0, 0.0, 1.0]], dtype=np.float64)
    cert, provenance = _authority(edges)
    result = propose_surface_wall_edge_target_field(
        points, edges, normals, ["wall"], ["feature"], ["fluid-wall"],
        np.asarray([1.0, 1.0]), 1, 0.1, 1.0, cert, provenance,
    )
    assert result["accepted"] is False
    assert result["reason"] == "sector_direction_conflict"
    assert result["target_edges"] == []
