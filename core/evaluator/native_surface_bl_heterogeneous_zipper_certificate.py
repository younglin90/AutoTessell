"""Fail-closed adapter for the C++23 heterogeneous surface-BL certificate.

The certificate recognizes only the proven C116 regular-hex 2-to-1 zipper.
It never emits faces or promotes a runtime route; unsupported transitions are
returned as an atomic empty artifact.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

import numpy as np

from core.utils.native_extensions import import_native_extension


def _array(value: Any, dtype: Any, ndim: int, width: int | None = None) -> np.ndarray:
    result = np.ascontiguousarray(np.asarray(value, dtype=dtype))
    if result.ndim != ndim or (width is not None and result.shape[-1] != width):
        raise ValueError("heterogeneous_zipper_array_shape")
    return result


def _refusal(reason: str) -> dict[str, Any]:
    return {
        "accepted": False,
        "status": "heterogeneous_zipper_template_refused",
        "reason": reason,
        "candidate_discarded": True,
        "artifact_emitted": False,
        "publication_eligible": False,
        "runtime_route": "private_default_off",
        "actual_layers": 0,
        "generated_vertices": [],
        "generated_faces": [],
        "provenance": [],
        "output_digest": "",
        "canonical_contract_key": "",
    }


def validate_regular_hex_certificate(
    points: Any,
    source_triangles: Any,
    edges: Any,
    front_points: Any,
    front_vertex_ids: Sequence[int],
    count_ledger: Sequence[Mapping[str, Any]],
    interval_ledger: Sequence[Mapping[str, Any]],
    midpoint_lineage: Sequence[Mapping[str, Any]],
    authority: Mapping[str, Any],
    provenance: Sequence[Mapping[str, Any]],
    template_id: str = "regular_hex_outer2_inner1_zipper_v1",
    chain_id: str = "regular_hex_zipper_chain_v1",
    requested_layers: int = 1,
) -> dict[str, Any]:
    """Validate one analytic certificate; no mesh artifact is generated."""

    try:
        kernel = import_native_extension(
            "native_surface_bl_heterogeneous_zipper_certificate"
        )
        return dict(
            kernel.validate_regular_hex_certificate(
                _array(points, np.float64, 2, 3),
                _array(source_triangles, np.int64, 2, 3),
                _array(edges, np.int64, 2, 4),
                _array(front_points, np.float64, 2, 3),
                [int(value) for value in front_vertex_ids],
                [dict(row) for row in count_ledger],
                [dict(row) for row in interval_ledger],
                [dict(row) for row in midpoint_lineage],
                dict(authority),
                [dict(row) for row in provenance],
                str(template_id),
                str(chain_id),
                int(requested_layers),
            )
        )
    except Exception as exc:  # noqa: BLE001
        return _refusal(f"native_heterogeneous_zipper_unavailable:{type(exc).__name__}")


def validate_bl0_identity(
    source_digest: str,
    output_digest: str,
    authority: Mapping[str, Any],
    requested_layers: int = 0,
) -> dict[str, Any]:
    """Validate the disabled-layer identity without invoking a writer."""

    try:
        kernel = import_native_extension(
            "native_surface_bl_heterogeneous_zipper_certificate"
        )
        return dict(
            kernel.validate_bl0_identity(
                str(source_digest),
                str(output_digest),
                dict(authority),
                int(requested_layers),
            )
        )
    except Exception as exc:  # noqa: BLE001
        return _refusal(f"native_heterogeneous_zipper_unavailable:{type(exc).__name__}")


__all__ = ["validate_regular_hex_certificate", "validate_bl0_identity"]
