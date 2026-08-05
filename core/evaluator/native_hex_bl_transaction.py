"""Thin fail-closed adapter for the C++23 Native Hex private transaction."""
from __future__ import annotations
from typing import Any, Sequence
import numpy as np
from core.utils.native_extensions import import_native_extension

def _array(value: Any, width: int) -> np.ndarray:
    result=np.ascontiguousarray(np.asarray(value,dtype=np.int64))
    if result.size==0:return np.empty((0,width),dtype=np.int64)
    if result.ndim!=2 or result.shape[1]!=width:raise ValueError("native_hex_array_shape")
    return result

def evaluate_native_hex_bl_transaction(
    baseline_points: Any, baseline_cells: Any, baseline_boundary: Any,
    candidate_points: Any, candidate_cells: Any, candidate_boundary: Any,
    requested_layers: int, actual_layers: int,
    baseline_boundary_digest: str, candidate_boundary_digest: str,
    baseline_semantic_digest: str, candidate_semantic_digest: str,
    boundary_binding: Sequence[dict[str,Any]] | None,
    source_certificate: dict[str,Any] | None,
    authority: dict[str,Any] | None,
    quality_profile: dict[str,Any] | None,
    surface_witness: dict[str,Any] | None,
) -> dict[str,Any]:
    try:
        kernel=import_native_extension("native_hex_bl_transaction")
        bp=np.ascontiguousarray(np.asarray(baseline_points,dtype=np.float64));cp=np.ascontiguousarray(np.asarray(candidate_points,dtype=np.float64))
        if bp.ndim!=2 or bp.shape[1]!=3 or cp.ndim!=2 or cp.shape[1]!=3:raise ValueError("native_hex_points_shape")
        return dict(kernel.evaluate_native_hex_bl_transaction(
            bp,_array(baseline_cells,8),_array(baseline_boundary,4),cp,_array(candidate_cells,8),_array(candidate_boundary,4),
            int(requested_layers),int(actual_layers),str(baseline_boundary_digest),str(candidate_boundary_digest),
            str(baseline_semantic_digest),str(candidate_semantic_digest),
            None if boundary_binding is None else [dict(row) for row in boundary_binding],
            None if source_certificate is None else dict(source_certificate),
            None if authority is None else dict(authority),
            None if quality_profile is None else dict(quality_profile),
            None if surface_witness is None else dict(surface_witness),
        ))
    except Exception as exc: # noqa: BLE001
        return {"accepted":False,"status":"transaction_unavailable","reason":f"native_hex_bl_transaction_unavailable:{type(exc).__name__}","requested_layers":int(requested_layers),"actual_layers":0,"runtime_route":"default_off","publication_eligible":False,"route_calls":0,"candidate_discarded":True}

__all__=["evaluate_native_hex_bl_transaction"]
