"""Fail-closed binding between provisional wall-edge policy and BL lineage."""

from __future__ import annotations

import hashlib
from typing import Any, Mapping


_REQUIRED = ("policy_edge_id", "source_face", "side", "layer", "patch", "feature", "physical_group", "component")


def validate_wall_edge_provenance(policy: Mapping[str, Any], candidate: Mapping[str, Any]) -> dict[str, Any]:
    if policy.get("status") != "USER_DECLARED_PROVISIONAL_WALL_EDGE_POLICY":
        return {"status": "REFUSED", "reason": "invalid_wall_edge_policy", "release_eligible": False}
    if policy.get("selected_edge_count", 0) == 0:
        return {"status": "REFUSED", "reason": "no_selected_wall_edges", "release_eligible": False}
    provenance = candidate.get("provenance")
    if not isinstance(provenance, list) or not provenance:
        return {"status": "REFUSED", "reason": "missing_candidate_provenance", "release_eligible": False}
    selected = set(policy.get("selected_edge_ids", ()))
    seen: set[str] = set()
    for item in provenance:
        if not isinstance(item, Mapping) or any(key not in item for key in _REQUIRED):
            return {"status": "REFUSED", "reason": "missing_policy_edge_identity_or_lineage", "release_eligible": False}
        edge_id = str(item["policy_edge_id"])
        if edge_id not in selected:
            return {"status": "REFUSED", "reason": "policy_edge_not_selected", "release_eligible": False}
        if edge_id in seen:
            return {"status": "REFUSED", "reason": "duplicate_policy_edge_lineage", "release_eligible": False}
        seen.add(edge_id)
        if item["feature"] != "unclassified_boundary":
            return {"status": "REFUSED", "reason": "feature_policy_mismatch", "release_eligible": False}
    digest = hashlib.sha256(repr(sorted(seen)).encode("utf-8")).hexdigest()
    return {
        "status": "PROVISIONAL_PROVENANCE_READY",
        "reason": "all_policy_edges_hash_bound",
        "bound_edge_count": len(seen),
        "bound_edge_digest": digest,
        "feature_authority": False,
        "wall_edge_authority": False,
        "release_eligible": False,
        "runtime_route": "default_off",
    }
