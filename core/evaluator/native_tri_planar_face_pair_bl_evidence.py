"""Evidence adapter for the private Native Tri planar face-pair BL card."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any


def summarize_native_tri_planar_face_pair_bl(
    result: Mapping[str, Any],
) -> dict[str, Any]:
    quality = result.get("quality")
    return {
        "accepted": bool(result.get("accepted", False)),
        "status": str(result.get("status", "")),
        "reason": str(result.get("reason", "")),
        "requested_layers": int(result.get("requested_layers", 0)),
        "actual_layers": int(result.get("actual_layers", 0)),
        "atomic_rollback": bool(result.get("atomic_rollback", False)),
        "artifact_emitted": bool(result.get("artifact_emitted", False)),
        "source_face_ids": list(result.get("source_face_ids", [])),
        "deterministic_digest": result.get("deterministic_digest"),
        "quality": dict(quality) if isinstance(quality, Mapping) else None,
        "topology": dict(result.get("topology", {})),
        "collision": dict(result.get("collision", {})),
        "quality_witness": list(result.get("quality_witness", [])),
    }


__all__ = ["summarize_native_tri_planar_face_pair_bl"]
