"""Fail-closed adapter for the private C++23 B-Rep authority bridge."""

from __future__ import annotations

from typing import Any, Sequence

import numpy as np

from core.utils.native_extensions import import_native_extension


def _array(value: Any, dtype: Any, width: int) -> np.ndarray:
    result = np.ascontiguousarray(np.asarray(value, dtype=dtype))
    if result.ndim != 2 or result.shape[1] != width:
        raise ValueError("surface_bl_authority_array_shape")
    return result


def bridge_authoritative_surface_wall_edge(
    points: Any,
    edges: Any,
    face_normals: Any,
    requested_layers: int,
    evidence: dict[str, Any] | None,
    direction_records: Sequence[dict[str, Any]] | None,
    explicit_mapping: Sequence[dict[str, Any]] | None,
    digests: dict[str, Any] | None,
) -> dict[str, Any]:
    """Validate typed B-Rep evidence and explicit mapping without publishing."""
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
    try:
        kernel = import_native_extension("native_surface_bl_front_authority_bridge")
        return dict(
            kernel.bridge_authoritative_surface_wall_edge(
                _array(points, np.float64, 3),
                _array(edges, np.int64, 4),
                _array(face_normals, np.float64, 3),
                int(requested_layers),
                {} if evidence is None else dict(evidence),
                [] if direction_records is None else [dict(row) for row in direction_records],
                [] if explicit_mapping is None else [dict(row) for row in explicit_mapping],
                {} if digests is None else dict(digests),
            )
        )
    except Exception as exc:  # noqa: BLE001
        return {
            "accepted": False,
            "status": "diagnostic_unavailable",
            "reason": f"native_surface_bl_authority_bridge_unavailable:{type(exc).__name__}",
            "requested_layers": requested_layers,
            "actual_layers": 0,
            "runtime_route": "default_off",
            "publication_eligible": False,
        }


__all__ = ["bridge_authoritative_surface_wall_edge"]
