"""L0-L1 evidence for complete common-scale stack transactions."""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path("/tmp/autotessell_surface_bl_front_shared_build")))
from native_surface_bl_front_shared import plan_shared_surface_wall_edge_front  # noqa: E402


def _plan(points, edges, normals, patches, features, groups, *, layers, first_height, growth_ratio, triangles=None, max_step_halvings=4):
    return plan_shared_surface_wall_edge_front(
        np.asarray(points, dtype=float),
        np.asarray(edges, dtype=np.int64),
        np.asarray(normals, dtype=float),
        list(patches),
        list(features),
        list(groups),
        layers,
        first_height,
        growth_ratio,
        None if triangles is None else np.asarray(triangles, dtype=np.int64),
        max_step_halvings=max_step_halvings,
        minimum_allowed_step=1.0e-8,
    )


def test_common_scale_preserves_growth_and_is_repeatable() -> None:
    points = [(0, 0, 0), (1, 0, 0), (0, 0.2, 0), (1, 0.2, 0)]
    edges = [[101, 0, 1, 0], [102, 2, 3, 0]]
    kwargs = dict(
        points=points,
        edges=edges,
        normals=[(0, 0, 1)],
        patches=["wall"],
        features=["smooth"],
        groups=["fluid_wall"],
        layers=3,
        first_height=0.01,
        growth_ratio=2.0,
    )
    first = _plan(**kwargs)
    second = _plan(**kwargs)
    assert first == second
    assert first["accepted"] is True
    assert first["quality"]["selected_scale"] == 1.0
    assert first["quality"]["valid_candidate_count"] == 5
    assert [item["used_step"] for item in first["provenance"] if item["source_wall_edge"] == 101] == [0.01, 0.02, 0.04]
    assert len(first["generated_vertices"]) == 12
    assert len(first["generated_faces"]) == 6
    assert len(first["provenance"]) == 6


def test_feature_like_shared_vertex_keeps_distinct_lineage() -> None:
    result = _plan(
        points=[(0, 0, 0), (1, 0, 0), (0, 1, 0)],
        edges=[[201, 0, 1, 0], [202, 0, 2, 1]],
        normals=[(0, 0, 1), (1, 0, 0)],
        patches=["wall_a", "wall_b"],
        features=["feature_a", "feature_b"],
        groups=["group_a", "group_b"],
        layers=2,
        first_height=0.01,
        growth_ratio=1.5,
    )
    assert result["accepted"] is True
    assert len(result["generated_vertices"]) == 6
    assert len(result["provenance"]) == 4
    assert {(item["source_wall_edge"], item["layer"]) for item in result["provenance"]} == {(201, 1), (201, 2), (202, 1), (202, 2)}
    assert {(item["patch"], item["feature"], item["physical_group"]) for item in result["provenance"]} == {
        ("wall_a", "feature_a", "group_a"),
        ("wall_b", "feature_b", "group_b"),
    }


def test_late_layer_collision_rolls_back_all_staged_layers() -> None:
    points = [
        (0, 0, 0),
        (1, 0, 0),
        (-0.1, 0.025, -0.1),
        (0.1, 0.025, -0.1),
        (0.0, 0.025, 0.1),
    ]
    result = _plan(
        points=points,
        edges=[[301, 0, 1, 0]],
        normals=[(0, 0, 1)],
        patches=["wall"],
        features=["late_collision"],
        groups=["fluid_wall"],
        layers=2,
        first_height=0.01,
        growth_ratio=2.0,
        triangles=[(2, 3, 4)],
        max_step_halvings=0,
    )
    assert result["accepted"] is False
    assert result["reason"] == "collision_or_quality_failure"
    assert result["actual_layers"] == 0
    assert result["generated_vertices"] == []
    assert result["generated_faces"] == []
    assert result["provenance"] == []
