from __future__ import annotations

import copy

import pytest


corridor = pytest.importorskip("native_wall_edge_metric_corridor")


def _policy(layers: int = 0) -> dict[str, object]:
    return {
        "engine": "native_all",
        "source_mode": "authoritative_cad_stl",
        "semantic_mode": "feature_patch_physical_group",
        "topology_mode": "strict_manifold",
        "target_cells": 100,
        "target_faces": 100,
        "count_tolerance": 0.25,
        "wall_edge_mode": "authoritative_directed_sector",
        "wall_selection": "authoritative_rows",
        "feature_mode": "preserve_all",
        "ridge_mode": "directed_sector",
        "corner_mode": "directed_sector",
        "metric_mode": "anisotropic_spd",
        "boundary_layer_count": layers,
        "boundary_layer_first_height": 0.1 if layers else 0.0,
        "boundary_layer_final_height": 0.1 if layers else 0.0,
        "boundary_layer_total_height": 0.1 if layers else 0.0,
        "boundary_layer_growth": 1.2,
        "metric_tangential_height": 1.0,
        "metric_co_normal_height": 1.0,
        "metric_normal_height": 1.0,
        "anisotropy": 1.0,
        "diffusion": 0.0,
        "attenuation": 0.0,
        "collision_tolerance": 1.0e-8,
        "visibility_tolerance": 1.0e-8,
        "height_tolerance": 1.0e-10,
        "max_metric_skewness": 1.0e-12,
        "max_signed_non_orthogonality": 1.0,
        "max_metric_aspect_ratio": 2.0,
        "min_positive_measure": 0.5,
        "seed": 7,
        "replay_count": 2,
    }


def _authority() -> dict[str, object]:
    return {
        "accepted": True,
        "source_sha256": "a" * 64,
        "semantic_sha256": "b" * 64,
        "config_sha256": "c" * 64,
        "writer_sha256": "d" * 64,
        "topology": {"duplicate": 0, "non_manifold": 0, "inverted": 0},
        "edges": [{
            "edge_id": "wall-edge-0",
            "sector_id": "sector-0",
            "feature": "flat-wall",
            "patch": "wall",
            "physical_group": "fluid-wall",
            "component": "plate",
            "provenance": "authoritative-cad",
        }],
    }


def _geometry(visible: bool = True) -> dict[str, object]:
    return {"edges": [{
        "edge_id": "wall-edge-0",
        "sector_id": "sector-0",
        "feature": "flat-wall",
        "patch": "wall",
        "physical_group": "fluid-wall",
        "component": "plate",
        "provenance": "authoritative-cad",
        "p0": [0.0, 0.0, 0.0],
        "p1": [1.0, 0.0, 0.0],
        "normal": [0.0, 0.0, 1.0],
        "visible": visible,
    }]}


def _obstacles() -> dict[str, object]:
    return {"boxes": []}


def test_corridor_seals_all_user_inputs_and_bl0_is_zero_work_identity() -> None:
    policy = _policy(0)
    sealed = corridor.seal_corridor_policy_v1(policy)
    assert sealed["accepted"] is True
    assert sealed["schema"].endswith("policy/v1")
    assert len(sealed["policy_sha256"]) == 64
    refused_policy = corridor.seal_corridor_policy_v1({**policy, "hidden_default": 1})
    assert refused_policy["accepted"] is False
    assert refused_policy["reason"] == "policy_unknown_key"

    result = corridor.certify_wall_edge_metric_corridor(_authority(), sealed, {}, _obstacles())
    assert result["accepted"] is True, result
    assert result["status"] == "disabled_identity"
    assert result["actual_layers"] == 0
    assert result["work_counters"] == {"layer_work": 0, "collision_queries": 0, "writer_calls": 0}
    assert result["rollback_required"] is False


def test_corridor_bl1_certifies_directed_frame_schedule_spd_and_quality() -> None:
    sealed = corridor.seal_corridor_policy_v1(_policy(1))
    result = corridor.certify_wall_edge_metric_corridor(_authority(), sealed, _geometry(), _obstacles())
    assert result["accepted"] is True, result
    assert result["actual_layers"] == 1
    assert result["layer_heights"] == pytest.approx([0.1])
    assert result["total_height"] == pytest.approx(0.1)
    assert result["metric_spd"] is True
    assert result["quality"]["metric_skewness_max"] == pytest.approx(0.0, abs=1.0e-12)
    assert result["quality"]["signed_non_orthogonality_max"] == pytest.approx(0.0, abs=1.0e-12)
    assert result["quality"]["metric_aspect_ratio"] == pytest.approx(1.0)
    assert result["edges"][0]["t"] == pytest.approx([1.0, 0.0, 0.0])
    assert result["edges"][0]["c"] == pytest.approx([0.0, 1.0, 0.0])
    assert result["edges"][0]["n"] == pytest.approx([0.0, 0.0, 1.0])
    assert result["edges"][0]["feature"] == "flat-wall"
    assert result["edges"][0]["physical_group"] == "fluid-wall"


def test_corridor_repeat_receipt_and_candidate_disk_parity_are_deterministic() -> None:
    sealed = corridor.seal_corridor_policy_v1(_policy(1))
    candidate = corridor.certify_wall_edge_metric_corridor(_authority(), sealed, _geometry(), _obstacles())
    reread = corridor.certify_wall_edge_metric_corridor(_authority(), sealed, _geometry(), _obstacles())
    assert candidate["receipt_sha256"] == reread["receipt_sha256"]
    parity = corridor.compare_corridor_receipts(candidate, reread)
    assert parity["accepted"] is True, parity
    assert parity["candidate_disk_parity"] is True

    tampered = copy.deepcopy(reread)
    tampered["source_sha256"] = "e" * 64
    refused = corridor.compare_corridor_receipts(candidate, tampered)
    assert refused["accepted"] is False
    assert refused["reason"] == "candidate_disk_receipt_mismatch"


def test_corridor_refuses_schedule_source_frame_visibility_and_collision_failures() -> None:
    inconsistent = _policy(2)
    inconsistent["boundary_layer_final_height"] = 0.3
    inconsistent["boundary_layer_total_height"] = 0.3
    sealed = corridor.seal_corridor_policy_v1(inconsistent)
    refused_schedule = corridor.certify_wall_edge_metric_corridor(_authority(), sealed, _geometry(), _obstacles())
    assert refused_schedule["accepted"] is False
    assert refused_schedule["reason"] == "layer_schedule_inconsistent"

    tampered_geometry = _geometry()
    tampered_geometry["edges"][0]["patch"] = "tampered"
    sealed_one = corridor.seal_corridor_policy_v1(_policy(1))
    refused_source = corridor.certify_wall_edge_metric_corridor(_authority(), sealed_one, tampered_geometry, _obstacles())
    assert refused_source["accepted"] is False
    assert refused_source["reason"] == "source_binding_lost"

    refused_visibility = corridor.certify_wall_edge_metric_corridor(_authority(), sealed_one, _geometry(False), _obstacles())
    assert refused_visibility["accepted"] is False
    assert refused_visibility["reason"] == "visibility_failed"

    obstacle = {"boxes": [{"obstacle_id": "close-gap", "lo": [-0.1, -0.1, 0.05], "hi": [1.1, 0.1, 0.2], "blocks_visibility": True}]}
    refused_collision = corridor.certify_wall_edge_metric_corridor(_authority(), sealed_one, _geometry(), obstacle)
    assert refused_collision["accepted"] is False
    assert refused_collision["reason"] == "collision_clearance_failed"


def test_corridor_refuses_degenerate_frame_and_metric_aspect() -> None:
    degenerate = _geometry()
    degenerate["edges"][0]["normal"] = [1.0, 0.0, 0.0]
    sealed = corridor.seal_corridor_policy_v1(_policy(1))
    refused_frame = corridor.certify_wall_edge_metric_corridor(_authority(), sealed, degenerate, _obstacles())
    assert refused_frame["accepted"] is False
    assert refused_frame["reason"] == "feature_frame_ambiguous"

    anisotropic = _policy(1)
    anisotropic["anisotropy"] = 4.0
    sealed_aspect = corridor.seal_corridor_policy_v1(anisotropic)
    refused_aspect = corridor.certify_wall_edge_metric_corridor(_authority(), sealed_aspect, _geometry(), _obstacles())
    assert refused_aspect["accepted"] is False
    assert refused_aspect["reason"] == "metric_quality_failed"
