"""Minimum accepted step prevents collapsed line-search layers."""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path("/tmp/autotessell_surface_bl_front_shared_build")))
from native_surface_bl_front_shared import plan_shared_surface_wall_edge_front  # noqa: E402


def test_minimum_allowed_step_refuses_sub_threshold_candidate() -> None:
    points = np.array([[0.0, 0.0, 0.0], [1.0, 0.0, 0.0], [1.0, 1.0, 0.0]], dtype=float)
    edges = np.array([[11, 0, 1, 0], [12, 1, 2, 0]], dtype=np.int64)
    normals = np.array([[0.0, 0.0, 1.0]], dtype=float)
    refused = plan_shared_surface_wall_edge_front(
        points, edges, normals, ["wall"], ["f"], ["g"], 1, 0.1, 1.0,
        minimum_allowed_step=0.2,
    )
    assert refused["accepted"] is False
    assert refused["reason"] == "collision_or_quality_failure"
    assert refused["generated_vertices"] == []
