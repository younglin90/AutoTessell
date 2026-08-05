"""Adapter for direct actual BRepFrontEvidence/v2 ingress."""

from __future__ import annotations

from typing import Any, Sequence

import numpy as np

from core.utils.native_extensions import import_native_extension


def validate_actual_brep_v2_ingress(
    canonical_positions: Any,
    evidence: dict[str, Any] | None,
    explicit_mapping: Sequence[dict[str, Any]] | None,
    requested_layers: int,
    source_digest: str,
    mapping_digest: str,
) -> dict[str, Any]:
    """Validate actual v2 evidence and explicit mapping without publication."""
    try:
        kernel = import_native_extension("native_surface_bl_front_actual_v2_ingress")
        return dict(
            kernel.validate_actual_brep_v2_ingress(
                np.ascontiguousarray(np.asarray(canonical_positions, dtype=np.float64)),
                {} if evidence is None else dict(evidence),
                [] if explicit_mapping is None else [dict(row) for row in explicit_mapping],
                int(requested_layers),
                str(source_digest),
                str(mapping_digest),
            )
        )
    except Exception as exc:  # noqa: BLE001
        return {
            "accepted": False,
            "status": "diagnostic_unavailable",
            "reason": f"native_surface_bl_front_actual_v2_ingress_unavailable:{type(exc).__name__}",
            "requested_layers": requested_layers,
            "actual_layers": 0,
            "runtime_route": "default_off",
            "publication_eligible": False,
        }


__all__ = ["validate_actual_brep_v2_ingress"]
