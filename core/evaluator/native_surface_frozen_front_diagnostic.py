"""Fail-closed Python adapter for the C++23 frozen-front diagnostic."""

from __future__ import annotations

from typing import Any, Sequence

import numpy as np

from core.utils.native_extensions import import_native_extension


def _array(value: Any, dtype: Any, ndim: int, width: int | None = None) -> np.ndarray:
    result = np.ascontiguousarray(np.asarray(value, dtype=dtype))
    if result.ndim != ndim or (width is not None and result.shape[-1] != width):
        raise ValueError("frozen_front_array_shape")
    return result


def evaluate_frozen_front_diagnostic(
    source_points: Any,
    edges: Any,
    layer_points: Any,
    normals: Any,
    provenance: Sequence[dict[str, Any]],
    requested_layers: int,
    *,
    collision_witness: Sequence[dict[str, Any]] | None = None,
    geodesic_witness: Sequence[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Evaluate supplied front/quality witnesses without creating or publishing a mesh."""
    if requested_layers < 0:
        return {
            "accepted": False,
            "status": "refused_rollback",
            "reason": "negative_layer_count",
            "requested_layers": requested_layers,
            "actual_layers": 0,
            "runtime_route": "default_off",
            "publication_eligible": False,
        }
    if requested_layers == 0:
        return {
            "accepted": True,
            "status": "disabled_identity",
            "reason": "disabled_identity",
            "requested_layers": 0,
            "actual_layers": 0,
            "runtime_route": "default_off",
            "publication_eligible": False,
            "source_immutable": True,
        }
    points = _array(source_points, np.float64, 2, 3)
    edge_array = _array(edges, np.int64, 2, 4)
    layer_array = np.ascontiguousarray(np.asarray(layer_points, dtype=np.float64))
    normal_array = _array(normals, np.float64, 2, 3)
    if layer_array.ndim != 4 or layer_array.shape[2:] != (2, 3):
        raise ValueError("frozen_front_layer_shape")
    try:
        kernel = import_native_extension("native_surface_bl_quality")
        return dict(
            kernel.evaluate_frozen_front_diagnostic(
                points,
                edge_array,
                layer_array,
                normal_array,
                [dict(item) for item in provenance],
                int(requested_layers),
                None if collision_witness is None else [dict(item) for item in collision_witness],
                None if geodesic_witness is None else [dict(item) for item in geodesic_witness],
            )
        )
    except Exception as exc:  # noqa: BLE001
        return {
            "accepted": False,
            "status": "diagnostic_unavailable",
            "reason": f"native_frozen_front_diagnostic_unavailable:{type(exc).__name__}",
            "requested_layers": requested_layers,
            "actual_layers": 0,
            "runtime_route": "default_off",
            "publication_eligible": False,
            "source_immutable": True,
        }


__all__ = ["evaluate_frozen_front_diagnostic"]
