"""Read-only direct-origin BL=0 capsule adapter tests."""

from __future__ import annotations

import copy

from core.evaluator.native_bl_identity_capsule import (
    CAPSULE_FIELDS,
    normalize_bl0_identity_capsule_v1,
)
from tests.test_native_bl_identity_cpp23 import _record, _topology


def _origins() -> dict[str, str]:
    return {field: "direct" for field in CAPSULE_FIELDS}


def _topology_capsule(**updates: int) -> dict[str, int]:
    result = _topology()
    result["negative_measure"] = 0
    result.update(updates)
    return result


def test_complete_direct_source_verified_capsule_is_identity_only() -> None:
    baseline = _record(product="surface")
    candidate = copy.deepcopy(baseline)
    result = normalize_bl0_identity_capsule_v1(
        baseline,
        candidate,
        topology=_topology_capsule(),
        field_origins=_origins(),
        authority_state="source_verified",
    )
    assert result["accepted"] is True
    assert result["identity_exact"] is True
    assert result["authority_state"] == "source_verified"
    assert result["publication_eligible"] is False
    assert result["actual_layers"] == 0
    assert result["runtime_route"] == "default_off"


def test_exact_identity_without_authority_is_not_accepted() -> None:
    baseline = _record(product="hex")
    result = normalize_bl0_identity_capsule_v1(
        baseline,
        copy.deepcopy(baseline),
        topology=_topology_capsule(),
        field_origins=_origins(),
        authority_state="inferred",
    )
    assert result["accepted"] is False
    assert result["identity_exact"] is True
    assert result["status"] == "evidence_incomplete"
    assert "authority_state_not_source_verified" in result["reasons"]


def test_missing_or_inferred_origin_and_negative_measure_refuse() -> None:
    baseline = _record(product="poly")
    missing = _origins()
    del missing["component_sha256"]
    result = normalize_bl0_identity_capsule_v1(
        baseline,
        copy.deepcopy(baseline),
        topology=_topology_capsule(),
        field_origins=missing,
        authority_state="source_verified",
    )
    assert result["accepted"] is False
    assert "origin_missing:component_sha256" in result["reasons"]

    unknown = _origins()
    unknown["invented_hash"] = "direct"
    result = normalize_bl0_identity_capsule_v1(
        baseline,
        copy.deepcopy(baseline),
        topology=_topology_capsule(),
        field_origins=unknown,
        authority_state="source_verified",
    )
    assert result["accepted"] is False
    assert "origin_unknown:invented_hash" in result["reasons"]

    result = normalize_bl0_identity_capsule_v1(
        baseline,
        copy.deepcopy(baseline),
        topology=_topology_capsule(negative_measure=1),
        field_origins=_origins(),
        authority_state="source_verified",
    )
    assert result["accepted"] is False
    assert "topology_nonzero:negative_measure" in result["reasons"]


def test_boolean_authority_and_layer_mutation_never_promote() -> None:
    baseline = _record(product="tri_plus_quad")
    result = normalize_bl0_identity_capsule_v1(
        baseline,
        copy.deepcopy(baseline),
        requested_layers=1,
        actual_layers=1,
        topology=_topology_capsule(),
        field_origins=_origins(),
        authority_state=True,
    )
    assert result["accepted"] is False
    assert result["publication_eligible"] is False
    assert result["actual_layers"] == 0
