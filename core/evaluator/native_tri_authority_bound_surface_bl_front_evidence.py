"""Evidence adapter for the private C125 Native Tri non-box surface front."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any


def summarize_native_tri_authority_bound_surface_bl_front(
    result: Mapping[str, Any],
) -> dict[str, Any]:
    quality = result.get("quality")
    return {
        "accepted": bool(result.get("accepted", False)),
        "status": str(result.get("status", "")),
        "reason": str(result.get("reason", "")),
        "requested_layers": int(result.get("requested_layers", 0)),
        "actual_layers": int(result.get("actual_layers", 0)),
        "layer_heights": list(result.get("layer_heights", [])),
        "cumulative_height": result.get("cumulative_height"),
        "source_face_count": result.get("source_face_count"),
        "source_face_coverage_complete": bool(
            result.get("source_face_coverage_complete", False)
        ),
        "metric_front_segments": result.get("metric_front_segments"),
        "nominal_face_count": result.get("nominal_face_count"),
        "actual_face_count": result.get("actual_face_count"),
        "face_count_delta": result.get("face_count_delta"),
        "deterministic_digest": result.get("deterministic_digest"),
        "source_certificate_sha256": result.get("source_certificate_sha256"),
        "edge_ledger_sha256": result.get("edge_ledger_sha256"),
        "template_id": result.get("template_id"),
        "wall_edge_ids": list(result.get("wall_edge_ids", [])),
        "active_sector_face_ids": list(result.get("active_sector_face_ids", [])),
        "bl0_identity": bool(result.get("bl0_identity", False)),
        "artifact_emitted": bool(result.get("artifact_emitted", False)),
        "atomic_rollback": bool(result.get("atomic_rollback", False)),
        "quality": dict(quality) if isinstance(quality, Mapping) else None,
        "topology": dict(result.get("topology", {})),
        "collision": dict(result.get("collision", {})),
        "projection_witness_count": sum(
            len(row.get("projection_witness", []))
            for row in result.get("generated_vertices", [])
            if isinstance(row, Mapping)
        ),
        "provenance_count": len(result.get("provenance", [])),
    }


summarize_native_tri_authority_bound_surface_bl_front_bl = (
    summarize_native_tri_authority_bound_surface_bl_front
)


__all__ = [
    "summarize_native_tri_authority_bound_surface_bl_front",
    "summarize_native_tri_authority_bound_surface_bl_front_bl",
]
