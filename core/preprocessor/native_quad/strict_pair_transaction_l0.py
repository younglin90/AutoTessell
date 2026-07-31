"""Default-OFF strict all-pair triangle-to-quad transaction.

Unlike ``native_quad_dominant``, this transaction derives every output quad
from an explicit complete source-triangle pair plan, then delegates all hard
source boundary, feature, component/topology, patch, and provenance checks to
the fixed-pair preflight/materializer.
"""
from __future__ import annotations

from dataclasses import dataclass
import numpy as np

from .strict_pair_preflight import _oriented_quad
from .strict_pair_product_l0 import (
    StrictQuadFixedPairProductResult,
    materialize_strict_quad_fixed_pair_product_l0,
)

@dataclass(frozen=True, slots=True)
class StrictQuadPairTransactionResult:
    accepted: bool
    status: str
    rejection_reason: str | None
    transaction_applied: bool
    independent_product_ready: bool
    product_result: StrictQuadFixedPairProductResult | None

def materialize_strict_quad_pair_transaction_l0(
    source_vertices: np.ndarray,
    source_triangles: np.ndarray,
    pair_plan: np.ndarray,
    feature_edges: np.ndarray,
    *,
    source_patch_ids: object,
) -> StrictQuadPairTransactionResult:
    """Derive an all-quad candidate from a complete explicit pair plan."""
    if (
        not isinstance(pair_plan, np.ndarray) or pair_plan.dtype != np.dtype(np.int64)
        or pair_plan.ndim != 2 or pair_plan.shape[1] != 2 or not pair_plan.flags.c_contiguous
        or len(pair_plan) == 0 or len(source_triangles) != 2 * len(pair_plan)
    ):
        return StrictQuadPairTransactionResult(False, "reject_strict_quad_pair_plan", "strict_quad_pair_plan_invalid", False, False, None)
    quads: list[tuple[int, int, int, int]] = []
    for first, second in pair_plan.tolist():
        if first < 0 or second < 0 or first >= len(source_triangles) or second >= len(source_triangles):
            return StrictQuadPairTransactionResult(False, "reject_strict_quad_pair_plan", "strict_quad_pair_plan_invalid", False, False, None)
        quad = _oriented_quad(source_triangles[first], source_triangles[second])
        if quad is None:
            return StrictQuadPairTransactionResult(False, "reject_strict_quad_pair_plan", "strict_quad_pair_not_adjacent", False, False, None)
        quads.append(quad)
    source_patches = tuple(source_patch_ids) if isinstance(source_patch_ids, (tuple, list)) else ()
    quad_patches = [source_patches[int(pair[0])] if len(source_patches) > int(pair[0]) else None for pair in pair_plan]
    result = materialize_strict_quad_fixed_pair_product_l0(
        source_vertices, source_vertices.copy(), source_triangles,
        np.empty((0, 3), dtype=np.int64), np.asarray(quads, dtype=np.int64), pair_plan,
        feature_edges, source_patch_ids=source_patch_ids, candidate_quad_patch_ids=quad_patches,
    )
    return StrictQuadPairTransactionResult(
        result.accepted, result.status, result.rejection_reason, result.accepted,
        False, result,
    )
