"""Thin Python orchestration adapter for the private C++ Tet/Hex authority-bound consumer."""
from __future__ import annotations
from typing import Any, Sequence
from core.utils.native_extensions import import_native_extension

def _rows(value: Any) -> list[list[Any]]:
    if hasattr(value, "tolist"):
        value = value.tolist()
    return [list(row) for row in value]

def evaluate_native_tet_hex_authority_bound_transaction(
    engine: str,
    authority_receipt: dict[str, Any],
    optimizer_receipt: dict[str, Any],
    boundary_binding: Sequence[dict[str, Any]],
    baseline_points: Any,
    baseline_cells: Any,
    candidate_points: Any,
    candidate_cells: Any,
    requested_layers: int,
    actual_layers: int,
) -> dict[str, Any]:
    try:
        kernel = import_native_extension("native_tet_hex_authority_bound_consumer")
        return dict(kernel.validate_native_tet_hex_authority_bound_transaction(
            str(engine), dict(authority_receipt), dict(optimizer_receipt),
            [dict(row) for row in boundary_binding],
            _rows(baseline_points), _rows(baseline_cells),
            _rows(candidate_points), _rows(candidate_cells),
            int(requested_layers), int(actual_layers),
        ))
    except Exception as exc:  # noqa: BLE001
        return {
            "accepted": False,
            "status": "authority_bound_consumer_unavailable",
            "reason": f"native_tet_hex_authority_bound_consumer_unavailable:{type(exc).__name__}",
            "engine": str(engine),
            "requested_layers": int(requested_layers),
            "actual_layers": 0,
            "runtime_route": "default_off",
            "publication_eligible": False,
            "route_calls": 0,
            "candidate_discarded": True,
            "atomic_rollback": True,
        }

__all__ = ["evaluate_native_tet_hex_authority_bound_transaction"]
