"""Thin adapter for the private C++ Native Poly authority-bound consumer."""
from __future__ import annotations
from typing import Any, Sequence
from core.utils.native_extensions import import_native_extension

def _rows(value: Any) -> list[list[Any]]:
    if hasattr(value, "tolist"):
        value = value.tolist()
    return [list(row) for row in value]

def _ints(value: Any) -> list[int]:
    if hasattr(value, "tolist"):
        value = value.tolist()
    return [int(item) for item in value]

def validate_native_poly_authority_bound(
    authority_receipt: dict[str, Any],
    optimizer_receipt: dict[str, Any],
    source_ledger: dict[str, Any],
    producer_certificate: dict[str, Any],
    partition: dict[str, Any],
    boundary_binding: Sequence[dict[str, Any]],
    points: Any,
    faces: Any,
    owner: Any,
    neighbour: Any,
    requested_layers: int,
    actual_layers: int,
    baseline_artifact_digest: str,
    candidate_artifact_digest: str,
) -> dict[str, Any]:
    try:
        module = import_native_extension("native_poly_authority_bound_consumer")
        return dict(module.validate_native_poly_authority_bound(
            dict(authority_receipt), dict(optimizer_receipt), dict(source_ledger),
            dict(producer_certificate), dict(partition),
            [dict(row) for row in boundary_binding],
            _rows(points), _rows(faces), _ints(owner), _ints(neighbour),
            int(requested_layers), int(actual_layers),
            str(baseline_artifact_digest), str(candidate_artifact_digest),
        ))
    except Exception as exc:  # noqa: BLE001
        return {
            "accepted": False,
            "status": "native_poly_authority_bound_unavailable",
            "reason": f"native_poly_authority_bound_unavailable:{type(exc).__name__}",
            "requested_layers": int(requested_layers),
            "actual_layers": 0,
            "runtime_route": "default_off",
            "publication_eligible": False,
            "route_calls": 0,
            "candidate_discarded": True,
            "atomic_rollback": True,
        }

__all__ = ["validate_native_poly_authority_bound"]
