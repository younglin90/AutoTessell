from __future__ import annotations

import copy
import sys
from pathlib import Path

import pytest


sys.path.insert(0, str(Path(__file__).parent))
from test_native_transaction_intent_v1_cpp23 import (  # noqa: E402
    _authority,
    _corridor,
    _digest_without,
    _manifest,
    _quality,
    _request,
    intent,
)


executor = pytest.importorskip("native_transaction_executor")


def _intent(layers: int, seed: int) -> dict[str, object]:
    request = _request(layers)
    request["parameters"][9]["value"] = seed
    request["request_sha256"] = _digest_without(request, "request_sha256")
    corridor = None if layers == 0 else _corridor(layers)
    result = intent.authorize_native_transaction_v1(
        _authority(), request, _manifest(), _quality(layers), corridor
    )
    assert result["accepted"] is True, result
    return result


def _candidate(transaction: dict[str, object], layers: int, stage: str = "staged_candidate") -> dict[str, object]:
    candidate: dict[str, object] = {
        "accepted": True,
        "published": False,
        "writer_stage": stage,
        "intent_receipt_sha256": transaction["intent_receipt_sha256"],
        "writer_build_sha256": transaction["writer_build_sha256"],
        "policy_sha256": transaction["quality_policy_v3_sha256"],
        "corridor_receipt_sha256": transaction["corridor_receipt_sha256"],
        "source_sha256": transaction["source_sha256"],
        "semantic_sha256": transaction["semantic_sha256"],
        "config_sha256": transaction["config_sha256"],
        "writer_sha256": transaction["writer_sha256"],
        "source_feature_patch_group_component_provenance_complete": True,
        "entity_uids": ["cell-0", "face-0"],
        "lineage_rows": [
            {
                "entity_uid": "cell-0",
                "feature": "flat-wall",
                "patch": "wall",
                "physical_group": "fluid-wall",
                "component": "cube",
                "provenance": "cad-ledger",
            },
            {
                "entity_uid": "face-0",
                "feature": "flat-wall",
                "patch": "wall",
                "physical_group": "fluid-wall",
                "component": "cube",
                "provenance": "cad-ledger",
            },
        ],
        "topology": {"duplicate": 0, "non_manifold": 0, "inverted": 0},
        "quality": {
            "accepted": True,
            "aspect_family": "tet_dihedral",
            "signed_non_orthogonality_max": 0.0,
            "skewness_max": 0.0,
            "aspect_ratio_max": 1.0,
            "positive_measure_min": 1.0,
        },
        "boundary_layer": {
            "actual_layers": layers,
            "layer_work": 0 if layers == 0 else 3,
            "positive_measure": layers > 0,
            "rows": [] if layers == 0 else [{"role": "wall"}, {"role": "front"}, {"role": "side"}],
        },
        "strict_topology_checked": True,
        "quality_checked": True,
    }
    candidate["artifact_sha256"] = executor.canonical_artifact_sha256_v1(candidate)["sha256"]
    return candidate


def _disk(candidate: dict[str, object]) -> dict[str, object]:
    result = copy.deepcopy(candidate)
    result["writer_stage"] = "disk_reread"
    result["artifact_sha256"] = executor.canonical_artifact_sha256_v1(result)["sha256"]
    return result


def _commit(transaction: dict[str, object], layers: int) -> dict[str, object]:
    candidate = _candidate(transaction, layers)
    staged = executor.validate_candidate_v1(transaction, candidate)
    assert staged["accepted"] is True, staged
    reread = executor.validate_disk_reread_v1(staged, _disk(candidate))
    assert reread["accepted"] is True, reread
    published = executor.publish_transaction_v1(reread)
    assert published["accepted"] is True, published
    return published


def test_bl0_state_graph_commits_without_layer_work() -> None:
    intent_receipt = _intent(0, 101)
    transaction = executor.begin_transaction_v1(intent_receipt, _authority(), None)
    assert transaction["accepted"] is True, transaction
    published = _commit(transaction, 0)
    assert published["transaction_state"] == "published"
    assert published["published"] is True
    assert published["generated_entity_count"] == 2
    assert published["writer_calls"] == 1


def test_bl1_state_graph_commits_with_positive_wall_front_side_schedule() -> None:
    intent_receipt = _intent(1, 102)
    transaction = executor.begin_transaction_v1(intent_receipt, _authority(), _corridor(1))
    assert transaction["accepted"] is True, {"reason": transaction.get("reason"), "transaction": transaction}
    published = _commit(transaction, 1)
    assert published["transaction_state"] == "published"
    assert published["published"] is True
    assert published["boundary_layer_count"] == 1


def test_artifact_digest_is_deterministic_and_stage_independent() -> None:
    transaction = executor.begin_transaction_v1(_intent(0, 103), _authority(), None)
    candidate = _candidate(transaction, 0)
    disk = _disk(candidate)
    assert candidate["artifact_sha256"] == disk["artifact_sha256"]
    assert executor.canonical_artifact_sha256_v1(candidate)["sha256"] == candidate["artifact_sha256"]


def test_topology_and_bl_schedule_failures_are_atomic_refusals() -> None:
    transaction = executor.begin_transaction_v1(_intent(0, 104), _authority(), None)
    bad_topology = _candidate(transaction, 0)
    bad_topology["topology"]["inverted"] = 1
    bad_topology["artifact_sha256"] = executor.canonical_artifact_sha256_v1(bad_topology)["sha256"]
    refused_topology = executor.validate_candidate_v1(transaction, bad_topology)
    assert refused_topology["accepted"] is False
    assert refused_topology["reason"] == "executor_topology_invalid"
    assert refused_topology["rollback_required"] is True

    positive = executor.begin_transaction_v1(_intent(1, 105), _authority(), _corridor(1))
    assert positive["accepted"] is True, {"reason": positive.get("reason"), "transaction": positive}
    bad_roles = _candidate(positive, 1)
    bad_roles["boundary_layer"]["rows"] = [{"role": "wall"}, {"role": "front"}]
    bad_roles["artifact_sha256"] = executor.canonical_artifact_sha256_v1(bad_roles)["sha256"]
    refused_roles = executor.validate_candidate_v1(positive, bad_roles)
    assert refused_roles["accepted"] is False
    assert refused_roles["reason"] == "executor_bl_sector_or_schedule_lost"


def test_disk_reread_tamper_cannot_publish() -> None:
    transaction = executor.begin_transaction_v1(_intent(0, 106), _authority(), None)
    candidate = _candidate(transaction, 0)
    staged = executor.validate_candidate_v1(transaction, candidate)
    assert staged["accepted"] is True, staged
    tampered = _disk(candidate)
    tampered["entity_uids"] = ["cell-0", "face-tampered"]
    tampered["artifact_sha256"] = executor.canonical_artifact_sha256_v1(tampered)["sha256"]
    refused = executor.validate_disk_reread_v1(staged, tampered)
    assert refused["accepted"] is False
    assert refused["reason"] == "executor_feature_patch_group_component_lost"
    unpublished = executor.publish_transaction_v1(staged)
    assert unpublished["accepted"] is False
    assert unpublished["reason"] == "executor_publish_without_commit_token"


def test_intent_capability_is_single_use_and_staging_can_roll_back() -> None:
    intent_receipt = _intent(0, 107)
    first = executor.begin_transaction_v1(intent_receipt, _authority(), None)
    assert first["accepted"] is True, first
    reused = executor.begin_transaction_v1(intent_receipt, _authority(), None)
    assert reused["accepted"] is False
    assert reused["reason"] == "executor_capability_reused"
    rolled_back = executor.rollback_transaction_v1(first, "quality_gate_failure")
    assert rolled_back["accepted"] is True, rolled_back
    assert rolled_back["transaction_state"] == "rolled_back"
    assert rolled_back["candidate_discarded"] is True
    refused_reuse = executor.rollback_transaction_v1(rolled_back, "reuse")
    assert refused_reuse["accepted"] is False
    assert refused_reuse["reason"] == "executor_capability_reused"


def test_begin_requires_authority_zero_topology_and_exact_corridor_receipt() -> None:
    bad_authority = _authority()
    bad_authority["topology"]["duplicate"] = 1
    refused_authority = executor.begin_transaction_v1(_intent(0, 108), bad_authority, None)
    assert refused_authority["accepted"] is False
    assert refused_authority["reason"] == "executor_intent_not_armed"

    mismatched_corridor = _corridor(1)
    mismatched_corridor["receipt_sha256"] = "2" * 64
    refused_corridor = executor.begin_transaction_v1(_intent(1, 109), _authority(), mismatched_corridor)
    assert refused_corridor["accepted"] is False
    assert refused_corridor["reason"] == "executor_positive_bl_corridor_missing"
