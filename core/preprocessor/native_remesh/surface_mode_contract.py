"""Fail-closed product labels for native surface-element representations.

This module is deliberately runtime-disconnected.  It records what an
already-produced surface representation proves; it neither selects an engine
nor converts, triangulates, or writes a mesh.  In particular, the existing
``native_quad_dominant`` pair merger is only a candidate ``tri_quad`` product.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from numbers import Integral


class SurfaceProductMode(StrEnum):
    """Canonical user-facing surface product semantics."""

    TRI = "tri"
    QUAD = "quad"
    TRI_QUAD = "tri_quad"


class SurfaceProductClassification(StrEnum):
    """Observed representation class, kept distinct from a requested product."""

    TRI_ONLY = "tri_only"
    STRICT_QUAD = "strict_quad"
    CANDIDATE_MIXED = "candidate_mixed"
    INVALID = "invalid"


_INTERNAL_MODE_ALIASES: dict[str, SurfaceProductMode] = {
    "native_tri_only": SurfaceProductMode.TRI,
    "native_quad_strict": SurfaceProductMode.QUAD,
    "native_tri_quad_mixed": SurfaceProductMode.TRI_QUAD,
}
_QUAD_DOMINANT_PRODUCER = "native_quad_dominant"


@dataclass(frozen=True, slots=True)
class SurfaceProductCertificate:
    """Read-only evidence for one canonical surface product request."""

    requested_mode: SurfaceProductMode | None
    classification: SurfaceProductClassification
    accepted: bool
    rejection_reason: str | None
    triangle_count: int | None
    quad_count: int | None
    separate_tri_quad_representation: bool
    triangular_handoff: bool
    producer: str
    contract: str = "native_surface_product_mode_l0"


def _normalise_mode(value: SurfaceProductMode | str) -> SurfaceProductMode | None:
    """Resolve canonical spellings and explicit internal aliases only."""
    if isinstance(value, SurfaceProductMode):
        return value
    if not isinstance(value, str):
        return None
    canonical = _INTERNAL_MODE_ALIASES.get(value, value)
    try:
        return SurfaceProductMode(canonical)
    except ValueError:
        return None


def _normalise_count(value: object) -> int | None:
    """Reject lossy, negative, and boolean element counts."""
    if isinstance(value, bool) or not isinstance(value, Integral):
        return None
    count = int(value)
    return count if count >= 0 else None


def _classify(
    *,
    triangle_count: int,
    quad_count: int,
    producer: str,
) -> SurfaceProductClassification:
    """Classify an explicit representation without changing it.

    ``native_quad_dominant`` is permanently classified as a mixed candidate,
    even when a particular fixture happens to leave no triangle remainder.
    It has no global pure-quad certificate.
    """
    if producer == _QUAD_DOMINANT_PRODUCER:
        return SurfaceProductClassification.CANDIDATE_MIXED
    if triangle_count > 0 and quad_count == 0:
        return SurfaceProductClassification.TRI_ONLY
    if triangle_count == 0 and quad_count > 0:
        return SurfaceProductClassification.STRICT_QUAD
    if triangle_count > 0 and quad_count > 0:
        return SurfaceProductClassification.CANDIDATE_MIXED
    return SurfaceProductClassification.INVALID


def certify_surface_product_mode(
    requested_mode: SurfaceProductMode | str,
    *,
    triangle_count: object,
    quad_count: object,
    separate_tri_quad_representation: bool,
    triangular_handoff: bool,
    producer: str = "unspecified",
) -> SurfaceProductCertificate:
    """Fail closed unless an existing representation proves its product label.

    ``tri_quad`` denotes a representation that retains separate triangle and
    quad arrays.  It may have zero triangle remainder on a particular input,
    but remains only a mixed *candidate* until a later product card supplies a
    strict global contract.  A triangular handoff is never strict quad output.
    """
    mode = _normalise_mode(requested_mode)
    triangles = _normalise_count(triangle_count)
    quads = _normalise_count(quad_count)
    if mode is None:
        return SurfaceProductCertificate(
            requested_mode=None,
            classification=SurfaceProductClassification.INVALID,
            accepted=False,
            rejection_reason="unknown_surface_product_mode",
            triangle_count=triangles,
            quad_count=quads,
            separate_tri_quad_representation=separate_tri_quad_representation,
            triangular_handoff=triangular_handoff,
            producer=producer,
        )
    if triangles is None or quads is None:
        return SurfaceProductCertificate(
            requested_mode=mode,
            classification=SurfaceProductClassification.INVALID,
            accepted=False,
            rejection_reason="surface_element_counts_invalid",
            triangle_count=triangles,
            quad_count=quads,
            separate_tri_quad_representation=separate_tri_quad_representation,
            triangular_handoff=triangular_handoff,
            producer=producer,
        )

    classification = _classify(
        triangle_count=triangles,
        quad_count=quads,
        producer=producer,
    )
    rejection_reason: str | None = None
    if mode is SurfaceProductMode.TRI:
        if classification is not SurfaceProductClassification.TRI_ONLY:
            rejection_reason = "representation_not_tri_only"
    elif mode is SurfaceProductMode.QUAD:
        if triangular_handoff:
            rejection_reason = "triangular_handoff_not_strict_quad"
        elif triangles != 0:
            rejection_reason = "triangles_not_allowed_in_strict_quad"
        elif classification is not SurfaceProductClassification.STRICT_QUAD:
            rejection_reason = "representation_not_strict_quad"
    else:
        if triangular_handoff:
            rejection_reason = "triangular_handoff_not_mixed_representation"
        elif not separate_tri_quad_representation:
            rejection_reason = "separate_tri_quad_representation_required"
        elif quads == 0:
            rejection_reason = "mixed_candidate_requires_quad"
        elif classification is not SurfaceProductClassification.CANDIDATE_MIXED:
            rejection_reason = "representation_not_mixed_candidate"

    return SurfaceProductCertificate(
        requested_mode=mode,
        classification=classification,
        accepted=rejection_reason is None,
        rejection_reason=rejection_reason,
        triangle_count=triangles,
        quad_count=quads,
        separate_tri_quad_representation=separate_tri_quad_representation,
        triangular_handoff=triangular_handoff,
        producer=producer,
    )
