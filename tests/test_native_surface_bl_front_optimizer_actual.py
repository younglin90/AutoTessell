"""Actual open-hemisphere evidence for the private optimizer."""

from __future__ import annotations

from pathlib import Path

import numpy as np

from core.evaluator.native_surface_bl_front_optimizer import optimize_surface_wall_edge_front
from core.layers.native_tet_surface_edge_ledger import _parse_stl, build_stl_edge_ledger


def test_open_hemisphere_bl0_bl1_bl3_is_deterministic_or_atomic(monkeypatch):
    monkeypatch.setenv("AUTOTESSELL_EXT_BUILD_DIR", "/tmp/autotessell_surface_bl_front_shared_build")
    path = Path("tests/benchmarks/hemisphere_open.stl")
    triangles_raw = _parse_stl(path)
    vertices: dict[tuple[float, float, float], int] = {}
    points: list[tuple[float, float, float]] = []
    normals: list[tuple[float, float, float]] = []
    for triangle in triangles_raw:
        ids = []
        for value in triangle:
            if value not in vertices:
                vertices[value] = len(points)
                points.append(value)
            ids.append(vertices[value])
        a, b, c = (np.asarray(points[i], dtype=float) for i in ids)
        n = np.cross(b - a, c - a)
        normals.append(tuple((n / np.linalg.norm(n)).tolist()))
    ledger = build_stl_edge_ledger(path)
    selected = [edge for edge in ledger["edges"] if edge["incidence"] == 1]
    edges = np.asarray(
        [[int(edge["edge_id"][:15], 16), vertices[tuple(edge["endpoint_a"])], vertices[tuple(edge["endpoint_b"])], edge["incident_facets"][0]] for edge in selected],
        dtype=np.int64,
    ).reshape((-1, 4))
    certificate = {"source_kind": "stl", "raw_sha256": "hemisphere-raw", "brep_hash": "hemisphere-brep", "authority": "ledger-v1", "provenance": "direct"}
    rows = [{"source_edge": str(int(row[0])), "source_face": str(int(row[3])), "wall_edge": str(int(row[0])), "output_face": str(int(row[0])), "feature": "open-edge", "patch": "wall", "physical_group": "fluid-wall", "component": "hemisphere", "provenance": "direct"} for row in edges]
    kwargs = dict(points=np.asarray(points), edges=edges, face_normals=np.asarray(normals), patch_names=["wall"] * len(normals), feature_names=["open-edge"] * len(normals), physical_groups=["fluid-wall"] * len(normals), first_height=0.001, growth_ratio=1.2, source_certificate=certificate, edge_provenance=rows)
    for layers in (0, 1, 3):
        first = optimize_surface_wall_edge_front(requested_layers=layers, **kwargs)
        second = optimize_surface_wall_edge_front(requested_layers=layers, **kwargs)
        assert first == second
        if layers == 0:
            assert first["accepted"] is True and first["status"] == "disabled_identity"
        elif first["accepted"]:
            assert first["actual_layers"] == layers
            assert first["quality"]["max_skewness"] <= 0.50
            assert first["quality"]["max_non_orthogonality"] <= 50.0
        else:
            assert first["actual_layers"] == 0
            assert first["generated_vertices"] == []
            assert first["generated_faces"] == []
