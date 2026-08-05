"""L0 tests for the default-off sector/BVH surface BL planner."""

from __future__ import annotations

import hashlib
import json

import numpy as np
import pytest

native_sector = pytest.importorskip("native_surface_bl_front_sector")


def _case() -> tuple[np.ndarray, np.ndarray, np.ndarray, list[str], list[str], list[str], list[str], np.ndarray]:
    points = np.array(
        [
            [0.0, 0.0, 0.0], [1.0, 0.0, 0.0],
            [0.0, 1.0, 0.0], [0.0, -1.0, 0.0],
            [-0.1, 0.0, -0.1], [0.1, 0.0, -0.1], [0.0, 0.2, -0.1],
        ], dtype=np.float64,
    )
    edges = np.array([[17, 0, 1, 0, 0], [17, 0, 1, 1, 1]], dtype=np.int64)
    normals = np.array([[0.0, 0.0, 1.0], [0.0, 1.0, 0.0]], dtype=np.float64)
    triangles = np.array([[0, 1, 2], [0, 1, 3], [4, 5, 6]], dtype=np.int64)
    return points, edges, normals, ["wall", "ridge"], ["smooth", "feature"], ["fluid", "fluid"], ["left", "right"], triangles


def _digest(value: object) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def test_bl0_identity_and_two_ridge_sectors_are_deterministic() -> None:
    points, edges, normals, patches, features, groups, sides, triangles = _case()
    disabled = native_sector.plan_surface_wall_edge_sectors(
        points, edges, normals, patches, features, groups, sides, 0, 0.0, 1.0
    )
    assert disabled["accepted"] is True
    assert disabled["status"] == "disabled_identity"
    assert disabled["generated_vertices"] == []

    # Use only the two incident triangles for the accepted ridge sectors.
    accepted_triangles = triangles[:2]
    first = native_sector.plan_surface_wall_edge_sectors(
        points, edges, normals, patches, features, groups, sides, 1, 0.2, 1.1, accepted_triangles
    )
    second = native_sector.plan_surface_wall_edge_sectors(
        points, edges, normals, patches, features, groups, sides, 1, 0.2, 1.1, accepted_triangles
    )
    assert first["accepted"] is True
    assert first["actual_layers"] == 1
    assert len(first["provenance"]) == 2
    assert first["provenance"][0]["side"] != first["provenance"][1]["side"]
    assert first["provenance"][0]["co_normal"] != first["provenance"][1]["co_normal"]
    assert _digest(first) == _digest(second)


def test_missing_visibility_and_witness_collision_refuse_whole_plan() -> None:
    points, edges, normals, patches, features, groups, sides, triangles = _case()
    missing = native_sector.plan_surface_wall_edge_sectors(
        points, edges, normals, patches, features, groups, sides, 1, 0.2, 1.0
    )
    assert missing["accepted"] is False
    assert missing["reason"] == "missing_conservative_visibility_inputs"
    assert missing["generated_vertices"] == []

    collision = native_sector.plan_surface_wall_edge_sectors(
        points, edges, normals, patches, features, groups, sides, 1, 0.2, 1.0, triangles
    )
    assert collision["accepted"] is False
    assert collision["status"] == "refused_rollback"
    assert collision["generated_vertices"] == []
    assert collision["generated_faces"] == []
