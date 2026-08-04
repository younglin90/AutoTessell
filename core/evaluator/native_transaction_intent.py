"""Thin orchestration for the C++ authoritative transaction-intent gate.

This module deliberately does not add defaults, filter parameters, compute
geometry, or mint identities. The Electron/API request and writer manifest
must already be complete and are passed unchanged to the native kernel.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from core.utils.native_extensions import load_native_extension


def authorize_native_transaction(
    authority_ledger: Mapping[str, Any],
    raw_request: Mapping[str, Any],
    engine_manifest: Mapping[str, Any],
    quality_policy_v3: Mapping[str, Any],
    corridor_receipt: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Pass one lossless request to the C++ transaction-intent gate."""
    native = load_native_extension("native_transaction_intent")
    if native is None:
        return {
            "accepted": False,
            "status": "native_transaction_intent_unavailable",
            "reason": "intent_native_kernel_unavailable",
            "generated_entity_count": 0,
            "writer_calls": 0,
            "candidate_discarded": True,
            "rollback_required": True,
        }
    return dict(native.authorize_native_transaction_v1(
        dict(authority_ledger),
        dict(raw_request),
        dict(engine_manifest),
        dict(quality_policy_v3),
        None if corridor_receipt is None else dict(corridor_receipt),
    ))


def validate_transaction_intent_receipt(receipt: Any) -> dict[str, Any]:
    """Validate only receipt shape; all semantic checks remain in C++."""
    reasons: list[str] = []
    if not isinstance(receipt, Mapping):
        return {"accepted": False, "reasons": ["intent_receipt_mapping_required"]}
    if receipt.get("accepted") is not True:
        reasons.append("intent_receipt_not_accepted")
    if receipt.get("schema") != "autotessell/native-transaction-intent/v1":
        reasons.append("intent_receipt_schema")
    for key in ("request_sha256", "manifest_sha256", "writer_build_sha256", "quality_policy_v3_sha256", "receipt_sha256"):
        value = receipt.get(key)
        if not isinstance(value, str) or len(value) != 64:
            reasons.append(f"intent_receipt_{key}_missing")
    if receipt.get("generated_entity_count") != 0 or receipt.get("writer_calls") != 0:
        reasons.append("intent_receipt_writer_work_nonzero")
    if receipt.get("rollback_token_state") != "armed":
        reasons.append("intent_receipt_rollback_token_missing")
    return {"accepted": not reasons, "reasons": sorted(set(reasons))}


__all__ = ["authorize_native_transaction", "validate_transaction_intent_receipt"]
