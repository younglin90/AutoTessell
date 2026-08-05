"""L0 tests for the canonical read-only L1 artifact collector."""

from __future__ import annotations

from copy import deepcopy
import hashlib

from core.evaluator.native_l1_route_artifact_collector import collect_l1_route_artifacts
from core.evaluator.native_route_evidence_matrix import MATRIX_PRODUCTS


def _topology() -> dict[str, int]:
    return {
        "invalid": 0,
        "inverted": 0,
        "duplicate": 0,
        "non_manifold": 0,
        "self_intersecting": 0,
        "negative_measure": 0,
    }


def _artifact(product: str, *, layers: int = 0, raw: bytes = b"artifact") -> dict[str, object]:
    return {
        "product": product,
        "artifact_bytes": raw,
        "engine": "native",
        "evidence_status": "observed",
        "boundary_layer": {
            "requested_layers": layers,
            "actual_layers": layers,
            "mode": "disabled_identity" if layers == 0 else "transaction_candidate",
        },
        "identity_exact": layers == 0,
        "authority_state": "source_verified",
        "quality_accepted": True,
        "quality_profile_id": "surface-wall-edge-v2",
        "stage_publish_receipt": layers > 0,
        "topology": _topology(),
        "field_origins": {
            "source": "direct",
            "feature": "direct",
            "physical_group": "direct",
            "component": "direct",
            "provenance": "direct",
        },
        "source_fields": {
            "source": "source-sha",
            "feature": "feature-sha",
            "physical_group": "group-sha",
            "component": "component-sha",
            "provenance": "provenance-sha",
        },
    }


def test_all_products_are_collected_without_authority_or_route() -> None:
    artifacts = [_artifact(product) for product in MATRIX_PRODUCTS]
    before = deepcopy(artifacts)
    result = collect_l1_route_artifacts(artifacts)
    assert artifacts == before
    assert result["status"] == "collector_observed"
    assert result["counts"] == {"complete": 7}
    assert result["publication_eligible"] is False
    assert result["runtime_route"] == "default_off"
    assert result["route_calls"] == 0
    assert all(row["artifact_digest_scope"] == "raw_bytes" for row in result["rows"])


def test_positive_bl_is_observed_unreleased_and_digest_is_deterministic() -> None:
    artifact = _artifact("tet", layers=3, raw=b"tet-positive")
    first = collect_l1_route_artifacts([artifact])
    second = collect_l1_route_artifacts(deepcopy([artifact]))
    assert first == second
    assert first["counts"] == {"positive_evidence_observed_unreleased": 1}


def test_missing_typed_evidence_is_incomplete_and_not_bl0() -> None:
    artifact = _artifact("hex")
    del artifact["topology"]
    result = collect_l1_route_artifacts([artifact])
    assert result["counts"] == {"incomplete": 1}
    assert "topology_typed_counters_missing_or_invalid" in result["rows"][0]["reasons"]


def test_alias_duplicate_digest_and_authority_fail_closed() -> None:
    alias = _artifact("strict-quad")
    duplicate_a = _artifact("tet")
    duplicate_b = _artifact("tet")
    duplicate_b["artifact_bytes"] = b"other"
    malformed = _artifact("poly")
    malformed["artifact_sha256"] = "not-a-digest"
    malformed["artifact_digest_scope"] = "raw_bytes"
    inferred = _artifact("tri")
    inferred["authority_state"] = "inferred"
    result = collect_l1_route_artifacts([alias, duplicate_a, duplicate_b, malformed, inferred])
    assert result["counts"] == {"incomplete": 3, "bl0_exact_unreleased": 1, "complete": 1}
    assert all(row["publication_eligible"] is False for row in result["rows"])
