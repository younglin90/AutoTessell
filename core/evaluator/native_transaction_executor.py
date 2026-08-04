"""Lossless Python transport for the C++ authoritative writer transaction.

The adapter deliberately performs no geometry work, quality calculation, ID
minting, default insertion, or parameter rewriting.  It only marshals the
already-authoritative receipts and delegates every state transition to the
native executor.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from core.utils.native_extensions import load_native_extension


def _native() -> Any | None:
    return load_native_extension("native_transaction_executor")


def begin_authoritative_transaction(
    intent_receipt: Mapping[str, Any],
    authority_ledger: Mapping[str, Any],
    corridor_receipt: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Open one native staging capability without changing caller values."""
    native = _native()
    if native is None:
        return _unavailable("executor_native_kernel_unavailable")
    return dict(native.begin_transaction_v1(
        dict(intent_receipt),
        dict(authority_ledger),
        None if corridor_receipt is None else dict(corridor_receipt),
    ))


def validate_staged_candidate(
    transaction: Mapping[str, Any], candidate: Mapping[str, Any]
) -> dict[str, Any]:
    native = _native()
    if native is None:
        return _unavailable("executor_native_kernel_unavailable")
    return dict(native.validate_candidate_v1(dict(transaction), dict(candidate)))


def validate_persisted_reread(
    transaction: Mapping[str, Any], disk_reread: Mapping[str, Any]
) -> dict[str, Any]:
    native = _native()
    if native is None:
        return _unavailable("executor_native_kernel_unavailable")
    return dict(native.validate_disk_reread_v1(dict(transaction), dict(disk_reread)))


def publish_authoritative_transaction(transaction: Mapping[str, Any]) -> dict[str, Any]:
    native = _native()
    if native is None:
        return _unavailable("executor_native_kernel_unavailable")
    return dict(native.publish_transaction_v1(dict(transaction)))


def rollback_authoritative_transaction(
    transaction: Mapping[str, Any], reason: str
) -> dict[str, Any]:
    native = _native()
    if native is None:
        return _unavailable("executor_native_kernel_unavailable")
    return dict(native.rollback_transaction_v1(dict(transaction), reason))


def _unavailable(reason: str) -> dict[str, Any]:
    return {
        "accepted": False,
        "schema": "autotessell/native-transaction-executor/v1",
        "status": "native_transaction_executor_unavailable",
        "reason": reason,
        "published": False,
        "candidate_discarded": True,
        "rollback_required": True,
        "generated_entity_count": 0,
        "writer_calls": 0,
    }


__all__ = [
    "begin_authoritative_transaction",
    "validate_staged_candidate",
    "validate_persisted_reread",
    "publish_authoritative_transaction",
    "rollback_authoritative_transaction",
]
