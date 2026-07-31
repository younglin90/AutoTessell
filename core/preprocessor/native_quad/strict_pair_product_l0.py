"""Default-OFF materialization of an already-certified strict quad subset.

This module is runtime-disconnected.  It neither finds triangle pairs nor
selects a preprocessor route, writes a mesh, triangulates a quad, or falls
back to the mixed ``native_quad_dominant`` product.  A caller supplies the
entire fixed-vertex candidate and receives an in-memory product only after the
existing source/provenance preflight and the product-mode certificate agree.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from numbers import Integral

import numpy as np

from core.preprocessor.native_remesh.surface_mode_contract import (
    SurfaceProductCertificate,
    SurfaceProductClassification,
    SurfaceProductMode,
    certify_surface_product_mode,
)

from .strict_pair_preflight import (
    StrictQuadPairPreflight,
    diagnose_strict_quad_pair_preflight,
)

_ENV = "AUTO_TESSELL_STRICT_QUAD_FIXED_PAIR_PRODUCT_L0"
_PRODUCER = "native_strict_quad_fixed_pair_l0"


@dataclass(frozen=True, slots=True)
class StrictQuadFixedPairProduct:
    """Read-only, fixed-vertex strict-quad surface held only in memory."""

    vertices: np.ndarray
    triangles: np.ndarray
    quads: np.ndarray
    quad_patch_ids: tuple[int | str | None, ...]
    source_vertices_hash: str
    source_triangles_hash: str
    quads_hash: str
    contract: str = "strict_quad_fixed_pair_product_l0"


@dataclass(frozen=True, slots=True)
class StrictQuadFixedPairProductResult:
    """Explicit product admission result; rejection never returns a fallback."""

    accepted: bool
    status: str
    rejection_reason: str | None
    preflight: StrictQuadPairPreflight
    product_certificate: SurfaceProductCertificate | None
    product: StrictQuadFixedPairProduct | None


def strict_quad_fixed_pair_product_l0_enabled() -> bool:
    """Return whether the disconnected in-memory materializer is explicitly on."""
    return os.environ.get(_ENV) == "1"


def _readonly_copy(values: np.ndarray) -> np.ndarray:
    copied = np.ascontiguousarray(values).copy()
    copied.setflags(write=False)
    return copied


def _quad_patch_payloads(
    values: object,
    expected_count: int,
) -> tuple[int | str | None, ...] | None:
    """Normalize only the generic scalar payloads preflight already permits."""
    if not isinstance(values, (tuple, list)) or len(values) != expected_count:
        return None
    normalized: list[int | str | None] = []
    for value in values:
        scalar = value.item() if isinstance(value, np.generic) else value
        if isinstance(scalar, bool) or not isinstance(scalar, (Integral, str, type(None))):
            return None
        normalized.append(int(scalar) if isinstance(scalar, Integral) else scalar)
    return tuple(normalized)


def materialize_strict_quad_fixed_pair_product_l0(
    source_vertices: object,
    candidate_vertices: object,
    source_triangles: object,
    candidate_triangles: object,
    quads: object,
    pair_provenance: object,
    feature_edges: object,
    *,
    source_patch_ids: object,
    candidate_quad_patch_ids: object,
) -> StrictQuadFixedPairProductResult:
    """Materialize a strict quad product only after both certificates pass.

    This is deliberately not a producer: it accepts no implicit candidate,
    performs no pair selection, and returns ``product=None`` on every failed
    precondition.  The source arrays are copied only after certification and
    become read-only, so the returned surface cannot silently become a
    triangular handoff or a mutable replacement of the source.
    """
    preflight = diagnose_strict_quad_pair_preflight(
        source_vertices,
        candidate_vertices,
        source_triangles,
        candidate_triangles,
        quads,
        pair_provenance,
        feature_edges,
        source_patch_ids=source_patch_ids,
        candidate_quad_patch_ids=candidate_quad_patch_ids,
    )
    if not preflight.accepted:
        return StrictQuadFixedPairProductResult(
            False,
            "reject_strict_quad_fixed_pair_preflight",
            "strict_quad_pair_preflight_rejected",
            preflight,
            None,
            None,
        )

    certificate = certify_surface_product_mode(
        SurfaceProductMode.QUAD,
        triangle_count=0,
        quad_count=len(quads),
        separate_tri_quad_representation=False,
        triangular_handoff=False,
        producer=_PRODUCER,
    )
    if (
        not certificate.accepted
        or certificate.classification is not SurfaceProductClassification.STRICT_QUAD
    ):
        return StrictQuadFixedPairProductResult(
            False,
            "reject_strict_quad_fixed_pair_mode",
            certificate.rejection_reason or "strict_quad_product_certificate_rejected",
            preflight,
            certificate,
            None,
        )
    if not strict_quad_fixed_pair_product_l0_enabled():
        return StrictQuadFixedPairProductResult(
            False,
            "reject_strict_quad_fixed_pair_product_disabled",
            "strict_quad_fixed_pair_product_l0_disabled",
            preflight,
            certificate,
            None,
        )

    # The preflight's payload proof applies to the exact candidate payload.
    # Re-normalize before retaining it so the materialized object is immutable
    # and has no mutable caller-owned list alias.
    payloads = _quad_patch_payloads(candidate_quad_patch_ids, len(quads))
    if payloads is None:
        return StrictQuadFixedPairProductResult(
            False,
            "reject_strict_quad_fixed_pair_patch_payload",
            "strict_quad_fixed_pair_patch_payload_invalid",
            preflight,
            certificate,
            None,
        )
    if (
        preflight.source_vertices_hash is None
        or preflight.source_triangles_hash is None
        or preflight.quads_hash is None
    ):
        return StrictQuadFixedPairProductResult(
            False,
            "reject_strict_quad_fixed_pair_evidence",
            "strict_quad_fixed_pair_evidence_missing",
            preflight,
            certificate,
            None,
        )

    product = StrictQuadFixedPairProduct(
        vertices=_readonly_copy(np.asarray(source_vertices, dtype=np.float64)),
        triangles=_readonly_copy(np.empty((0, 3), dtype=np.int64)),
        quads=_readonly_copy(np.asarray(quads, dtype=np.int64)),
        quad_patch_ids=payloads,
        source_vertices_hash=preflight.source_vertices_hash,
        source_triangles_hash=preflight.source_triangles_hash,
        quads_hash=preflight.quads_hash,
    )
    return StrictQuadFixedPairProductResult(
        True,
        "pass_strict_quad_fixed_pair_product",
        None,
        preflight,
        certificate,
        product,
    )


__all__ = [
    "StrictQuadFixedPairProduct",
    "StrictQuadFixedPairProductResult",
    "materialize_strict_quad_fixed_pair_product_l0",
    "strict_quad_fixed_pair_product_l0_enabled",
]
