"""Thin fail-closed adapter for the private-stage Native Tet BL validator."""
from __future__ import annotations
from typing import Any, Sequence
import numpy as np
from core.utils.native_extensions import import_native_extension

def _array(value: Any, dtype: Any, width: int) -> np.ndarray:
    result = np.ascontiguousarray(np.asarray(value, dtype=dtype))
    if result.ndim != 2 or result.shape[1] != width:
        raise ValueError("native_tet_bl_transaction_array_shape")
    return result

def evaluate_native_tet_bl_transaction(
    baseline_points: Any,
    baseline_tets: Any,
    candidate_points: Any,
    candidate_tets: Any,
    requested_layers: int,
    actual_layers: int,
    baseline_boundary_digest: str,
    candidate_boundary_digest: str,
    baseline_semantic_digest: str,
    candidate_semantic_digest: str,
    lineage: Sequence[dict[str, Any]],
    surface_witness: dict[str, Any] | None,
    authority_capsule: dict[str, Any] | None,
    quality_profile: dict[str, Any] | None,
    stable_core_indices: Sequence[int] | None = None,
) -> dict[str, Any]:
    try:
        kernel = import_native_extension("native_tet_bl_transaction")
        return dict(kernel.evaluate_native_tet_bl_transaction(
            _array(baseline_points, np.float64, 3),
            _array(baseline_tets, np.int64, 4),
            _array(candidate_points, np.float64, 3),
            _array(candidate_tets, np.int64, 4),
            int(requested_layers), int(actual_layers),
            str(baseline_boundary_digest), str(candidate_boundary_digest),
            str(baseline_semantic_digest), str(candidate_semantic_digest),
            [dict(row) for row in lineage],
            None if surface_witness is None else dict(surface_witness),
            None if authority_capsule is None else dict(authority_capsule),
            None if quality_profile is None else dict(quality_profile),
            None if stable_core_indices is None else [int(index) for index in stable_core_indices],
        ))
    except Exception as exc:  # noqa: BLE001
        return {
            "accepted": False,
            "status": "transaction_unavailable",
            "reason": f"native_tet_bl_transaction_unavailable:{type(exc).__name__}",
            "requested_layers": int(requested_layers),
            "actual_layers": 0,
            "runtime_route": "default_off",
            "publication_eligible": False,
            "route_calls": 0,
            "candidate_discarded": True,
        }

__all__ = ["evaluate_native_tet_bl_transaction"]
