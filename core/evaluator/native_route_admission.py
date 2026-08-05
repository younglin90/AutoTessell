"""Fail-closed admission for an actual native release route.

Route selection alone must never look like a release.  This adapter combines
the explicit product registry with the immutable corpus-readiness result and,
when a candidate is supplied, the Gate4 and quality witnesses.  It does not
run a mesher or synthesize missing evidence; a missing witness is a measured
refusal that the campaign runner can record and retry after the corpus is
repaired by an authoritative route.
"""
from __future__ import annotations

from typing import Any, Mapping

from .native_route_registry import SCHEMA as ROUTE_SCHEMA
from .native_route_registry import select_native_route

SCHEMA = "autotessell/native-route-admission/v1"


def _refusal(route: Mapping[str, Any], status: str, reasons: list[str]) -> dict[str, Any]:
    return {
        "schema": SCHEMA,
        "route_schema": ROUTE_SCHEMA,
        "accepted": False,
        "publication_eligible": False,
        "release_claim_eligible": False,
        "status": status,
        "route": dict(route),
        "reasons": sorted(set(reasons)),
    }


def admit_native_route_candidate(
    product: str,
    *,
    boundary_layers: int,
    source_kind: str,
    corpus_case: Mapping[str, Any] | None,
    gate4: Mapping[str, Any] | None = None,
    quality_witness: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Admit one measured candidate, or return a durable refusal.

    ``corpus_case`` is the per-case output of
    :func:`audit_native_campaign_config`.  A positive-layer route additionally
    needs a positive-thickness witness.  All products require Gate4 and a
    quality witness before publication, including BL=0; BL=0 only skips the
    positive-thickness requirement.
    """
    route = select_native_route(
        product, boundary_layers=boundary_layers, source_kind=source_kind
    )
    if route.get("accepted") is not True:
        return _refusal(route, "route_refused", list(route.get("reasons", ())))

    reasons: list[str] = []
    if not isinstance(corpus_case, Mapping):
        reasons.append("corpus_case_missing")
    else:
        if corpus_case.get("ready") is not True:
            reasons.append("corpus_not_ready")
            reasons.extend(str(reason) for reason in corpus_case.get("reasons", ()))

    if not isinstance(gate4, Mapping) or gate4.get("accepted") is not True:
        reasons.append("gate4_witness_missing")
    if not isinstance(quality_witness, Mapping) or quality_witness.get("accepted") is not True:
        reasons.append("quality_witness_missing")
    elif boundary_layers > 0:
        layer = quality_witness.get("boundary_layer")
        if not isinstance(layer, Mapping):
            reasons.append("positive_boundary_layer_witness_missing")
        else:
            requested = layer.get("requested_layers")
            actual = layer.get("actual_layers")
            thickness = layer.get("first_layer_height")
            if requested != boundary_layers or actual != boundary_layers:
                reasons.append("positive_boundary_layer_count_mismatch")
            if not isinstance(thickness, (int, float)) or thickness <= 0.0:
                reasons.append("positive_boundary_layer_thickness_missing")

    if reasons:
        return _refusal(route, "candidate_refused", reasons)

    return {
        "schema": SCHEMA,
        "route_schema": ROUTE_SCHEMA,
        "accepted": True,
        "publication_eligible": True,
        "release_claim_eligible": True,
        "status": "candidate_admitted",
        "route": dict(route),
        "reasons": [],
        "boundary_layers": boundary_layers,
    }


__all__ = ["SCHEMA", "admit_native_route_candidate"]
