"""Fail-closed adapter for the private C++23 feature-aware surface BL optimizer."""

from __future__ import annotations

from typing import Any, Sequence

import numpy as np

from core.utils.native_extensions import import_native_extension
from core.layers.native_bl_atomic_certificate import sha256


def _array(value: Any, dtype: Any, width: int) -> np.ndarray:
    result = np.ascontiguousarray(np.asarray(value, dtype=dtype))
    if result.ndim != 2 or result.shape[1] != width:
        raise ValueError("surface_bl_front_optimizer_array_shape")
    return result


def optimize_surface_wall_edge_front(
    points: Any,
    edges: Any,
    face_normals: Any,
    patch_names: Sequence[str],
    feature_names: Sequence[str],
    physical_groups: Sequence[str],
    requested_layers: int,
    first_height: float,
    growth_ratio: float,
    source_certificate: dict[str, Any] | None,
    edge_provenance: Sequence[dict[str, Any]] | None,
    *,
    max_step_halvings: int = 8,
    min_signed_area: float = 1.0e-14,
    max_metric_aspect_ratio: float = float("inf"),
    strict_quality: bool = False,
) -> dict[str, Any]:
    """Run only the private optimizer; it never publishes or routes a candidate."""
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
        kernel = import_native_extension("native_surface_bl_front_shared_optimizer")
        return dict(
            kernel.optimize_surface_wall_edge_front(
                _array(points, np.float64, 3),
                _array(edges, np.int64, 4),
                _array(face_normals, np.float64, 3),
                list(patch_names),
                list(feature_names),
                list(physical_groups),
                int(requested_layers),
                float(first_height),
                float(growth_ratio),
                None if source_certificate is None else dict(source_certificate),
                None if edge_provenance is None else [dict(item) for item in edge_provenance],
                int(max_step_halvings),
                float(min_signed_area),
                float(max_metric_aspect_ratio),
                bool(strict_quality),
            )
        )
    except Exception as exc:  # noqa: BLE001
        return {
            "accepted": False,
            "status": "diagnostic_unavailable",
            "reason": f"native_surface_bl_front_optimizer_unavailable:{type(exc).__name__}",
            "requested_layers": requested_layers,
            "actual_layers": 0,
            "runtime_route": "default_off",
            "publication_eligible": False,
        }




def optimize_surface_ridge_sector(
    points: Any,
    edges: Any,
    face_normals: Any,
    patch_names: Sequence[str],
    feature_names: Sequence[str],
    physical_groups: Sequence[str],
    requested_layers: int,
    first_height: float,
    growth_ratio: float,
    source_certificate: dict[str, Any] | None,
    edge_provenance: Sequence[dict[str, Any]] | None,
    *,
    strict_quality: bool = False,
) -> dict[str, Any]:
    """Run the C++ face-sector direct-strip producer; never publishes."""
    if requested_layers < 0:
        return {"accepted": False, "status": "refused_rollback",
                "reason": "negative_layer_count", "requested_layers": requested_layers,
                "actual_layers": 0, "runtime_route": "default_off",
                "publication_eligible": False, "candidate_discarded": True}
    try:
        kernel = import_native_extension("native_surface_bl_front_shared_optimizer")
        return dict(kernel.optimize_surface_ridge_sector(
            _array(points, np.float64, 3), _array(edges, np.int64, 4),
            _array(face_normals, np.float64, 3), list(patch_names),
            list(feature_names), list(physical_groups), int(requested_layers),
            float(first_height), float(growth_ratio),
            None if source_certificate is None else dict(source_certificate),
            None if edge_provenance is None else [dict(row) for row in edge_provenance],
            bool(strict_quality),
        ))
    except Exception as exc:  # noqa: BLE001
        return {"accepted": False, "status": "diagnostic_unavailable",
                "reason": f"native_surface_ridge_sector_unavailable:{type(exc).__name__}",
                "requested_layers": requested_layers, "actual_layers": 0,
                "runtime_route": "default_off", "publication_eligible": False,
                "candidate_discarded": True}

def propose_surface_wall_edge_target_field(
    points: Any,
    edges: Any,
    face_normals: Any,
    patch_names: Sequence[str],
    feature_names: Sequence[str],
    physical_groups: Sequence[str],
    clearance_caps: Any,
    requested_layers: int,
    first_height: float,
    growth_ratio: float,
    source_certificate: dict[str, Any] | None,
    edge_provenance: Sequence[dict[str, Any]] | None,
    *,
    max_metric_aspect: float = 10.0,
    max_height_skew: float = 0.50,
    triangle_conditioned_aspect_limit: float = 0.0,
    source_triangles: Any | None = None,
    curved_strip_frame_mode: bool = False,
    strict_quality: bool = False,
) -> dict[str, Any]:
    """Build a private target-field receipt; it never extrudes, routes, or publishes."""
    if requested_layers < 0:
        return {
            "accepted": False,
            "status": "refused_rollback",
            "reason": "negative_layer_count",
            "requested_layers": requested_layers,
            "actual_layers": 0,
            "target_vertices": [],
            "target_edges": [],
            "runtime_route": "default_off",
            "publication_eligible": False,
            "candidate_discarded": True,
        }
    try:
        caps = np.ascontiguousarray(
            np.asarray(
                np.empty(0, dtype=np.float64)
                if clearance_caps is None
                else clearance_caps,
                dtype=np.float64,
            )
        )
        if caps.ndim != 1:
            raise ValueError("target_field_clearance_shape")
        kernel = import_native_extension("native_surface_bl_front_shared_optimizer")
        triangle_array = (
            None if source_triangles is None else _array(source_triangles, np.int64, 3)
        )
        result = dict(
            kernel.propose_surface_wall_edge_target_field(
                _array(points, np.float64, 3),
                _array(edges, np.int64, 4),
                _array(face_normals, np.float64, 3),
                list(patch_names),
                list(feature_names),
                list(physical_groups),
                caps,
                int(requested_layers),
                float(first_height),
                float(growth_ratio),
                None if source_certificate is None else dict(source_certificate),
                None if edge_provenance is None else [dict(row) for row in edge_provenance],
                float(max_metric_aspect),
                float(max_height_skew),
                float(triangle_conditioned_aspect_limit),
                triangle_array,
                bool(curved_strip_frame_mode),
                bool(strict_quality),
            )
        )
        if curved_strip_frame_mode and bool(result.get("accepted", False)):
            if triangle_array is None:
                return {
                    "accepted": False,
                    "status": "refused_rollback",
                    "reason": "source_triangles_required_for_curved_frame",
                    "requested_layers": requested_layers,
                    "actual_layers": 0,
                    "target_vertices": [],
                    "target_edges": [],
                    "runtime_route": "default_off",
                    "publication_eligible": False,
                    "candidate_discarded": True,
                }
            result["source_triangle_digest"] = sha256(triangle_array.tolist())
            result["source_triangle_count"] = int(triangle_array.shape[0])
        return result
    except Exception as exc:  # noqa: BLE001
        return {
            "accepted": False,
            "status": "diagnostic_unavailable",
            "reason": f"native_surface_bl_front_target_field_unavailable:{type(exc).__name__}",
            "requested_layers": requested_layers,
            "actual_layers": 0,
            "target_vertices": [],
            "target_edges": [],
            "publication_eligible": False,
            "candidate_discarded": True,
        }



__all__ = [
    "optimize_surface_wall_edge_front",
    "optimize_surface_ridge_sector",
    "propose_surface_wall_edge_target_field",
]
