"""Apply an explicit user wall policy only to exact topological boundary edges."""

from __future__ import annotations

import hashlib
from typing import Any, Mapping


def apply_user_wall_edge_policy(ledger: Mapping[str, Any], *, select_boundary: bool = True) -> dict[str, Any]:
    if ledger.get("status") != "USER_DECLARED_PROVISIONAL_EDGE_LEDGER":
        return {"status": "REFUSED", "reason": "edge_ledger_not_valid", "release_eligible": False}
    if ledger.get("non_manifold_edge_count", 0) != 0:
        return {"status": "REFUSED", "reason": "non_manifold_edges_present", "release_eligible": False}
    candidates = [edge for edge in ledger.get("edges", []) if edge.get("incidence") == 1]
    selected = candidates if select_boundary else []
    if any(edge.get("incidence") != 1 for edge in selected):
        return {"status": "REFUSED", "reason": "selected_edge_not_topological_boundary", "release_eligible": False}
    ids = sorted(edge["edge_id"] for edge in selected)
    digest = hashlib.sha256(repr(ids).encode("utf-8")).hexdigest()
    return {
        "status": "USER_DECLARED_PROVISIONAL_WALL_EDGE_POLICY",
        "reason": "explicit_user_wall_policy_on_incidence_one_edges",
        "source_sha256": ledger.get("source_sha256"),
        "edge_digest": ledger.get("edge_digest"),
        "selected_edge_ids": ids,
        "selected_edge_count": len(ids),
        "selected_edge_digest": digest,
        "feature": "unclassified_boundary",
        "feature_authority": False,
        "physical_group": "fluid_wall",
        "physical_group_authority": "user_declared_provisional",
        "wall_edge_authority": False,
        "release_eligible": False,
        "runtime_route": "default_off",
    }
