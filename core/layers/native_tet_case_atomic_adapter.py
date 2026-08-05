"""Strict Native Tet case-bound wrapper around the atomic surface adapter."""

from __future__ import annotations

from typing import Any, Mapping, MutableMapping

from .native_tet_case_policy_binding import validate_case_policy_binding
from .surface_bl_atomic_adapter import _refusal, certify_and_persist_surface_plan
from .native_bl_atomic_certificate import AtomicCertificate, SourceAuthority


def certify_and_persist_case_bound_surface_plan(
    source_output: Mapping[str, Any],
    authority: SourceAuthority,
    plan: Mapping[str, Any] | None,
    destination: MutableMapping[str, Any],
    *,
    source_ledger: Mapping[str, Any],
    policy: Mapping[str, Any],
    case: str,
    observed_source_sha256: str | None,
    requested_layers: int,
    first_height: float,
    growth_ratio: float,
    authority_evidence: Mapping[str, Any] | None,
    topology_evidence: Mapping[str, Any] | None,
    quality_evidence: Mapping[str, Any] | None,
    candidate_output: Mapping[str, Any] | None = None,
    persist: Any = None,
) -> AtomicCertificate:
    """Require source-case binding before the generic atomic adapter is called."""
    if requested_layers > 0:
        if plan is None:
            return _refusal(source_output, requested_layers, "missing_native_candidate_plan")
        bound = validate_case_policy_binding(
            source_ledger, policy, plan, case=case,
            observed_source_sha256=observed_source_sha256,
        )
        if bound.get("status") != "PROVISIONAL_CASE_POLICY_BOUND":
            return _refusal(source_output, requested_layers, f"case_policy_binding:{bound.get('reason', 'refused')}", candidate=plan)
        # The case validator binds the real STL/CAD file digest. The generic
        # adapter additionally checks its JSON source snapshot, so do not make
        # the two unrelated digest domains look interchangeable.
        adapter_policy = dict(policy)
        adapter_policy.pop("source_sha256", None)
        return certify_and_persist_surface_plan(
            source_output, authority, plan, destination,
            requested_layers=requested_layers, first_height=first_height, growth_ratio=growth_ratio,
            authority_evidence=authority_evidence, topology_evidence=topology_evidence,
            quality_evidence=quality_evidence, candidate_output=candidate_output, persist=persist,
            wall_edge_policy=adapter_policy,
        )
    return certify_and_persist_surface_plan(
        source_output, authority, plan, destination,
        requested_layers=requested_layers, first_height=first_height, growth_ratio=growth_ratio,
        authority_evidence=authority_evidence, topology_evidence=topology_evidence,
        quality_evidence=quality_evidence, candidate_output=candidate_output, persist=persist,
    )
