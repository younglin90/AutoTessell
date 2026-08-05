"""Focused tests for the C++ shared-vertex quality-first surface front."""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np


BUILD = Path("/tmp/autotessell_surface_bl_front_shared_build")
if str(BUILD) not in sys.path:
    sys.path.insert(0, str(BUILD))

from native_surface_bl_front_shared import plan_shared_surface_wall_edge_front  # noqa: E402


def _inputs() -> tuple[np.ndarray, np.ndarray, np.ndarray, list[str], list[str], list[str]]:
    points = np.array([[0.0, 0.0, 0.0], [1.0, 0.0, 0.0], [1.0, 1.0, 0.0]], dtype=float)
    edges = np.array([[11, 0, 1, 0], [12, 1, 2, 0]], dtype=np.int64)
    normals = np.array([[0.0, 0.0, 1.0]], dtype=float)
    return points, edges, normals, ["wall"], ["unclassified_boundary"], ["fluid_wall"]


def test_bl0_is_disabled_identity_and_bl2_deduplicates_shared_vertices() -> None:
    points, edges, normals, patches, features, groups = _inputs()
    disabled = plan_shared_surface_wall_edge_front(points, edges, normals, patches, features, groups, 0, 0.0, 1.0)
    assert disabled["accepted"] is True
    assert disabled["status"] == "disabled_identity"
    assert disabled["generated_vertices"] == []

    first = plan_shared_surface_wall_edge_front(points, edges, normals, patches, features, groups, 2, 0.1, 1.2)
    second = plan_shared_surface_wall_edge_front(points, edges, normals, patches, features, groups, 2, 0.1, 1.2)
    assert first["accepted"] is True
    assert first["actual_layers"] == 2
    assert first["lineage_is_shared"] is True
    assert first["quality"]["shared_vertex_count"] == 3
    assert len(first["generated_vertices"]) == 6
    assert len(first["generated_faces"]) == 4
    assert 0.0 <= first["quality"]["max_skewness"] <= 0.50
    assert 0.0 <= first["quality"]["max_non_orthogonality"] <= 50.0
    assert first["quality"]["metric_aspect_ratio"] > 0.0 and first["quality"]["metric_distortion"] > 0.0
    assert len(first["provenance"]) == 4
    assert first == second


def test_duplicate_sector_and_collision_refuse_the_whole_transaction() -> None:
    points, edges, normals, patches, features, groups = _inputs()
    duplicate = np.vstack([edges, edges[0]])
    refused = plan_shared_surface_wall_edge_front(points, duplicate, normals, patches, features, groups, 1, 0.1, 1.0)
    assert refused["accepted"] is False
    assert refused["reason"] == "duplicate_source_edge_sector"
    assert refused["generated_vertices"] == []

    collision_points = np.vstack([points, [[0.0, 0.0, -0.1], [0.1, 0.0, 0.1], [-0.1, 0.0, 0.1]]])
    source_triangles = np.array([[3, 4, 5]], dtype=np.int64)
    refused = plan_shared_surface_wall_edge_front(
        collision_points, edges, normals, patches, features, groups, 1, 0.2, 1.0, source_triangles,
    )
    assert refused["accepted"] is False
    assert refused["reason"] == "collision_or_quality_failure"
    assert refused["actual_layers"] == 0
    assert refused["generated_faces"] == []


def test_twisted_front_quality_gate_refuses_without_halving_budget() -> None:
    points = np.array([[0.0, 0.0, 0.0], [1.0, 0.0, 0.0], [1.0, 1.0, 0.0]], dtype=float)
    edges = np.array([[11, 0, 1, 0], [12, 1, 2, 1]], dtype=np.int64)
    normals = np.array([[0.0, 0.0, 1.0], [1.0, 0.0, 0.0]], dtype=float)
    refused = plan_shared_surface_wall_edge_front(
        points, edges, normals, ["wall", "wall"], ["f", "f"], ["g", "g"], 1, 2.0, 1.0,
        max_step_halvings=0,
    )
    assert refused["accepted"] is False
    assert refused["reason"] == "collision_or_quality_failure"
    assert refused["generated_vertices"] == []
