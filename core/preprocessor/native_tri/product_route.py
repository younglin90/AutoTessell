"""Explicit product boundary for the independent Native Tri surface route."""

from __future__ import annotations

import os
from collections.abc import Mapping
from pathlib import Path
from typing import Any

import numpy as np

from .release_route import NativeTriSourceAuthority, run_native_tri_release


def run_native_tri_surface_product(
    vertices: np.ndarray,
    faces: np.ndarray,
    *,
    target_edge_length: float,
    source_authority: NativeTriSourceAuthority | None,
    product: str = "native_tri_surface",
    explicit_route: bool = False,
    max_rounds: int = 1,
    source_path: str | Path | None = None,
    source_provenance: object | None = None,
    source_certificate: Mapping[str, object] | None = None,
) -> dict[str, Any]:
    """Call the independent Tri route only for its own explicit product."""
    if product != "native_tri_surface":
        return {
            "accepted": False, "status": "native_tri_product_refused",
            "reason": "product_boundary_mismatch", "product": product,
            "route_selected": False, "independent_route": False,
        }
    if not explicit_route:
        return {
            "accepted": False, "status": "native_tri_product_refused",
            "reason": "explicit_product_route_required", "product": product,
            "route_selected": False, "independent_route": False,
        }
    if os.environ.get("AUTO_TESSELL_NATIVE_TRI_RELEASE") != "1":
        return {
            "accepted": False, "status": "native_tri_product_refused",
            "reason": "native_tri_release_opt_in_missing", "product": product,
            "route_selected": False, "independent_route": False,
        }
    if source_authority is None:
        return {
            "accepted": False, "status": "native_tri_product_refused",
            "reason": "source_authority_missing", "product": product,
            "route_selected": False, "independent_route": False,
        }
    try:
        result = run_native_tri_release(
            vertices, faces, target_edge_length=target_edge_length,
            source_authority=source_authority, max_rounds=max_rounds,
            source_path=source_path, source_provenance=source_provenance,
            source_certificate=source_certificate,
        )
    except (OSError, RuntimeError, TypeError, ValueError) as exc:
        return {
            "accepted": False, "status": "native_tri_product_refused",
            "reason": f"native_tri_release_exception:{type(exc).__name__}",
            "product": product, "route_selected": True,
            "independent_route": False,
        }
    return {
        "accepted": bool(result.accepted),
        "status": result.status,
        "reason": result.reason,
        "product": product,
        "route_selected": True,
        "independent_route": bool(result.independent_route),
        "evidence": result.as_dict(),
        "vertices": result.vertices,
        "faces": result.faces,
    }


__all__ = ["run_native_tri_surface_product"]
