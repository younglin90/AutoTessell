from __future__ import annotations

import numpy as np

from core.evaluator.native_surface_bl_front_optimizer import optimize_surface_ridge_sector


def _case():
    # The same canonical wall edge is represented by two face sectors.  The
    # sectors receive independent co-normal fronts; no averaged ridge vertex
    # is allowed to contaminate either face.
    points = np.asarray([[0, 0, 0], [1, 0, 0]], dtype=np.float64)
    edges = np.asarray([[101, 0, 1, 0], [102, 0, 1, 1]], dtype=np.int64)
    normals = np.asarray([[0, 0, 1], [0, 1, 0]], dtype=np.float64)
    certificate = {
        "source_kind": "actual-brep-explicit-mapping",
        "raw_sha256": "a" * 64,
        "brep_hash": "b" * 64,
        "authority": "direct-source-ledger",
        "provenance": "canonical-edge-face-sector",
    }
    rows = [
        {
            "source_edge": str(int(row[0])), "source_face": str(int(row[3])),
            "wall_edge": f"wall-{int(row[0])}", "output_face": f"out-{int(row[0])}",
            "feature": f"feature-{int(row[3])}", "patch": f"patch-{int(row[3])}",
            "physical_group": f"group-{int(row[3])}", "component": "plate",
            "provenance": "direct-sector-ledger",
        }
        for row in edges
    ]
    return points, edges, normals, certificate, rows


def test_ridge_sector_bl0_bl1_bl3_is_deterministic_and_strict() -> None:
    points, edges, normals, certificate, rows = _case()
    for layers, growth in ((0, 1.0), (1, 1.0), (3, 1.2)):
        first = optimize_surface_ridge_sector(
            points, edges, normals, ["patch-0", "patch-1"],
            ["feature-0", "feature-1"], ["group-0", "group-1"],
            layers, 0.25, growth, certificate, rows, strict_quality=True,
        )
        second = optimize_surface_ridge_sector(
            points, edges, normals, ["patch-0", "patch-1"],
            ["feature-0", "feature-1"], ["group-0", "group-1"],
            layers, 0.25, growth, certificate, rows, strict_quality=True,
        )
        assert first == second
        assert first["accepted"] is True, first
        assert first["actual_layers"] == layers
        assert first["runtime_route"] == "default_off"
        assert first["publication_eligible"] is False
        if layers:
            assert first["quality"]["ridge_sector_fronts"] == 2
            assert first["quality"]["shared_front"] is True
            assert first["quality"]["p95_skewness"] == 0.0
            assert first["quality"]["p95_non_orthogonality"] == 0.0
            assert first["quality"]["metric_aspect_ratio"] == 4.0
            assert len(first["provenance"]) == 2 * layers
            assert {row["sector_id"] for row in first["provenance"]} == {
                "edge:101:face:0", "edge:102:face:1"
            }


def test_ridge_sector_missing_authority_rolls_back() -> None:
    points, edges, normals, _, rows = _case()
    result = optimize_surface_ridge_sector(
        points, edges, normals, ["patch-0", "patch-1"],
        ["feature-0", "feature-1"], ["group-0", "group-1"],
        1, 0.25, 1.0, None, None, strict_quality=True,
    )
    assert result["accepted"] is False
    assert result["actual_layers"] == 0
    assert result["candidate_discarded"] is True
