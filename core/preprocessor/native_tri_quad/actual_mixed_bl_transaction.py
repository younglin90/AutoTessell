"""Private adapter for the source-bound Native TRI+QUAD mixed BL transaction."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Mapping

from core.preprocessor.native_tri_quad.authority_ingress_receipt import (
    validate_native_tri_quad_authority_ingress,
)
from core.utils.native_extensions import import_native_extension


def run_native_tri_quad_actual_mixed_bl_transaction(
    source: bytes | bytearray | memoryview | str | Path,
    points: Any,
    triangles: Any,
    quads: Any,
    receipt: Mapping[str, Any],
    wall_loop: Any,
    co_normals: Any,
    layer_heights: Any,
    requested_layers: int,
    max_offset: float,
) -> dict[str, Any]:
    """Validate the sealed ingress first, then invoke the private C++ transaction."""
    authority = validate_native_tri_quad_authority_ingress(
        source, points, triangles, quads, receipt
    )
    if not authority.get("accepted", False):
        return {
            **authority,
            "status": "tri_quad_actual_mixed_bl_transaction_refused",
            "reason": f"authority_ingress:{authority.get('reason', 'rejected')}",
        }
    try:
        kernel = import_native_extension("native_tri_quad_actual_mixed_bl_transaction")
        return dict(kernel.run_transaction(
            points.tolist() if hasattr(points, "tolist") else points,
            triangles.tolist() if hasattr(triangles, "tolist") else triangles,
            quads.tolist() if hasattr(quads, "tolist") else quads,
            dict(receipt), wall_loop, co_normals,
            layer_heights, int(requested_layers), float(max_offset),
        ))
    except Exception as exc:  # noqa: BLE001
        return {
            "accepted": False,
            "status": "tri_quad_actual_mixed_bl_transaction_refused",
            "reason": f"native_transaction_unavailable:{type(exc).__name__}",
            "requested_layers": 0,
            "actual_layers": 0,
            "candidate_discarded": True,
            "publication_eligible": False,
            "runtime_route": "private_default_off",
            "route_calls": 0,
        }


__all__ = ["run_native_tri_quad_actual_mixed_bl_transaction"]
