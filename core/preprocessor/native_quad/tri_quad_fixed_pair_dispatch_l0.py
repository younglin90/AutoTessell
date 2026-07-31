"""Explicit Python-only dispatch for the isolated fixed-pair tri+quad product.

This module deliberately has no CLI, plugin, pipeline, or UI registration.
Callers must supply exact source arrays plus authoritative source certificates;
the dispatcher cannot infer them or select a public surface route.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import numpy as np

from core.evaluator.surface_physical_group_provenance import (
    AuthoritativePhysicalGroupMapping,
)

from .tri_quad_fixed_pair_product_l0 import (
    AuthoritativeTriQuadFeatureEdges,
    AuthoritativeTriQuadPatchIds,
    TriQuadFixedPairProductResult,
    materialize_tri_quad_fixed_pair_product_l0,
    tri_quad_fixed_pair_product_l0_enabled,
)
from .tri_quad_fixed_pair_writer_l0 import (
    TriQuadFixedPairWriterResult,
    tri_quad_fixed_pair_writer_l0_enabled,
    write_tri_quad_fixed_pair_product_l0,
)


@dataclass(frozen=True, slots=True)
class TriQuadFixedPairDispatchRequest:
    """Exact source evidence and a fresh output target for one offline call."""

    source_vertices: np.ndarray
    source_triangles: np.ndarray
    pair_plan: np.ndarray
    feature_edges: AuthoritativeTriQuadFeatureEdges
    source_patch_ids: AuthoritativeTriQuadPatchIds
    source_physical_groups: AuthoritativePhysicalGroupMapping
    target_directory: Path | str


@dataclass(frozen=True, slots=True)
class TriQuadFixedPairDispatchResult:
    """Offline outcome; no successful result selects or claims a public route."""

    accepted: bool
    status: str
    rejection_reason: str | None
    product_result: TriQuadFixedPairProductResult | None
    writer_result: TriQuadFixedPairWriterResult | None
    artifact_path: Path | None
    artifact_written: bool
    route_selected: bool = False
    ui_claimed: bool = False
    product_claimed: bool = False
    contract: str = "tri_quad_fixed_pair_dispatch_l0"


def dispatch_tri_quad_fixed_pair_product_l0(
    request: object,
) -> TriQuadFixedPairDispatchResult:
    """Materialize, then atomically write only after both explicit gates admit it."""
    if not isinstance(request, TriQuadFixedPairDispatchRequest):
        return TriQuadFixedPairDispatchResult(
            False,
            "reject_tri_quad_fixed_pair_dispatch_request",
            "explicit_tri_quad_fixed_pair_dispatch_request_required",
            None,
            None,
            None,
            False,
        )

    product_result = materialize_tri_quad_fixed_pair_product_l0(
        request.source_vertices,
        request.source_triangles,
        request.pair_plan,
        request.feature_edges,
        source_patch_ids=request.source_patch_ids,
        source_physical_groups=request.source_physical_groups,
    )
    if not product_result.accepted:
        return TriQuadFixedPairDispatchResult(
            False,
            product_result.status,
            product_result.rejection_reason,
            product_result,
            None,
            None,
            False,
        )

    if not (tri_quad_fixed_pair_product_l0_enabled() and tri_quad_fixed_pair_writer_l0_enabled()):
        return TriQuadFixedPairDispatchResult(
            True,
            "pass_tri_quad_fixed_pair_dispatch_unwritten",
            None,
            product_result,
            None,
            None,
            False,
        )

    writer_result = write_tri_quad_fixed_pair_product_l0(
        product_result,
        request.target_directory,
    )
    if not writer_result.written:
        return TriQuadFixedPairDispatchResult(
            False,
            writer_result.status,
            writer_result.rejection_reason,
            product_result,
            writer_result,
            None,
            False,
        )
    return TriQuadFixedPairDispatchResult(
        True,
        "pass_tri_quad_fixed_pair_dispatch_unrouted",
        None,
        product_result,
        writer_result,
        writer_result.artifact_path,
        True,
    )


__all__ = [
    "TriQuadFixedPairDispatchRequest",
    "TriQuadFixedPairDispatchResult",
    "dispatch_tri_quad_fixed_pair_product_l0",
]
