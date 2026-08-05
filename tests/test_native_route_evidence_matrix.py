"""Python adapter smoke tests for the shared route evidence matrix."""

from __future__ import annotations

import copy

from core.evaluator.native_route_evidence_matrix import evaluate_route_evidence_matrix


def _row(product: str, requested: int = 0, actual: int = 0, mode: str = "disabled_identity"):
    return {
        "product": product,
        "engine": "native",
        "evidence_status": "observed",
        "boundary_layer": {
            "requested_layers": requested,
            "actual_layers": actual,
            "mode": mode,
        },
        "identity_exact": requested == 0,
        "authority_state": "source_verified",
        "field_origins_complete": True,
        "quality_accepted": True,
        "quality_profile_id": "profile-v1",
        "stage_publish_receipt": requested > 0,
        "topology": {
            "invalid": 0,
            "inverted": 0,
            "duplicate": 0,
            "non_manifold": 0,
            "self_intersecting": 0,
            "negative_measure": 0,
        },
    }


def test_adapter_is_read_only_and_never_publish_eligible() -> None:
    rows = [_row("tet"), _row("surface", 1, 1, "transaction_candidate")]
    before = copy.deepcopy(rows)
    result = evaluate_route_evidence_matrix(rows)
    assert rows == before
    assert result["publication_eligible"] is False
    assert result["runtime_route"] == "default_off"
    assert result["route_calls"] == 0
    assert result["counts"] == {
        "complete": 1,
        "positive_evidence_observed_unreleased": 1,
    }


def test_adapter_preserves_truthful_absence() -> None:
    result = evaluate_route_evidence_matrix(
        [{"product": "poly", "engine": "native", "evidence_status": "absent"}]
    )
    assert result["counts"] == {"absent": 1}
    assert result["rows"][0]["classification"] == "absent"
