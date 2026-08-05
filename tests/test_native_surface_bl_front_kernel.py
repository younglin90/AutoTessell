"""L0 tests for the default-off C++ surface wall-edge front planner."""

from __future__ import annotations

import hashlib
import json

import numpy as np
import pytest

native_surface_bl_front = pytest.importorskip("native_surface_bl_front")


def _inputs() -> tuple[np.ndarray, np.ndarray, np.ndarray, list[str], list[str], list[str]]:
    points = np.array(
        [[0.0, 0.0, 0.0], [1.0, 0.0, 0.0], [0.0, 1.0, 0.0]], dtype=np.float64
    )
    edges = np.array([[17, 0, 1, 0]], dtype=np.int64)
    normals = np.array([[0.0, 0.0, 1.0]], dtype=np.float64)
    return points, edges, normals, ["wall"], ["smooth"], ["fluid"]


def _digest(value: object) -> str:
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()


def test_bl0_is_identity_and_bl1_plan_is_deterministic() -> None:
    points, edges, normals, patches, features, groups = _inputs()
    disabled = native_surface_bl_front.plan_surface_wall_edge_front(
        points, edges, normals, patches, features, groups, 0, 0.0, 1.0
    )
    assert disabled["accepted"] is True
    assert disabled["status"] == "disabled_identity"
    assert disabled["actual_layers"] == 0
    assert disabled["generated_vertices"] == []

    first = native_surface_bl_front.plan_surface_wall_edge_front(
        points, edges, normals, patches, features, groups, 1, 0.2, 1.2
    )
    second = native_surface_bl_front.plan_surface_wall_edge_front(
        points, edges, normals, patches, features, groups, 1, 0.2, 1.2
    )
    assert first["accepted"] is True
    assert first["actual_layers"] == first["requested_layers"] == 1
    assert len(first["generated_faces"]) == 2
    assert first["source_immutable"] is True
    assert first["provenance"][0]["source_wall_edge"] == 17
    assert _digest(first) == _digest(second)


def test_collision_rejects_without_partial_candidate() -> None:
    points, edges, normals, patches, features, groups = _inputs()
    points = np.vstack(
        [points, [[-0.1, 0.1, -0.1], [0.1, 0.1, -0.1], [0.0, 0.1, 0.1]]]
    )
    source_triangles = np.array([[0, 1, 2], [3, 4, 5]], dtype=np.int64)
    refused = native_surface_bl_front.plan_surface_wall_edge_front(
        points,
        edges,
        normals,
        patches,
        features,
        groups,
        1,
        0.2,
        1.0,
        source_triangles,
        0,
    )
    assert refused["accepted"] is False
    assert refused["status"] == "refused_rollback"
    assert refused["reason"] == "collision_or_visibility_failure"
    assert refused["generated_vertices"] == []
    assert refused["generated_faces"] == []
