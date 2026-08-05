from __future__ import annotations

from pathlib import Path

import numpy as np

from core.evaluator.native_surface_bl_front_optimizer import optimize_surface_wall_edge_front


BUILD = Path("/tmp/autotessell_surface_bl_front_shared_build")


def _authority(edges: np.ndarray) -> tuple[dict[str, str], list[dict[str, str]]]:
    cert = {
        "source_kind": "authoritative-stl-ledger",
        "raw_sha256": "a" * 64,
        "brep_hash": "b" * 64,
        "authority": "source-ledger-v1",
        "provenance": "direct-source-ledger",
    }
    rows = [
        {
            "source_edge": str(int(row[0])), "source_face": str(int(row[3])),
            "wall_edge": f"wall-{int(row[0])}", "output_face": f"out-{int(row[0])}",
            "feature": "feature-a", "patch": "wall", "physical_group": "fluid-wall",
            "component": "component-0", "provenance": "direct",
        }
        for row in edges
    ]
    return cert, rows


def test_strict_shared_front_bl0_identity_and_bl1_quality() -> None:
    points = np.asarray([[0, 0, 0], [1, 0, 0]], dtype=np.float64)
    edges = np.asarray([[11, 0, 1, 0]], dtype=np.int64)
    normals = np.asarray([[0, 0, 1]], dtype=np.float64)
    cert, rows = _authority(edges)
    bl0 = optimize_surface_wall_edge_front(
        points, edges, normals, ["wall"], ["feature-a"], ["fluid-wall"],
        0, 0.0, 1.2, cert, rows, strict_quality=True,
    )
    assert bl0["accepted"] is True
    assert bl0["status"] == "disabled_identity"
    bl1 = optimize_surface_wall_edge_front(
        points, edges, normals, ["wall"], ["feature-a"], ["fluid-wall"],
        1, 0.25, 1.0, cert, rows, max_step_halvings=0, strict_quality=True,
    )
    assert bl1["accepted"] is True, bl1
    quality = bl1["quality"]
    assert quality["shared_front"] is True
    assert quality["direction_strategy"] == "feature_sector_most_normal"
    assert quality["strict_profile"] is True
    assert quality["p95_skewness"] <= 0.10
    assert quality["p99_skewness"] <= 0.20
    assert quality["max_skewness"] <= 0.30
    assert quality["p95_non_orthogonality"] <= 10.0
    assert quality["p99_non_orthogonality"] <= 20.0
    assert quality["max_non_orthogonality"] <= 30.0
    assert quality["metric_aspect_p99"] <= 5.0
    assert quality["metric_aspect_ratio"] <= 10.0
    assert all(item["shared_front"] is True for item in bl1["provenance"])
    bl3 = optimize_surface_wall_edge_front(
        points, edges, normals, ["wall"], ["feature-a"], ["fluid-wall"],
        3, 0.25, 1.2, cert, rows, max_step_halvings=0, strict_quality=True,
    )
    assert bl3["accepted"] is True, bl3
    assert bl3["actual_layers"] == 3
    assert [item["requested_step"] for item in bl3["provenance"]] == [0.25, 0.3, 0.36]


def test_strict_shared_front_refuses_missing_authority_atomically() -> None:
    points = np.asarray([[0, 0, 0], [1, 0, 0]], dtype=np.float64)
    edges = np.asarray([[11, 0, 1, 0]], dtype=np.int64)
    normals = np.asarray([[0, 0, 1]], dtype=np.float64)
    result = optimize_surface_wall_edge_front(
        points, edges, normals, ["wall"], ["feature-a"], ["fluid-wall"],
        1, 0.25, 1.0, None, None, strict_quality=True,
    )
    assert result["accepted"] is False
    assert result["actual_layers"] == 0
    assert result["candidate_discarded"] is True
