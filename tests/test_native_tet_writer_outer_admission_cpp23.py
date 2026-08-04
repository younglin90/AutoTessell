from __future__ import annotations

from copy import deepcopy

import numpy as np

import native_tet_bl_admission as native

from tests.test_native_tet_bl_admission_cpp23 import _authority, _ledger, _policy, _tetra


def _full_input(layers: int = 1) -> dict[str, object]:
    return {
        "boundary_layer_count": layers,
        "first_height": 0.1,
        "growth_ratio": 1.2,
        "target_cells": 4,
        "target_faces": 4,
        "wall_edge_mode": "source_edge",
        "feature_angle": 30.0,
        "min_signed_volume": 0.1,
        "min_scaled_jacobian": 0.3,
        "max_skewness": 0.4,
        "max_non_orthogonality": 40.0,
        "max_aspect_ratio": 1.5,
    }


def _outer_ledger() -> dict[str, object]:
    ledger = deepcopy(_ledger())
    ledger["outer_face_authority"] = [
        {
            "source_face_id": f"face-{index}",
            "source_edge_id": f"edge-{index}",
            "feature": "feature-0",
            "patch": "wall",
            "physical_group": "fluid-wall",
            "component": "component-0",
            "provenance": "source-cad-0",
        }
        for index in range(4)
    ]
    return ledger


def _sealed_policy() -> dict[str, object]:
    policy = _policy()
    params = _full_input()
    policy["input_parameters"] = params
    policy["input_parameters_sha256"] = native.canonical_input_parameters_sha256(params)
    return policy


def test_writer_owned_outer_surface_binds_lineage_and_all_user_inputs() -> None:
    points, tets = _tetra()
    result = dict(native.admit_writer_owned_outer_surface(
        points, tets, _sealed_policy(), 1, _outer_ledger(), _authority()
    ))

    assert result["accepted"] is True
    assert result["writer_owned_outer_surface"] is True
    assert result["collision_surface_source"] == "writer_owned_outer_faces"
    assert result["outer_face_count"] == 4
    assert result["collision_broad_phase_pairs"] == 0
    assert result["collision_narrow_phase_hits"] == 0
    assert len(result["writer_face_ledger"]) == 4
    assert result["input_parameters_sha256"] == _sealed_policy()["input_parameters_sha256"]
    assert all(row["source_face_id"].startswith("face-") for row in result["writer_face_ledger"])


def test_writer_owned_outer_surface_rejects_tampered_parameter_digest() -> None:
    points, tets = _tetra()
    policy = _sealed_policy()
    policy["input_parameters"] = dict(policy["input_parameters"], target_cells=999)
    result = dict(native.admit_writer_owned_outer_surface(
        points, tets, policy, 1, _outer_ledger(), _authority()
    ))

    assert result["accepted"] is False
    assert result["refusal_stage"] == "policy"
    assert result["refusal_reason"] == "input_parameters_unsealed_or_incomplete"


def test_writer_owned_outer_surface_re_evaluates_changed_user_parameter() -> None:
    points, tets = _tetra()
    policy = _sealed_policy()
    params = dict(policy["input_parameters"], target_cells=999)
    policy["input_parameters"] = params
    policy["input_parameters_sha256"] = native.canonical_input_parameters_sha256(params)
    result = dict(native.admit_writer_owned_outer_surface(
        points, tets, policy, 1, _outer_ledger(), _authority()
    ))

    assert result["accepted"] is True
    assert result["input_parameters"]["target_cells"] == 999
