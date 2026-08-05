from __future__ import annotations

import numpy as np
import pytest


independent = pytest.importorskip("native_surface_bl_independent_verifier")


def _lineage(count: int) -> list[dict[str, object]]:
    return [
        {
            "source_wall_edge": str(i),
            "source_face": str(i),
            "side": "left",
            "layer": 1,
            "patch": "wall",
            "feature": "smooth",
            "physical_group": "fluid-wall",
            "component": "main",
        }
        for i in range(count)
    ]


def test_true_narrow_phase_does_not_reject_aabb_only_false_positive() -> None:
    points = np.asarray(
        [
            [0.0, 0.0, 0.0],
            [2.0, 0.0, 0.0],
            [0.0, 2.0, 0.0],
            [1.6, 1.6, 0.0],
            [2.0, 1.6, 0.0],
            [1.6, 2.0, 0.0],
        ],
        dtype=np.float64,
    )
    triangles = np.asarray([[0, 1, 2], [3, 4, 5]], dtype=np.int64)
    normals = np.asarray([[0.0, 0.0, 1.0], [0.0, 0.0, 1.0]], dtype=np.float64)
    result = independent.verify_surface_artifact(
        points, triangles, normals, _lineage(2), True, False, 1e-12, 10.0, 20.0, 0.5, 0.75
    )
    assert result["verdict"] == "PASS_FOR_REVIEW", result
    assert result["topology"]["broad_phase_candidate_pairs"] == 1
    assert result["topology"]["narrow_phase_intersections"] == 0
    assert result["quality"]["gate_passed"] is True


def test_quality_gate_reports_and_refuses_skinny_surface() -> None:
    points = np.asarray([[0.0, 0.0, 0.0], [100.0, 0.0, 0.0], [0.001, 0.001, 0.0]], dtype=np.float64)
    triangles = np.asarray([[0, 1, 2]], dtype=np.int64)
    normals = np.asarray([[0.0, 0.0, 1.0]], dtype=np.float64)
    refused = independent.verify_surface_artifact(
        points, triangles, normals, _lineage(1), True, False
    )
    assert refused["verdict"] == "REFUSED"
    assert refused["reason"] == "surface_quality_gate_failed"
    assert refused["quality"]["aspect_ratio_max"] > 20.0
    accepted_with_explicit_limits = independent.verify_surface_artifact(
        points,
        triangles,
        normals,
        _lineage(1),
        True,
        False,
        1e-12,
        100000.0,
        100000.0,
        1.0,
        1.0,
    )
    assert accepted_with_explicit_limits["verdict"] == "PASS_FOR_REVIEW"
