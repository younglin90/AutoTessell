"""Evidence adapter for the private conforming cube-lattice Native Tri BL card."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any


def summarize_native_tri_authoritative_cube_lattice_bl(
    result: Mapping[str, Any],
) -> dict[str, Any]:
    quality = result.get("quality")
    return {
        "accepted": bool(result.get("accepted", False)),
        "status": str(result.get("status", "")),
        "reason": str(result.get("reason", "")),
        "requested_layers": int(result.get("requested_layers", 0)),
        "actual_layers": int(result.get("actual_layers", 0)),
        "lattice_N": int(result.get("lattice_N", 0)),
        "lattice_quantum": result.get("lattice_quantum"),
        "deterministic_digest": result.get("deterministic_digest"),
        "atomic_rollback": bool(result.get("atomic_rollback", False)),
        "artifact_emitted": bool(result.get("artifact_emitted", False)),
        "pair_ring_face_counts": list(result.get("pair_ring_face_counts", [])),
        "pair_core_face_count": int(result.get("pair_core_face_count", 0)),
        "quality": dict(quality) if isinstance(quality, Mapping) else None,
        "topology": dict(result.get("topology", {})),
        "collision": dict(result.get("collision", {})),
    }


__all__ = ["summarize_native_tri_authoritative_cube_lattice_bl"]
