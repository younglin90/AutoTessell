"""Evidence adapter for the private C124 Native Tri box/NACA quality card."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any


def summarize_native_tri_authority_bound_diagonal_front_cdt(
    result: Mapping[str, Any],
) -> dict[str, Any]:
    quality = result.get("quality")
    return {
        "accepted": bool(result.get("accepted", False)),
        "status": str(result.get("status", "")),
        "reason": str(result.get("reason", "")),
        "requested_layers": int(result.get("requested_layers", 0)),
        "actual_layers": int(result.get("actual_layers", 0)),
        "lattice_quantum": result.get("lattice_quantum"),
        "metric_front_segments": result.get("metric_front_segments"),
        "pair_ring_face_counts": result.get("pair_ring_face_counts"),
        "pair_core_face_count": result.get("pair_core_face_count"),
        "support_refined_face_count": result.get("support_refined_face_count"),
        "tangential_segments_per_patch_axis": result.get(
            "tangential_segments_per_patch_axis"
        ),
        "nominal_face_count": result.get("nominal_face_count"),
        "actual_face_count": result.get("actual_face_count"),
        "face_count_delta": result.get("face_count_delta"),
        "atomic_rollback": bool(result.get("atomic_rollback", False)),
        "artifact_emitted": bool(result.get("artifact_emitted", False)),
        "quality": dict(quality) if isinstance(quality, Mapping) else None,
        "topology": dict(result.get("topology", {})),
        "collision": dict(result.get("collision", {})),
        "worst_face_vertices": result.get("worst_face_vertices"),
    }


# Keep the explicit BL suffix for callers that distinguish the writer evidence from admission evidence.
summarize_native_tri_authority_bound_diagonal_front_cdt_bl = (
    summarize_native_tri_authority_bound_diagonal_front_cdt
)


def summarize_native_tri_curved_naca_admission(
    result: Mapping[str, Any],
) -> dict[str, Any]:
    return {
        "accepted": bool(result.get("accepted", False)),
        "status": str(result.get("status", "")),
        "reason": str(result.get("reason", "")),
        "requested_layers": int(result.get("requested_layers", 0)),
        "actual_layers": int(result.get("actual_layers", 0)),
        "layer_heights": list(result.get("layer_heights", [])),
        "requested_cumulative_height": result.get("requested_cumulative_height"),
        "source_raw_aspect_p95": result.get("source_raw_aspect_p95"),
        "source_raw_aspect_max": result.get("source_raw_aspect_max"),
        "source_mean_ratio_min": result.get("source_mean_ratio_min"),
        "curved_projection_authority": bool(
            result.get("curved_projection_authority", False)
        ),
        "artifact_emitted": bool(result.get("artifact_emitted", False)),
        "atomic_rollback": bool(result.get("atomic_rollback", False)),
    }


__all__ = [
    "summarize_native_tri_authority_bound_diagonal_front_cdt",
    "summarize_native_tri_authority_bound_diagonal_front_cdt_bl",
    "summarize_native_tri_curved_naca_admission",
]
