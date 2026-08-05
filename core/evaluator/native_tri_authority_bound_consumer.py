"""Thin adapter for the private C++ Native Tri authority-bound consumer."""
from __future__ import annotations
from typing import Any, Sequence
from core.utils.native_extensions import import_native_extension

def _rows(value: Any) -> list[list[Any]]:
    if hasattr(value, "tolist"):
        value = value.tolist()
    return [list(row) for row in value]

def evaluate_native_tri_authority_bound(
    authority_receipt: dict[str, Any],
    optimizer_receipt: dict[str, Any],
    source_ledger: dict[str, Any],
    producer_certificate: dict[str, Any],
    boundary_binding: Sequence[dict[str, Any]],
    baseline_points: Any,
    baseline_triangles: Any,
    candidate_points: Any,
    candidate_triangles: Any,
    requested_layers: int,
    actual_layers: int,
    baseline_artifact_digest: str,
    candidate_artifact_digest: str,
    quad_relabel: bool = False,
) -> dict[str, Any]:
    try:
        module = import_native_extension("native_tri_authority_bound_consumer")
        return dict(module.validate_native_tri_authority_bound(
            dict(authority_receipt), dict(optimizer_receipt),
            dict(source_ledger), dict(producer_certificate),
            [dict(row) for row in boundary_binding],
            _rows(baseline_points), _rows(baseline_triangles),
            _rows(candidate_points), _rows(candidate_triangles),
            int(requested_layers), int(actual_layers),
            str(baseline_artifact_digest), str(candidate_artifact_digest),
            bool(quad_relabel),
        ))
    except Exception as exc:  # noqa: BLE001
        return {
            "accepted": False,
            "status": "native_tri_authority_bound_unavailable",
            "reason": f"native_tri_authority_bound_unavailable:{type(exc).__name__}",
            "requested_layers": int(requested_layers),
            "actual_layers": 0,
            "runtime_route": "default_off",
            "publication_eligible": False,
            "route_calls": 0,
            "candidate_discarded": True,
            "atomic_rollback": True,
        }

__all__ = ["evaluate_native_tri_authority_bound"]
