"""L0 independent verifier and explicit corpus matrix tests."""

from __future__ import annotations

import numpy as np
import pytest

from core.layers.surface_bl_independent_corpus import build_corpus_matrix, classify_verifier_row


independent = pytest.importorskip("native_surface_bl_independent_verifier")


def _case() -> tuple[np.ndarray, np.ndarray, np.ndarray, list[dict[str, object]]]:
    points = np.array([[0.0, 0.0, 0.0], [1.0, 0.0, 0.0], [0.5, 0.866025403784, 0.0]], dtype=np.float64)
    triangles = np.array([[0, 1, 2]], dtype=np.int64)
    normals = np.array([[0.0, 0.0, 1.0]], dtype=np.float64)
    provenance = [{
        "source_wall_edge": "17", "source_face": "3", "side": "left", "layer": 1,
        "patch": "wall", "feature": "ridge", "physical_group": "fluid", "component": "main",
    }]
    return points, triangles, normals, provenance


def test_independent_verifier_returns_review_state_without_sharing_quality_kernel() -> None:
    points, triangles, normals, provenance = _case()
    result = independent.verify_surface_artifact(points, triangles, normals, provenance, True, False)
    assert result["verdict"] == "PASS_FOR_REVIEW"
    assert result["surface_quality_recomputed"] is True
    assert result["volume_quality_recomputed"] is False
    assert result["topology"]["invalid"] == 0


def test_independent_verifier_refuses_duplicate_and_unverified_authority() -> None:
    points, triangles, normals, provenance = _case()
    duplicate = independent.verify_surface_artifact(
        points, np.vstack([triangles, triangles]), np.vstack([normals, normals]), provenance * 2, True, False
    )
    assert duplicate["verdict"] == "REFUSED"
    assert duplicate["topology"]["duplicate"] == 1
    unverified = independent.verify_surface_artifact(points, triangles, normals, provenance, False, False)
    assert unverified["verdict"] == "UNVERIFIED"


def test_corpus_matrix_is_explicit_and_missing_authority_never_passes() -> None:
    matrix = build_corpus_matrix(".")
    assert matrix["source_count"] == 8
    assert matrix["configuration_count"] == 19
    assert matrix["row_count"] == 152
    assert matrix["planned_verifier_invocations"] == 456
    assert {row["verdict"] for row in matrix["rows"]} == {"UNVERIFIED"}
    assert classify_verifier_row(authoritative_source=False, artifact_present=True, replay_identical=True, gate_passed=True) == "UNVERIFIED"
    assert classify_verifier_row(authoritative_source=True, artifact_present=True, replay_identical=False, gate_passed=True) == "REFUSED"
    assert classify_verifier_row(authoritative_source=True, artifact_present=True, replay_identical=True, gate_passed=True) == "PASS_FOR_REVIEW"
