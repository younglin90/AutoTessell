"""Explicit Python-only dispatch for isolated fixed-pair strict-quad artifacts."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import numpy as np

from core.evaluator.surface_physical_group_provenance import (
    AuthoritativePhysicalGroupMapping,
)

from .strict_pair_product_l0 import strict_quad_fixed_pair_product_l0_enabled
from .strict_pair_transaction_l0 import (
    StrictQuadPairTransactionResult,
    materialize_strict_quad_pair_transaction_l0,
)
from .strict_quad_fixed_pair_writer_l0 import (
    StrictQuadFixedPairWriterResult,
    strict_quad_fixed_pair_writer_l0_enabled,
    write_strict_quad_fixed_pair_product_l0,
)


@dataclass(frozen=True, slots=True)
class AuthoritativeStrictQuadPatchIds:
    """Explicit source-face patch IDs; bare payloads are forbidden at dispatch."""

    payloads: tuple[int | str | None, ...]
    authoritative: bool


@dataclass(frozen=True, slots=True)
class StrictQuadFixedPairDispatchRequest:
    """Exact source evidence plus a fresh target for one offline strict product."""

    source_vertices: np.ndarray
    source_triangles: np.ndarray
    pair_plan: np.ndarray
    feature_edges: np.ndarray
    source_patch_ids: AuthoritativeStrictQuadPatchIds
    source_physical_groups: AuthoritativePhysicalGroupMapping
    target_directory: Path | str


@dataclass(frozen=True, slots=True)
class StrictQuadFixedPairDispatchResult:
    """Offline result; no success selects or claims a public product route."""

    accepted: bool
    status: str
    rejection_reason: str | None
    transaction_result: StrictQuadPairTransactionResult | None
    writer_result: StrictQuadFixedPairWriterResult | None
    artifact_path: Path | None
    artifact_written: bool
    route_selected: bool = False
    ui_claimed: bool = False
    product_claimed: bool = False
    contract: str = "strict_quad_fixed_pair_dispatch_l0"


def _authoritative_patches(
    value: object,
    source_count: int,
) -> tuple[int | str | None, ...] | None:
    if (
        not isinstance(value, AuthoritativeStrictQuadPatchIds)
        or not value.authoritative
        or len(value.payloads) != source_count
    ):
        return None
    return value.payloads


def dispatch_strict_quad_fixed_pair_product_l0(
    request: object,
) -> StrictQuadFixedPairDispatchResult:
    """Materialize strict quads first; write only after both explicit gates admit."""
    if not isinstance(request, StrictQuadFixedPairDispatchRequest):
        return StrictQuadFixedPairDispatchResult(
            False,
            "reject_strict_quad_fixed_pair_dispatch_request",
            "explicit_strict_quad_fixed_pair_dispatch_request_required",
            None,
            None,
            None,
            False,
        )
    patches = _authoritative_patches(request.source_patch_ids, len(request.source_triangles))
    if patches is None:
        return StrictQuadFixedPairDispatchResult(
            False,
            "reject_strict_quad_fixed_pair_dispatch_authority",
            "authoritative_source_patch_ids_required",
            None,
            None,
            None,
            False,
        )
    transaction_result = materialize_strict_quad_pair_transaction_l0(
        request.source_vertices,
        request.source_triangles,
        request.pair_plan,
        request.feature_edges,
        source_patch_ids=patches,
        source_physical_groups=request.source_physical_groups,
    )
    if not transaction_result.accepted or transaction_result.product_result is None:
        return StrictQuadFixedPairDispatchResult(
            False,
            transaction_result.status,
            transaction_result.rejection_reason,
            transaction_result,
            None,
            None,
            False,
        )
    if not (
        strict_quad_fixed_pair_product_l0_enabled() and strict_quad_fixed_pair_writer_l0_enabled()
    ):
        return StrictQuadFixedPairDispatchResult(
            True,
            "pass_strict_quad_fixed_pair_dispatch_unwritten",
            None,
            transaction_result,
            None,
            None,
            False,
        )
    writer_result = write_strict_quad_fixed_pair_product_l0(
        transaction_result.product_result,
        request.target_directory,
    )
    if not writer_result.written:
        return StrictQuadFixedPairDispatchResult(
            False,
            writer_result.status,
            writer_result.rejection_reason,
            transaction_result,
            writer_result,
            None,
            False,
        )
    return StrictQuadFixedPairDispatchResult(
        True,
        "pass_strict_quad_fixed_pair_dispatch_unrouted",
        None,
        transaction_result,
        writer_result,
        writer_result.artifact_path,
        True,
    )


__all__ = [
    "AuthoritativeStrictQuadPatchIds",
    "StrictQuadFixedPairDispatchRequest",
    "StrictQuadFixedPairDispatchResult",
    "dispatch_strict_quad_fixed_pair_product_l0",
]
