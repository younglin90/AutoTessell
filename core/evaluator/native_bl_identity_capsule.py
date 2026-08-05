"""Thin read-only adapter for the C++ BL=0 identity capsule witness."""

from __future__ import annotations

from typing import Any, Mapping

from core.utils.native_extensions import import_native_extension

CAPSULE_FIELDS = (
    "schema",
    "engine",
    "product",
    "mode",
    "source_sha256",
    "route_sha256",
    "geometry_sha256",
    "topology_sha256",
    "boundary_sha256",
    "feature_sha256",
    "physical_group_sha256",
    "component_sha256",
    "provenance_sha256",
    "artifact_tree_sha256",
    "quality_profile_id",
    "quality_witness_digest",
    "authority_certificate_sha256",
)


def _unavailable(reason: str, authority_state: Any) -> dict[str, Any]:
    return {
        "accepted": False,
        "identity_exact": False,
        "authority_state": authority_state if isinstance(authority_state, str) else "unverified",
        "publication_eligible": False,
        "status": "evidence_incomplete",
        "reason": reason,
        "reasons": [reason],
        "requested_layers": 0,
        "actual_layers": 0,
        "candidate_immutable": True,
        "runtime_route": "default_off",
    }


def normalize_bl0_identity_capsule_v1(
    baseline: Mapping[str, Any],
    candidate: Mapping[str, Any],
    *,
    requested_layers: int = 0,
    actual_layers: int = 0,
    topology: Mapping[str, Any],
    field_origins: Mapping[str, Any],
    authority_state: Any,
) -> dict[str, Any]:
    """Read evidence and fail closed; never fill or infer missing fields."""
    try:
        kernel = import_native_extension("native_bl_identity")
        return dict(
            kernel.normalize_bl0_identity_capsule_v1(
                dict(baseline),
                dict(candidate),
                requested_layers,
                actual_layers,
                dict(topology),
                dict(field_origins),
                authority_state,
            )
        )
    except Exception as exc:  # noqa: BLE001
        return _unavailable(
            f"native_bl_identity_capsule_unavailable:{type(exc).__name__}",
            authority_state,
        )


__all__ = ["CAPSULE_FIELDS", "normalize_bl0_identity_capsule_v1"]
