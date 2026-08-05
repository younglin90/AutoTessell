from __future__ import annotations

from collections import defaultdict
from pathlib import Path

import numpy as np

from core.layers.native_tet_surface_edge_ledger import build_stl_edge_ledger
from tests.test_native_surface_bl_front_actual_stl import _surface
from core.utils.native_extensions import import_native_extension


plan_front = import_native_extension("native_surface_bl_front_shared").plan_shared_surface_wall_edge_front


def _hemisphere_boundary_loop() -> tuple[np.ndarray, np.ndarray, np.ndarray, list[int]]:
    path = Path("tests/benchmarks/hemisphere_open.stl")
    points, triangles, normals, vertex_ids = _surface(path)
    ledger = build_stl_edge_ledger(path)
    selected = [edge for edge in ledger["edges"] if edge["incidence"] == 1]
    edges = np.asarray(
        [
            [int(edge["edge_id"][:15], 16), vertex_ids[tuple(edge["endpoint_a"])], vertex_ids[tuple(edge["endpoint_b"])], edge["incident_facets"][0]]
            for edge in selected
        ],
        dtype=np.int64,
    )
    adjacency: dict[int, list[int]] = defaultdict(list)
    for edge in selected:
        a = vertex_ids[tuple(edge["endpoint_a"])]
        b = vertex_ids[tuple(edge["endpoint_b"])]
        adjacency[a].append(b)
        adjacency[b].append(a)
    start = min(adjacency)
    loop = [start]
    previous = -1
    current = start
    while True:
        choices = [value for value in adjacency[current] if value != previous]
        next_vertex = choices[0]
        if next_vertex == start:
            break
        loop.append(next_vertex)
        previous, current = current, next_vertex
        if len(loop) > len(adjacency) + 1:
            raise AssertionError("boundary loop ordering failed")
    return points, triangles, normals, edges, loop


def test_hemisphere_directed_loop_tangent_frame_is_deterministic() -> None:
    points, triangles, normals, edges, loop = _hemisphere_boundary_loop()
    kwargs = dict(
        points=points,
        edges=edges,
        face_normals=normals,
        patch_names=["wall"] * len(normals),
        feature_names=["smooth-rim"] * len(normals),
        physical_groups=["fluid-wall"] * len(normals),
        requested_layers=1,
        first_height=1.0e-4,
        growth_ratio=1.0,
        source_triangles=triangles,
        max_step_halvings=8,
        minimum_allowed_step=1.0e-8,
        directed_loops=[list(reversed(loop))],
    )
    first = plan_front(**kwargs)
    second = plan_front(**kwargs)
    assert first == second
    assert first["accepted"] is False
    assert first["actual_layers"] == 0
    assert first["reason"] == "directed_wall_loop_winding_mismatch"


def test_directed_loop_tangent_frame_accepts_smooth_planar_rim() -> None:
    points = np.asarray([[0.0, 0.0, 0.0], [1.0, 0.0, 0.0], [1.0, 1.0, 0.0], [0.0, 1.0, 0.0]], dtype=float)
    edges = np.asarray([[100, 0, 1, 0], [101, 1, 2, 0], [102, 2, 3, 0], [103, 3, 0, 0]], dtype=np.int64)
    normals = np.asarray([[0.0, 0.0, 1.0]], dtype=float)
    result = plan_front(
        points, edges, normals, ["wall"], ["smooth-rim"], ["fluid-wall"],
        1, 0.01, 1.0, directed_loops=[[0, 1, 2, 3]],
    )
    assert result["accepted"] is True, result
    assert result["quality"]["direction_mode"] == "directed_loop_tangent_frame"
    assert result["quality"]["directed_wall_loop_count"] == 1
    assert result["quality"]["min_signed_area"] > 0.0


def test_hemisphere_directed_loop_coverage_is_fail_closed() -> None:
    points, triangles, normals, edges, loop = _hemisphere_boundary_loop()
    result = plan_front(
        points,
        edges,
        normals,
        ["wall"] * len(normals),
        ["smooth-rim"] * len(normals),
        ["fluid-wall"] * len(normals),
        1,
        1.0e-4,
        1.0,
        triangles,
        directed_loops=[loop[:-1]],
    )
    assert result["accepted"] is False
    assert result["actual_layers"] == 0
    assert result["reason"] == "directed_wall_loop_edge_binding_mismatch"


def test_hemisphere_authoritative_winding_and_replaceable_cavity_accepts_layer() -> None:
    points, triangles, normals, edges, loop = _hemisphere_boundary_loop()
    cavity_faces = sorted({int(row[3]) for row in edges})
    result = plan_front(
        points=points,
        edges=edges,
        face_normals=normals,
        patch_names=["wall"] * len(normals),
        feature_names=["smooth-rim"] * len(normals),
        physical_groups=["fluid-wall"] * len(normals),
        requested_layers=1,
        first_height=1.0e-4,
        growth_ratio=1.0,
        source_triangles=triangles,
        directed_loops=[loop],
        cavity_faces=cavity_faces,
    )
    assert result["accepted"] is True, result.get("last_failure_reason")
    assert result["replaceable_cavity_verified"] is True
    assert result["quality"]["cavity_mode"] == "replaceable_source_faces"
    assert result["quality"]["cavity_source_face_count"] == len(cavity_faces)
