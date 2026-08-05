"""Thin adapter for the private deterministic Native Poly dual receipt."""
from __future__ import annotations
from typing import Any
from core.utils.native_extensions import import_native_extension

def validate_canonical_dual_hull_receipt(
    hull_mode: str,
    input_point_digest: str,
    input_label_digest: str,
    plane_group_digest: str,
    points: Any,
    polygon_vertices: Any,
    plane_normal: Any,
    source_label: str,
) -> dict[str, Any]:
    try:
        module = import_native_extension("native_poly_dual_deterministic_receipt")
        tolist = lambda value: value.tolist() if hasattr(value, "tolist") else value
        return dict(module.validate_canonical_dual_hull_receipt(
            str(hull_mode), str(input_point_digest), str(input_label_digest),
            str(plane_group_digest), tolist(points), tolist(polygon_vertices),
            tolist(plane_normal), str(source_label),
        ))
    except Exception as exc:  # noqa: BLE001
        return {
            "accepted": False,
            "status": "native_poly_dual_receipt_unavailable",
            "reason": f"native_poly_dual_receipt_unavailable:{type(exc).__name__}",
            "hull_mode": str(hull_mode),
            "runtime_route": "default_off",
            "publication_eligible": False,
            "candidate_discarded": True,
            "actual_layers": 0,
        }

__all__ = ["validate_canonical_dual_hull_receipt"]
