"""Bind one provisional wall policy to one provisional source-ledger case."""

from __future__ import annotations

import hashlib
from typing import Any, Mapping

from .native_bl_atomic_certificate import canonical_bytes


def _digest(value: Any) -> str:
    return hashlib.sha256(canonical_bytes(value)).hexdigest()


def _mapping_for_face(source: Mapping[str, Any], face: int) -> Mapping[str, Any] | None:
    for item in source.get("mapping_ranges", ()):
        if isinstance(item, Mapping) and int(item.get("start", -1)) <= face <= int(item.get("end", -2)):
            return item
    return None


def validate_case_policy_binding(
    source_ledger: Mapping[str, Any],
    policy: Mapping[str, Any],
    candidate: Mapping[str, Any],
    *,
    case: str,
    observed_source_sha256: str | None = None,
) -> dict[str, Any]:
    """Fail closed when policy and candidate labels do not belong to one case."""
    if source_ledger.get("schema") != "NativeTetSurfaceSourceLedger/v1" or source_ledger.get("status") != "USER_DECLARED_PROVISIONAL":
        return {"status": "REFUSED", "reason": "invalid_source_ledger", "release_eligible": False}
    sources = [item for item in source_ledger.get("sources", ()) if isinstance(item, Mapping) and item.get("case") == case]
    if len(sources) != 1:
        return {"status": "REFUSED", "reason": "source_case_not_unique", "release_eligible": False}
    source = sources[0]
    if observed_source_sha256 is None:
        return {"status": "REFUSED", "reason": "missing_observed_source_digest", "release_eligible": False}
    if observed_source_sha256 != source.get("sha256"):
        return {"status": "REFUSED", "reason": "source_file_digest_mismatch", "release_eligible": False}
    if policy.get("case", case) != case:
        return {"status": "REFUSED", "reason": "policy_case_mismatch", "release_eligible": False}
    if policy.get("source_sha256") != source.get("sha256"):
        return {"status": "REFUSED", "reason": "policy_source_digest_mismatch", "release_eligible": False}
    if policy.get("status") != "USER_DECLARED_PROVISIONAL_WALL_EDGE_POLICY":
        return {"status": "REFUSED", "reason": "invalid_wall_edge_policy", "release_eligible": False}
    provenance = candidate.get("provenance")
    if not isinstance(provenance, list) or not provenance:
        return {"status": "REFUSED", "reason": "missing_candidate_provenance", "release_eligible": False}
    for item in provenance:
        if not isinstance(item, Mapping):
            return {"status": "REFUSED", "reason": "missing_case_lineage", "release_eligible": False}
        face = item.get("source_face")
        if not isinstance(face, int) or isinstance(face, bool):
            return {"status": "REFUSED", "reason": "invalid_source_face", "release_eligible": False}
        mapping = _mapping_for_face(source, face)
        if mapping is None:
            return {"status": "REFUSED", "reason": "source_face_not_mapped", "release_eligible": False}
        for field in ("patch", "physical_group", "component"):
            if item.get(field) != mapping.get(field) or item.get(field) != policy.get(field, mapping.get(field)):
                return {"status": "REFUSED", "reason": f"case_{field}_mismatch", "release_eligible": False}
        policy_feature = policy.get("feature")
        if item.get("feature") != policy_feature:
            return {"status": "REFUSED", "reason": "case_feature_mismatch", "release_eligible": False}
        if mapping.get("feature") not in {"unclassified", policy_feature}:
            return {"status": "REFUSED", "reason": "source_feature_not_compatible", "release_eligible": False}
    return {
        "status": "PROVISIONAL_CASE_POLICY_BOUND",
        "case": case,
        "source_sha256": source.get("sha256"),
        "policy_sha256": _digest(policy),
        "feature_authority": False,
        "wall_edge_authority": False,
        "release_eligible": False,
        "runtime_route": "default_off",
    }
