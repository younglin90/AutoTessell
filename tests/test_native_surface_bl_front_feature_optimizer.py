"""L0 feature-aware physical-space wall-edge BL optimizer contract."""

from __future__ import annotations

from pathlib import Path

import numpy as np

from core.evaluator.native_surface_bl_front_optimizer import optimize_surface_wall_edge_front


BUILD = Path("/tmp/autotessell_surface_bl_front_shared_build")


def _authority(edges: np.ndarray) -> tuple[dict[str, str], list[dict[str, str]]]:
    certificate = {
        "source_kind": "stl",
        "raw_sha256": "raw-sha256",
        "brep_hash": "brep-hash",
        "authority": "source-ledger-v1",
        "provenance": "direct-source-ledger",
    }
    rows = [
        {
            "source_edge": str(int(row[0])),
            "source_face": str(int(row[3])),
            "wall_edge": f"wall-{int(row[0])}",
            "output_face": f"out-{int(row[0])}",
            "feature": "feature-a",
            "patch": "wall",
            "physical_group": "fluid-wall",
            "component": "component-0",
            "provenance": "direct",
        }
        for row in edges
    ]
    return certificate, rows


def _smooth_case():
    points = np.array([[0, 0, 0], [1, 0, 0], [1, 1, 0]], dtype=np.float64)
    edges = np.array([[11, 0, 1, 0], [12, 1, 2, 0]], dtype=np.int64)
    normals = np.array([[0, 0, 1]], dtype=np.float64)
    certificate, rows = _authority(edges)
    return points, edges, normals, certificate, rows


def test_bl0_is_exact_identity_and_private(monkeypatch):
    monkeypatch.setenv("AUTOTESSELL_EXT_BUILD_DIR", str(BUILD))
    points, edges, normals, certificate, rows = _smooth_case()
    result = optimize_surface_wall_edge_front(
        points, edges, normals, ["wall"], ["feature-a"], ["fluid-wall"], 0, 0.0, 1.2, certificate, rows
    )
    assert result["accepted"] is True
    assert result["status"] == "disabled_identity"
    assert result["actual_layers"] == 0
    assert result["generated_vertices"] == []
    assert result["runtime_route"] == "default_off"
    assert result["publication_eligible"] is False


def test_smooth_front_is_cumulative_deterministic_and_quality_first(monkeypatch):
    monkeypatch.setenv("AUTOTESSELL_EXT_BUILD_DIR", str(BUILD))
    points, edges, normals, certificate, rows = _smooth_case()
    args = (points, edges, normals, ["wall"], ["feature-a"], ["fluid-wall"], 3, 0.01, 1.2, certificate, rows)
    first = optimize_surface_wall_edge_front(*args)
    second = optimize_surface_wall_edge_front(*args)
    assert first == second
    assert first["accepted"] is True
    assert first["status"] == "stage_receipt_sealed"
    assert first["actual_layers"] == 3
    assert first["quality"]["max_skewness"] <= 0.50
    assert first["quality"]["max_non_orthogonality"] <= 50.0
    assert first["quality"]["duplicate"] == 0
    assert first["quality"]["non_manifold"] == 0
    assert all(item["direction_mode"] == "smooth" for item in first["provenance"])
    by_edge = {}
    for item in first["provenance"]:
        by_edge.setdefault(item["source_wall_edge"], []).append(item["used_step"])
    for steps in by_edge.values():
        assert np.allclose(np.asarray(steps[1:]) / np.asarray(steps[:-1]), 1.2)


def test_feature_junction_locks_direction_and_missing_authority_rolls_back(monkeypatch):
    monkeypatch.setenv("AUTOTESSELL_EXT_BUILD_DIR", str(BUILD))
    points = np.array([[0, 0, 0], [1, 0, 0], [1, 0, 0]], dtype=np.float64)
    edges = np.array([[21, 0, 1, 0], [22, 0, 2, 1]], dtype=np.int64)
    normals = np.array([[0, 0, 1], [0, 0, 1]], dtype=np.float64)
    certificate, rows = _authority(edges)
    result = optimize_surface_wall_edge_front(
        points, edges, normals, ["patch-a", "patch-b"], ["feature-a", "feature-b"], ["group-a", "group-b"], 1, 0.01, 1.0, certificate, rows
    )
    assert result["accepted"] is True
    assert {item["direction_mode"] for item in result["provenance"]} == {"feature_locked"}
    assert all(item["sector_ids"] for item in result["provenance"])
    refused = optimize_surface_wall_edge_front(
        points, edges, normals, ["patch-a", "patch-b"], ["feature-a", "feature-b"], ["group-a", "group-b"], 1, 0.01, 1.0, None, None
    )
    assert refused["accepted"] is False
    assert refused["reason"] == "authority_incomplete"
    assert refused["actual_layers"] == 0
