"""Verify the optional metric-aspect quality cap is atomic on actual STL input."""

from __future__ import annotations

from pathlib import Path

import numpy as np

from core.layers.native_tet_surface_edge_ledger import build_stl_edge_ledger
from tests.test_native_surface_bl_front_actual_stl import _surface


def _plan(path: Path, *, layers: int, max_metric_aspect_ratio: float):
    from native_surface_bl_front_shared import plan_shared_surface_wall_edge_front

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
    ).reshape((-1, 4))
    return plan_shared_surface_wall_edge_front(
        points,
        edges,
        normals,
        ["wall"] * len(normals),
        ["unclassified_boundary"] * len(normals),
        ["fluid_wall"] * len(normals),
        layers,
        0.01,
        1.2,
        triangles,
        max_step_halvings=8,
        minimum_allowed_step=1.0e-6,
        max_metric_aspect_ratio=max_metric_aspect_ratio,
    )


def test_actual_hemisphere_aspect_cap_refuses_whole_transaction() -> None:
    path = Path("tests/benchmarks/hemisphere_open.stl")
    uncapped = _plan(path, layers=1, max_metric_aspect_ratio=float("inf"))
    capped = _plan(path, layers=1, max_metric_aspect_ratio=10.0)

    assert uncapped["accepted"] is True
    assert uncapped["actual_layers"] == 1
    assert uncapped["quality"]["metric_aspect_ratio"] < 20.0
    assert capped["accepted"] is False
    assert capped["reason"] == "collision_or_quality_failure"
    assert capped["actual_layers"] == 0
    assert capped["generated_vertices"] == []
    assert capped["generated_faces"] == []
    assert capped["provenance"] == []


def test_bl0_ignores_aspect_cap_and_preserves_identity() -> None:
    result = _plan(Path("tests/benchmarks/hemisphere_open.stl"), layers=0, max_metric_aspect_ratio=1.0)
    assert result["accepted"] is True
    assert result["status"] == "disabled_identity"
    assert result["actual_layers"] == 0
