"""Thin adapter for the private typed authority-bound transaction."""
from __future__ import annotations
from typing import Any
from core.utils.native_extensions import import_native_extension

def seal_authority_bound_surface_transaction(authority_receipt: dict[str, Any], optimizer_receipt: dict[str, Any], requested_layers: int) -> dict[str, Any]:
    try:
        module = import_native_extension("native_surface_bl_front_actual_v2_transaction")
        return dict(module.seal_authority_bound_surface_transaction(dict(authority_receipt), dict(optimizer_receipt), int(requested_layers)))
    except Exception as exc:  # noqa: BLE001
        return {"accepted": False, "status": "diagnostic_unavailable", "reason": f"native_authority_bound_transaction_unavailable:{type(exc).__name__}", "requested_layers": requested_layers, "actual_layers": 0, "runtime_route": "default_off", "publication_eligible": False}

__all__ = ["seal_authority_bound_surface_transaction"]
