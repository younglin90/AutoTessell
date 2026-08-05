"""Feed actual STL surfaces into the C++ shared-front candidate."""

from __future__ import annotations

from pathlib import Path

import numpy as np

from core.utils.native_extensions import import_native_extension

plan_shared_surface_wall_edge_front = import_native_extension(
    "native_surface_bl_front_shared"
).plan_shared_surface_wall_edge_front

from core.layers.native_tet_surface_edge_ledger import _parse_stl, build_stl_edge_ledger  # noqa: E402


def _surface(path: Path):
    triangles_raw = _parse_stl(path)
    vertices: dict[tuple[float, float, float], int] = {}
    points: list[tuple[float, float, float]] = []
    triangles: list[tuple[int, int, int]] = []
    normals: list[tuple[float, float, float]] = []
    for triangle in triangles_raw:
        ids = []
        for point in triangle:
            if point not in vertices:
                vertices[point] = len(points)
                points.append(point)
            ids.append(vertices[point])
        triangles.append(tuple(ids))
        a, b, c = (np.asarray(points[ids[index]], dtype=float) for index in range(3))
        normal = np.cross(b - a, c - a)
        normals.append(tuple((normal / np.linalg.norm(normal)).tolist()))
    return np.asarray(points, dtype=float), np.asarray(triangles, dtype=np.int64), np.asarray(normals, dtype=float), vertices


def _candidate(path: Path, layers: int):
    points, triangles, normals, vertex_ids = _surface(path)
    ledger = build_stl_edge_ledger(path)
    selected = [edge for edge in ledger["edges"] if edge["incidence"] == 1]
    edges = np.asarray(
        [[int(edge["edge_id"][:15], 16), vertex_ids[tuple(edge["endpoint_a"])], vertex_ids[tuple(edge["endpoint_b"])], edge["incident_facets"][0]] for edge in selected],
        dtype=np.int64,
    ).reshape((-1, 4))
    result = plan_shared_surface_wall_edge_front(
        points, edges, normals, ["wall"] * len(normals), ["unclassified_boundary"] * len(normals), ["fluid_wall"] * len(normals),
        layers, 0.01, 1.2, triangles, max_step_halvings=8, minimum_allowed_step=1.0e-6,
    )
    return ledger, result


def test_actual_stl_counts_and_bl0_identity() -> None:
    for name, expected in (("cube.stl", (12, 18, 0)), ("hemisphere_open.stl", (624, 960, 48))):
        path = Path("tests/benchmarks") / name
        ledger = build_stl_edge_ledger(path)
        assert (ledger["facet_count"], ledger["edge_count"], ledger["boundary_edge_count"]) == expected
        _, result = _candidate(path, 0)
        assert result["accepted"] is True and result["status"] == "disabled_identity"


def test_actual_open_hemisphere_bl1_bl3_is_deterministic_or_atomic_refusal() -> None:
    path = Path("tests/benchmarks/hemisphere_open.stl")
    for layers in (1, 3):
        first_ledger, first = _candidate(path, layers)
        second_ledger, second = _candidate(path, layers)
        assert first_ledger["edge_digest"] == second_ledger["edge_digest"]
        assert first == second
        if first["accepted"]:
            assert first["actual_layers"] == layers
            assert first["quality"]["max_skewness"] <= 0.50
            assert first["quality"]["max_non_orthogonality"] <= 50.0
            assert len(first["provenance"]) == 48 * layers
        else:
            assert first["actual_layers"] == 0
            assert first["generated_vertices"] == []
            assert first["generated_faces"] == []
