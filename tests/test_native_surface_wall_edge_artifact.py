from __future__ import annotations

import numpy as np

from core.layers.native_surface_wall_edge_artifact import build_surface_wall_edge_artifact


def _triangle_pair() -> tuple[np.ndarray, np.ndarray, np.ndarray, list[dict[str, object]]]:
    points = np.array(
        [
            [0.0, 0.0, 0.0], [1.0, 0.0, 0.0], [0.5, 0.866025403784, 0.0],
            [0.0, 0.0, 1.0], [1.0, 0.0, 1.0], [0.5, 0.866025403784, 1.0],
        ], dtype=np.float64,
    )
    triangles = np.array([[0, 1, 2], [3, 5, 4]], dtype=np.int64)
    normals = np.array([[0.0, 0.0, 1.0], [0.0, 0.0, -1.0]], dtype=np.float64)
    provenance = [
        {"source_wall_edge": "17", "source_face": 0, "side": "source", "layer": 0,
         "patch": "wall", "feature": "flat", "physical_group": "wall", "component": 0,
         "provenance": "source-ledger"},
        {"source_wall_edge": "17", "source_face": 0, "side": "outer", "layer": 1,
         "patch": "wall", "feature": "flat", "physical_group": "wall", "component": 0,
         "provenance": "surface-bl-sbl-015"},
    ]
    return points, triangles, normals, provenance


def test_bl0_is_exact_identity_and_does_not_need_generated_lineage() -> None:
    points, triangles, normals, _ = _triangle_pair()
    result = build_surface_wall_edge_artifact(
        points[:3], triangles[:1], points[:3], triangles[:1], normals[:1], [], [],
        requested_layers=0, authoritative_source=True,
        source_labels=np.array([7]), candidate_labels=np.array([7]),
    )
    assert result["accepted"] is True
    assert result["status"] == "disabled_identity"
    assert result["actual_layers"] == 0


def test_positive_bl_requires_authority_and_passes_independent_cpp_gates(monkeypatch) -> None:
    monkeypatch.setenv("AUTOTESSELL_EXT_BUILD_DIR", "/tmp/autotessell_surface_bl_independent_build")
    points, triangles, normals, provenance = _triangle_pair()
    result = build_surface_wall_edge_artifact(
        points[:3], triangles[:1], points, triangles, normals, provenance, ["17"],
        requested_layers=1, authoritative_source=True,
    )
    assert result["accepted"] is True
    assert result["status"] == "committed"
    assert result["actual_layers"] == 1
    assert result["independent"]["verdict"] == "PASS_FOR_REVIEW"
    assert result["quality"]["accepted"] is True


def test_positive_bl_refuses_unverified_source(monkeypatch) -> None:
    monkeypatch.setenv("AUTOTESSELL_EXT_BUILD_DIR", "/tmp/autotessell_surface_bl_independent_build")
    points, triangles, normals, provenance = _triangle_pair()
    result = build_surface_wall_edge_artifact(
        points[:3], triangles[:1], points, triangles, normals, provenance, ["17"],
        requested_layers=1, authoritative_source=False,
    )
    assert result["accepted"] is False
    assert result["reason"] == "missing_authoritative_source"
