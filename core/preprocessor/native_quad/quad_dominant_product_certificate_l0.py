"""Fail-closed output diagnostic for the existing quad-dominant candidate.

``native_quad_dominant_remesh`` produces a local pair-merger result.  It now
emits exact local source-face partition facts, but not source shape, feature,
boundary, topology, physical-group, or source-certificate provenance evidence.
This adapter records those facts against the *actual* result and never upgrades
either ``quad`` or ``tri_quad`` into a product success.  It is
runtime-disconnected: no route, writer, or mesh mutation is performed here.
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
    accepted_face_pairs_hash: str | None
    remaining_triangle_source_indices_hash: str | None
    output_face_provenance_exact: bool
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


def _exact_output_face_provenance(
    source_faces: np.ndarray | None,
    output_triangles: np.ndarray | None,
    output_quads: np.ndarray | None,
    accepted_pairs: object,
    remaining_source_indices: object,
) -> bool:
    if (
        source_faces is None
        or output_triangles is None
        or output_quads is None
        or not isinstance(accepted_pairs, np.ndarray)
        or accepted_pairs.dtype != np.dtype(np.int64)
        or accepted_pairs.ndim != 2
        or accepted_pairs.shape[1] != 2
        or not accepted_pairs.flags.c_contiguous
        or not isinstance(remaining_source_indices, np.ndarray)
        or remaining_source_indices.dtype != np.dtype(np.int64)
        or remaining_source_indices.ndim != 1
        or not remaining_source_indices.flags.c_contiguous
    ):
        return False
    if len(accepted_pairs) != len(output_quads):
        return False
    if accepted_pairs.size and (
        (accepted_pairs < 0).any()
        or (accepted_pairs >= len(source_faces)).any()
        or (accepted_pairs[:, 0] >= accepted_pairs[:, 1]).any()
    ):
        return False
    if len(accepted_pairs) > 1:
        previous, current = accepted_pairs[:-1], accepted_pairs[1:]
        if (
            (current[:, 0] < previous[:, 0])
            | ((current[:, 0] == previous[:, 0]) & (current[:, 1] <= previous[:, 1]))
        ).any():
            return False
    consumed = np.zeros(len(source_faces), dtype=bool)
    if accepted_pairs.size:
        flattened = accepted_pairs.reshape(-1)
        if len(np.unique(flattened)) != len(flattened):
            return False
        consumed[flattened] = True
    expected_remaining = np.flatnonzero(~consumed).astype(np.int64, copy=False)
    if not np.array_equal(remaining_source_indices, expected_remaining):
        return False
    if not np.array_equal(output_triangles, source_faces[remaining_source_indices]):
        return False
    from core.preprocessor.native_remesh.quad_dominant import _oriented_quads_for_pairs

    try:
        expected_quads, _ = _oriented_quads_for_pairs(source_faces, accepted_pairs)
    except RuntimeError:
        return False
    return bool(np.array_equal(output_quads, expected_quads))


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
    accepted_pairs = result.accepted_face_pairs
    remaining_source_indices = result.remaining_triangle_source_indices
    output_face_provenance_exact = _exact_output_face_provenance(
        source_faces,
        output_triangles,
        output_quads,
        accepted_pairs,
        remaining_source_indices,
    )

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
        rejection_reason = (
            representation.rejection_reason
            or "quad_dominant_representation_rejected"
        )
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
        accepted_face_pairs_hash=_hash(
            accepted_pairs if isinstance(accepted_pairs, np.ndarray) else None
        ),
        remaining_triangle_source_indices_hash=_hash(
            remaining_source_indices if isinstance(remaining_source_indices, np.ndarray) else None
        ),
        output_face_provenance_exact=output_face_provenance_exact,
        missing_source_evidence=tuple(missing),
        source_certificate_complete=False,
        product_claimed=False,
    )


__all__ = [
    "QuadDominantProductCertificateL0",
    "diagnose_quad_dominant_product_output_l0",
]
