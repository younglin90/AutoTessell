from __future__ import annotations

import copy

import pytest


intent = pytest.importorskip("native_transaction_intent")


def _digest_without(value: dict[str, object], key: str) -> str:
    payload = {name: item for name, item in value.items() if name != key}
    return intent.canonical_sha256_v1(payload)["sha256"]


def _request(layers: int = 0) -> dict[str, object]:
    parameters = [
        {"parameter_id": "source_mode", "type": "string", "value": "authoritative_cad", "explicit": True, "control_id": "source-mode"},
        {"parameter_id": "surface_metric", "type": "string", "value": "anisotropic_spd", "explicit": True, "control_id": "surface-metric"},
        {"parameter_id": "volume_metric", "type": "string", "value": "tet_quality", "explicit": True, "control_id": "volume-metric"},
        {"parameter_id": "boundary_layer_count", "type": "integer", "value": layers, "explicit": True, "control_id": "bl-count"},
        {"parameter_id": "wall_edge_mode", "type": "string", "value": "authoritative_directed_sector", "explicit": True, "control_id": "wall-edge"},
        {"parameter_id": "feature_mode", "type": "string", "value": "preserve_all", "explicit": True, "control_id": "features"},
        {"parameter_id": "topology_mode", "type": "string", "value": "strict_manifold", "explicit": True, "control_id": "topology"},
        {"parameter_id": "max_non_orthogonality", "type": "number", "value": 5.0, "explicit": True, "control_id": "quality-nonorth"},
        {"parameter_id": "target_cells", "type": "integer", "value": 100, "explicit": True, "control_id": "target-cells"},
        {"parameter_id": "seed", "type": "integer", "value": 7, "explicit": True, "control_id": "seed"},
        {"parameter_id": "provenance_mode", "type": "string", "value": "writer_ledger", "explicit": True, "control_id": "provenance"},
    ]
    request = {
        "schema": "autotessell/native-request/v1",
        "engine": "native_tet",
        "product": "native_tet",
        "ui_schema_version": "electron-input-v4",
        "control_schema_version": "native-input-contract-v3",
        "parameters": parameters,
    }
    request["request_sha256"] = _digest_without(request, "request_sha256")
    return request


def _manifest() -> dict[str, object]:
    sink_map = {
        "source_mode": ("source_authority", "source identity", "ingress"),
        "surface_metric": ("surface_metric", "surface metric", "surface-preflight"),
        "volume_metric": ("volume_metric", "volume metric", "volume-preflight"),
        "boundary_layer_count": ("bl_schedule", "layer count", "bl-schedule"),
        "wall_edge_mode": ("wall_edge_sector", "wall edge", "wall-edge-preflight"),
        "feature_mode": ("feature_protection", "feature preservation", "feature-gate"),
        "topology_mode": ("topology_transaction", "strict topology", "topology-gate"),
        "max_non_orthogonality": ("quality_gate", "non-orthogonality", "quality-gate"),
        "target_cells": ("count_tuning", "secondary count", "count-tuning"),
        "seed": ("seed_replay", "deterministic replay", "replay"),
        "provenance_mode": ("output_provenance", "output provenance", "writer-output"),
    }
    manifest = {
        "schema": "autotessell/native-writer-manifest/v1",
        "engine": "native_tet",
        "product": "native_tet",
        "writer_build_sha256": "f" * 64,
        "sinks": [
            {"parameter_id": parameter_id, "applicable": True, "primary_sink": sink, "semantic_role": role, "writer_stage": stage}
            for parameter_id, (sink, role, stage) in sink_map.items()
        ],
    }
    manifest["manifest_sha256"] = _digest_without(manifest, "manifest_sha256")
    return manifest


def _authority() -> dict[str, object]:
    return {
        "accepted": True,
        "source_mode": "authoritative_cad",
        "provenance_root": "cad-ledger-root-0",
        "source_sha256": "a" * 64,
        "semantic_sha256": "b" * 64,
        "config_sha256": "c" * 64,
        "writer_sha256": "d" * 64,
        "topology": {"duplicate": 0, "non_manifold": 0, "inverted": 0},
        "lineage_rows": [{
            "entity_id": "wall-edge-0", "feature": "flat-wall", "patch": "wall",
            "physical_group": "fluid-wall", "component": "cube", "provenance": "cad-ledger",
        }],
    }


def _quality(layers: int = 0) -> dict[str, object]:
    return {
        "accepted": True,
        "schema": "autotessell/native-quality-policy/v3",
        "policy_sha256": "e" * 64,
        "policy": {"boundary_layer_count": layers, "max_non_orthogonality": 5.0, "max_skewness": 0.1},
    }


def _corridor(layers: int = 1) -> dict[str, object]:
    return {
        "accepted": True,
        "schema": "autotessell/native-wall-edge-metric-corridor/v1",
        "actual_layers": layers,
        "receipt_sha256": "1" * 64,
        "metric_spd": True,
        "edges": [{"edge_id": "wall-edge-0", "sector_id": "sector-0"}],
    }


def _authorize(layers: int = 0, corridor: object = None) -> dict[str, object]:
    return intent.authorize_native_transaction_v1(_authority(), _request(layers), _manifest(), _quality(layers), corridor)


def test_intent_covers_all_sink_categories_and_bl0_zero_work() -> None:
    result = _authorize(0)
    assert result["accepted"] is True, result
    assert result["schema"].endswith("/v1")
    assert result["parameter_count"] == 11
    assert result["applicable_parameter_count"] == 11
    assert result["generated_entity_count"] == 0
    assert result["writer_calls"] == 0
    assert result["quality_precedes_count"] is True
    assert result["rollback_token_state"] == "armed"
    assert len(result["receipt_sha256"]) == 64
    assert {row["primary_sink"] for row in result["sink_rows"]} == {
        "source_authority", "surface_metric", "volume_metric", "bl_schedule", "wall_edge_sector",
        "feature_protection", "topology_transaction", "quality_gate", "count_tuning", "seed_replay", "output_provenance",
    }


def test_intent_is_deterministic_and_all_input_changes_are_sealed() -> None:
    first = _authorize(0)
    second = _authorize(0)
    assert first["receipt_sha256"] == second["receipt_sha256"]
    changed_request = _request(0)
    changed_request["parameters"][8]["value"] = 101
    changed_request["request_sha256"] = _digest_without(changed_request, "request_sha256")
    changed = intent.authorize_native_transaction_v1(_authority(), changed_request, _manifest(), _quality(0), None)
    assert changed["accepted"] is True, changed
    assert changed["request_sha256"] != first["request_sha256"]
    assert changed["receipt_sha256"] != first["receipt_sha256"]


@pytest.mark.parametrize(
    ("mutation", "reason"),
    [
        (lambda request: request["parameters"].append(copy.deepcopy(request["parameters"][0])), "intent_duplicate_parameter"),
        (lambda request: request["parameters"][0].update({"explicit": False}), "intent_request_schema_missing"),
        (lambda request: request["parameters"][0].update({"type": "integer"}), "intent_parameter_type_invalid"),
        (lambda request: request["parameters"][7].update({"value": float("nan")}), "intent_parameter_nonfinite"),
    ],
)
def test_intent_refuses_lossy_or_invalid_user_requests(mutation, reason: str) -> None:
    request = _request(0)
    mutation(request)
    try:
        request["request_sha256"] = _digest_without(request, "request_sha256")
    except KeyError:
        request["request_sha256"] = "0" * 64
    result = intent.authorize_native_transaction_v1(_authority(), request, _manifest(), _quality(0), None)
    assert result["accepted"] is False
    assert result["reason"] == reason


def test_intent_refuses_manifest_ambiguity_and_unconsumed_parameters() -> None:
    manifest = _manifest()
    manifest["sinks"].append(copy.deepcopy(manifest["sinks"][0]))
    manifest["manifest_sha256"] = _digest_without(manifest, "manifest_sha256")
    refused = intent.authorize_native_transaction_v1(_authority(), _request(0), manifest, _quality(0), None)
    assert refused["accepted"] is False
    assert refused["reason"] == "intent_parameter_sink_ambiguous"

    manifest = _manifest()
    manifest["sinks"] = [row for row in manifest["sinks"] if row["parameter_id"] != "seed"]
    manifest["manifest_sha256"] = _digest_without(manifest, "manifest_sha256")
    refused_unconsumed = intent.authorize_native_transaction_v1(_authority(), _request(0), manifest, _quality(0), None)
    assert refused_unconsumed["accepted"] is False
    assert refused_unconsumed["reason"] == "intent_unknown_parameter"


def test_intent_positive_bl_requires_corridor_and_exact_layer_contract() -> None:
    missing = _authorize(1)
    assert missing["accepted"] is False
    assert missing["reason"] == "intent_positive_bl_corridor_missing"
    accepted = _authorize(1, _corridor(1))
    assert accepted["accepted"] is True, accepted
    assert accepted["boundary_layer_count"] == 1
    mismatch = _authorize(1, _corridor(3))
    assert mismatch["accepted"] is False
    assert mismatch["reason"] == "intent_layer_schedule_inconsistent"


def test_intent_refuses_authority_or_quality_tamper_and_consumes_rollback_token() -> None:
    authority = _authority()
    authority["topology"]["inverted"] = 1
    refused_authority = intent.authorize_native_transaction_v1(authority, _request(0), _manifest(), _quality(0), None)
    assert refused_authority["accepted"] is False
    assert refused_authority["reason"] == "intent_authority_ledger_missing"
    bad_quality = _quality(0)
    bad_quality["accepted"] = False
    refused_quality = intent.authorize_native_transaction_v1(_authority(), _request(0), _manifest(), bad_quality, None)
    assert refused_quality["accepted"] is False
    assert refused_quality["reason"] == "intent_quality_contract_missing"

    armed = _authorize(0)
    rolled_back = intent.rollback_transaction_intent_v1(armed, "quality_failure_after_writer_attempt")
    assert rolled_back["accepted"] is True
    assert rolled_back["rollback_token_state"] == "consumed"
    assert rolled_back["candidate_discarded"] is True
    refused_reuse = intent.rollback_transaction_intent_v1({**armed, "rollback_token_state": "consumed"}, "reuse")
    assert refused_reuse["accepted"] is False
    assert refused_reuse["reason"] == "intent_candidate_disk_intent_mismatch"
