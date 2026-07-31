"""Fail-closed output diagnostic for the existing quad-dominant candidate.

``native_quad_dominant_remesh`` produces a local pair-merger result.  It does
not emit source shape, feature, boundary, topology, physical-group, or face
provenance evidence.  This adapter records that fact against the *actual*
result and never upgrades either ``quad`` or ``tri_quad`` into a product
success.  It is runtime-disconnected: no route, writer, or mesh mutation is
performed here.
"""

from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256

import numpy as np

from core.preprocessor.native_remesh.quad_dominant import QuadDominantResult
from core.preprocessor.native_remesh.surface_mode_contract import (
    SurfaceProductCertificate,
    SurfaceProductMode,
    certify_surface_product_mode,
)

_PRODUCER = "native_quad_dominant"
_REQUIRED_SOURCE_EVIDENCE = (
    "source_shape",
    "feature",
    "boundary",
    "topology",
    "physical_group",
    "provenance",
)


@dataclass(frozen=True, slots=True)
class QuadDominantProductCertificateL0:
    """Evidence gap for one actual quad-dominant output; never acceptance."""

    requested_mode: SurfaceProductMode | None
    representation_certificate: SurfaceProductCertificate
    accepted: bool
    status: str
    rejection_reason: str
    source_vertices_exact: bool
    source_vertices_hash: str | None
    source_triangles_hash: str | None
    output_vertices_hash: str | None
    output_triangles_hash: str | None
    output_quads_hash: str | None
    missing_source_evidence: tuple[str, ...]
    source_certificate_complete: bool
    product_claimed: bool
    contract: str = "native_quad_dominant_output_certificate_l0"


def _canonical_array(
    value: object,
    *,
    dtype: np.dtype[np.float64] | np.dtype[np.int64],
    columns: int,
) -> np.ndarray | None:
    if (
        not isinstance(value, np.ndarray)
        or value.dtype != dtype
        or value.ndim != 2
        or value.shape[1] != columns
        or not value.flags.c_contiguous
    ):
        return None
    return value


def _hash(array: np.ndarray | None) -> str | None:
    if array is None:
        return None
    digest = sha256()
    digest.update(str(array.dtype).encode("ascii"))
    digest.update(np.asarray(array.shape, dtype=np.int64).tobytes())
    digest.update(array.tobytes())
    return digest.hexdigest()


def diagnose_quad_dominant_product_output_l0(
    source_vertices: object,
    source_triangles: object,
    result: QuadDominantResult,
    *,
    requested_mode: SurfaceProductMode | str,
) -> QuadDominantProductCertificateL0:
    """Record why one actual candidate cannot be a released surface product.

    The only source fact this adapter can check is byte-exact output vertices.
    The five remaining hard gates have no mesher-emitted proof, so
    ``accepted`` and ``product_claimed`` are always false.  A future producer
    must bind these facts to an immutable source certificate before this API
    can be replaced by an accepting product contract.
    """
    if not isinstance(result, QuadDominantResult):
        raise TypeError("result must be QuadDominantResult")

    source_points = _canonical_array(source_vertices, dtype=np.dtype(np.float64), columns=3)
    source_faces = _canonical_array(source_triangles, dtype=np.dtype(np.int64), columns=3)
    output_points = _canonical_array(result.vertices, dtype=np.dtype(np.float64), columns=3)
    output_triangles = _canonical_array(result.triangles, dtype=np.dtype(np.int64), columns=3)
    output_quads = _canonical_array(result.quads, dtype=np.dtype(np.int64), columns=4)

    triangle_count = -1 if output_triangles is None else len(output_triangles)
    quad_count = -1 if output_quads is None else len(output_quads)
    representation = certify_surface_product_mode(
        requested_mode,
        triangle_count=triangle_count,
        quad_count=quad_count,
        separate_tri_quad_representation=output_triangles is not None and output_quads is not None,
        triangular_handoff=False,
        producer=_PRODUCER,
    )
    source_vertices_exact = bool(
        source_points is not None
        and output_points is not None
        and source_points.shape == output_points.shape
        and source_points.tobytes() == output_points.tobytes()
    )
    missing = list(_REQUIRED_SOURCE_EVIDENCE)
    if source_vertices_exact:
        missing.remove("source_shape")

    if not representation.accepted:
        status = "reject_quad_dominant_representation"
        rejection_reason = representation.rejection_reason or "quad_dominant_representation_rejected"
    elif not source_vertices_exact:
        status = "reject_quad_dominant_source_shape"
        rejection_reason = "quad_dominant_source_vertices_not_exact"
    else:
        status = "reject_quad_dominant_source_certificate_required"
        rejection_reason = "quad_dominant_source_certificate_required"

    return QuadDominantProductCertificateL0(
        requested_mode=representation.requested_mode,
        representation_certificate=representation,
        accepted=False,
        status=status,
        rejection_reason=rejection_reason,
        source_vertices_exact=source_vertices_exact,
        source_vertices_hash=_hash(source_points),
        source_triangles_hash=_hash(source_faces),
        output_vertices_hash=_hash(output_points),
        output_triangles_hash=_hash(output_triangles),
        output_quads_hash=_hash(output_quads),
        missing_source_evidence=tuple(missing),
        source_certificate_complete=False,
        product_claimed=False,
    )


__all__ = [
    "QuadDominantProductCertificateL0",
    "diagnose_quad_dominant_product_output_l0",
]
