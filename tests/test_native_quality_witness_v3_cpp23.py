from __future__ import annotations

import copy

import numpy as np
import pytest


native_witness = pytest.importorskip("native_quality_witness")


def _policy(layers: int = 0) -> dict[str, object]:
    return {
        "engine": "native_tet",
        "source_mode": "authoritative_cad",
        "semantic_mode": "feature_boundary_component",
        "topology_mode": "strict_manifold",
        "target_cells": 50,
        "target_faces": 0,
        "sizing_mode": "quality_first",
        "metric_mode": "isotropic",
        "boundary_layer_count": layers,
        "boundary_layer_first_height": 0.1 if layers else 0.0,
        "boundary_layer_total_height": 0.1 if layers else 0.0,
        "boundary_layer_growth": 1.2,
        "wall_edge_mode": "source_wall_edges",
        "feature_mode": "preserve_all",
        "max_non_orthogonality": 5.0,
        "max_skewness": 0.1,
        "max_aspect_ratio": 2.0,
        "min_volume": 0.5,
        "replay_count": 1,
        "count_tolerance": 0.5,
    }


def _cube_snapshot(layers: int = 0) -> dict[str, object]:
    points = np.array(
        [[0.0, 0.0, 0.0], [1.0, 0.0, 0.0], [1.0, 1.0, 0.0], [0.0, 1.0, 0.0],
         [0.0, 0.0, 1.0], [1.0, 0.0, 1.0], [1.0, 1.0, 1.0], [0.0, 1.0, 1.0]],
        dtype=np.float64,
    )
    faces = [[0, 3, 2, 1], [4, 5, 6, 7], [0, 1, 5, 4],
             [1, 2, 6, 5], [2, 3, 7, 6], [3, 0, 4, 7]]
    lineage = [
        {
            "writer_entity_id": f"writer-face-{index}",
            "source_face_id": f"source-face-{index}",
            "source_edge_id": f"source-edge-{index}",
            "feature": "cube-face",
            "patch": "wall",
            "physical_group": "fluid-wall",
            "component": "cube",
            "provenance": "authoritative-cad",
            "role": "wall",
        }
        for index in range(len(faces))
    ]
    return {
        "points": points,
        "faces": faces,
        "owner": np.zeros(len(faces), dtype=np.int64),
        "neighbour": np.empty(0, dtype=np.int64),
        "face_uids": [f"face-{index}" for index in range(len(faces))],
        "cell_uids": ["cell-0"],
        "lineage": lineage,
        "cell_volumes": [1.0],
        "boundary_layer": {
            "actual_layers": layers,
            "positive_thickness": layers > 0,
            "lineage_complete": True,
            "wall_edge_lineage_complete": True,
            "minimum_height": 0.1 if layers else 0.0,
        },
    }


def _authority() -> dict[str, str]:
    return {key: value * 64 for key, value in {
        "source_sha256": "a", "semantic_sha256": "b", "config_sha256": "c", "writer_sha256": "d",
    }.items()}


def test_v3_seals_complete_user_policy_and_rejects_unknown_key() -> None:
    policy = _policy()
    sealed = native_witness.seal_policy_v3(policy)
    assert sealed["accepted"] is True
    assert sealed["schema"] == "autotessell/native-quality-policy/v3"
    assert len(sealed["policy_sha256"]) == 64
    refused = native_witness.seal_policy_v3({**policy, "hardcoded_escape": True})
    assert refused["accepted"] is False
    assert refused["reason"] == "quality_policy_unknown_key"


@pytest.mark.parametrize("layers", [0, 1])
def test_v3_measures_cube_for_bl_zero_and_positive_wall_edge_bl(layers: int) -> None:
    policy = _policy(layers)
    sealed = native_witness.seal_policy_v3(policy)
    result = native_witness.evaluate_v3(_cube_snapshot(layers), _authority(), sealed, "candidate")
    assert result["accepted"] is True, result
    assert result["schema"].endswith("/v3")
    assert result["orientation_checked"] is True
    assert result["full_population"] is True
    assert result["topology"] == {"duplicate_faces": 0, "non_manifold_faces": 0, "inverted_faces": 0}
    assert result["boundary_layer"]["actual_layers"] == layers
    assert result["quality"]["skewness"]["max"] == pytest.approx(0.0, abs=1.0e-12)
    assert result["quality"]["aspect_ratio"]["max"] == pytest.approx(1.0)
    assert result["quality"]["cell_volume"]["min"] == pytest.approx(1.0)


def test_v3_candidate_and_reread_are_digest_and_metric_equal() -> None:
    policy = _policy(1)
    sealed = native_witness.seal_policy_v3(policy)
    candidate = native_witness.evaluate_v3(_cube_snapshot(1), _authority(), sealed, "candidate")
    reread = native_witness.evaluate_v3(_cube_snapshot(1), _authority(), sealed, "reread")
    parity = native_witness.compare_candidate_reread_v3(candidate, reread)
    assert parity["accepted"] is True, parity
    assert parity["candidate_disk_parity"] is True
    tampered = copy.deepcopy(reread)
    tampered["writer_sha256"] = "0" * 64
    refused = native_witness.compare_candidate_reread_v3(candidate, tampered)
    assert refused["accepted"] is False
    assert refused["reason"] == "quality_candidate_disk_digest_mismatch"


def test_v3_rejects_duplicate_surface_and_missing_positive_bl_evidence() -> None:
    policy = _policy()
    sealed = native_witness.seal_policy_v3(policy)
    duplicate = _cube_snapshot()
    duplicate["faces"] = list(duplicate["faces"]) + [duplicate["faces"][0]]
    duplicate["owner"] = np.zeros(7, dtype=np.int64)
    duplicate["face_uids"] = list(duplicate["face_uids"]) + ["face-duplicate"]
    duplicate["lineage"] = list(duplicate["lineage"]) + [duplicate["lineage"][0]]
    refused = native_witness.evaluate_v3(duplicate, _authority(), sealed, "candidate")
    assert refused["accepted"] is False
    assert refused["reason"] == "quality_duplicate_face"

    positive_policy = native_witness.seal_policy_v3(_policy(1))
    missing_bl = _cube_snapshot(1)
    missing_bl["boundary_layer"] = {"actual_layers": 1}
    refused_bl = native_witness.evaluate_v3(missing_bl, _authority(), positive_policy, "candidate")
    assert refused_bl["accepted"] is False
    assert refused_bl["reason"] == "quality_wall_edge_lineage_missing"
