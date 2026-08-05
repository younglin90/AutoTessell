"""L0/L1 contract tests for the shared native route evidence matrix."""

from __future__ import annotations

import copy

from core.evaluator.native_route_evidence_matrix import (
    MATRIX_PRODUCTS,
    evaluate_route_evidence_matrix,
)


def _topology(**updates: int) -> dict[str, int]:
    result = {
        "invalid": 0,
        "inverted": 0,
        "duplicate": 0,
        "non_manifold": 0,
        "self_intersecting": 0,
        "negative_measure": 0,
    }
    result.update(updates)
    return result


def _row(
    product: str,
    *,
    requested: int = 0,
    actual: int = 0,
    mode: str = "disabled_identity",
    evidence_status: str = "observed",
    identity_exact: bool = True,
    authority_state: str = "source_verified",
    origins: bool = True,
    quality: bool = True,
    profile: str = "surface-wall-edge-v2",
    receipt: bool = False,
    topology: dict[str, int] | None = None,
) -> dict[str, object]:
    return {
        "product": product,
        "engine": "native",
        "evidence_status": evidence_status,
        "boundary_layer": {
            "requested_layers": requested,
            "actual_layers": actual,
            "mode": mode,
        },
        "identity_exact": identity_exact,
        "authority_state": authority_state,
        "field_origins_complete": origins,
        "quality_accepted": quality,
        "quality_profile_id": profile,
        "stage_publish_receipt": receipt,
        "topology": topology or _topology(),
    }


def test_all_products_bl0_complete_or_exact_unreleased() -> None:
    rows = [_row(product) for product in MATRIX_PRODUCTS]
    result = evaluate_route_evidence_matrix(copy.deepcopy(rows))
    assert result["status"] == "matrix_observed"
    assert result["counts"] == {"complete": 7}
    assert all(item["publication_eligible"] is False for item in result["rows"])
    assert all(item["runtime_route"] == "default_off" for item in result["rows"])
    assert result["route_calls"] == 0

    incomplete_authority = [_row(product, authority_state="inferred") for product in MATRIX_PRODUCTS]
    result = evaluate_route_evidence_matrix(incomplete_authority)
    assert result["counts"] == {"bl0_exact_unreleased": 7}
    assert all("bl0_source_authority_incomplete" in row["reasons"] for row in result["rows"])


def test_positive_evidence_is_observed_but_never_publish_eligible() -> None:
    rows = [
        _row(
            product,
            requested=3,
            actual=3,
            mode="transaction_candidate",
            identity_exact=False,
            receipt=True,
        )
        for product in MATRIX_PRODUCTS
    ]
    first = evaluate_route_evidence_matrix(rows)
    second = evaluate_route_evidence_matrix(copy.deepcopy(rows))
    assert first == second
    assert first["counts"] == {"positive_evidence_observed_unreleased": 7}
    assert first["publication_eligible"] is False
    assert all(row["publication_eligible"] is False for row in first["rows"])


def test_absent_incomplete_and_conflict_are_not_bl0() -> None:
    rows = [
        _row("tet", evidence_status="absent"),
        {"product": "hex", "engine": "native", "evidence_status": "present"},
        _row("strict-quad"),
        _row("tri", requested=3, actual=1, mode="transaction_candidate", identity_exact=False),
        _row("poly", topology=_topology(negative_measure=1)),
    ]
    result = evaluate_route_evidence_matrix(rows)
    classes = [row["classification"] for row in result["rows"]]
    assert classes == ["absent", "incomplete", "conflict", "conflict", "incomplete"]
    assert result["counts"] == {"absent": 1, "conflict": 2, "incomplete": 2}
    assert result["publication_eligible"] is False


def test_profile_mismatch_and_boolean_authority_fail_closed() -> None:
    bad_profile = _row("surface", requested=1, actual=1, mode="transaction_candidate", identity_exact=False, profile="")
    bad_authority = _row("tet", authority_state="inferred", requested=1, actual=1, mode="transaction_candidate", identity_exact=False)
    result = evaluate_route_evidence_matrix([bad_profile, bad_authority])
    assert result["counts"] == {"incomplete": 1, "positive_evidence_observed_unreleased": 1}
    assert all(row["publication_eligible"] is False for row in result["rows"])
