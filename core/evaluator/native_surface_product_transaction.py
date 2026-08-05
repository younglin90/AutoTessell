"""Thin fail-closed adapter for the C++23 surface-product private validator."""
from __future__ import annotations
from typing import Any, Sequence
import numpy as np
from core.utils.native_extensions import import_native_extension

def _array(value: Any, width: int) -> np.ndarray:
    result=np.ascontiguousarray(np.asarray(value,dtype=np.int64))
    if result.size == 0: return np.empty((0,width),dtype=np.int64)
    if result.ndim!=2 or result.shape[1]!=width: raise ValueError("surface_product_array_shape")
    return result

def evaluate_surface_product_transaction(
    kind: str, source_points: Any, source_triangles: Any, source_quads: Any,
    candidate_points: Any, candidate_triangles: Any, candidate_quads: Any,
    requested_layers: int, actual_layers: int, source_certificate: dict[str,Any] | None,
    authority: dict[str,Any] | None, quality_profile: dict[str,Any] | None,
    surface_witness: dict[str,Any] | None, lineage: Sequence[dict[str,Any]],
) -> dict[str,Any]:
    try:
        kernel=import_native_extension("native_surface_product_transaction")
        points_source=np.ascontiguousarray(np.asarray(source_points,dtype=np.float64))
        points_candidate=np.ascontiguousarray(np.asarray(candidate_points,dtype=np.float64))
        if points_source.ndim!=2 or points_source.shape[1]!=3 or points_candidate.ndim!=2 or points_candidate.shape[1]!=3: raise ValueError("surface_product_points_shape")
        return dict(kernel.evaluate_surface_product_transaction(
            str(kind),points_source,_array(source_triangles,3),_array(source_quads,4),
            points_candidate,_array(candidate_triangles,3),_array(candidate_quads,4),
            int(requested_layers),int(actual_layers),
            None if source_certificate is None else dict(source_certificate),
            None if authority is None else dict(authority),
            None if quality_profile is None else dict(quality_profile),
            None if surface_witness is None else dict(surface_witness),
            [dict(row) for row in lineage],
        ))
    except Exception as exc: # noqa: BLE001
        return {"accepted":False,"status":"transaction_unavailable","reason":f"native_surface_product_transaction_unavailable:{type(exc).__name__}","requested_layers":int(requested_layers),"actual_layers":0,"runtime_route":"default_off","publication_eligible":False,"route_calls":0,"candidate_discarded":True}

__all__=["evaluate_surface_product_transaction"]
