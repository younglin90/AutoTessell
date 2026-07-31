"""Fail-closed Delaunay rebuild for real same-side internal-face debt.

The repair keeps every existing vertex coordinate.  It is therefore only an
admission candidate: the original mesh remains selected unless the rebuild
preserves the immutable source boundary and strictly reduces same-side faces
without worsening any audited validity debt.
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np


@dataclass(frozen=True, slots=True)
class SameSideRetriangulation:
    """Exact rollback transaction and its auditable admission evidence."""

    points: np.ndarray
    tets: np.ndarray
    accepted: bool
    reason: str
    before_same_side_internal_faces: int
    candidate_same_side_internal_faces: int
    before_ambiguous_internal_faces: int
    candidate_ambiguous_internal_faces: int
    before_inverted_tets: int
    candidate_inverted_tets: int
    source_component_bijective: bool
    source_faces_preserved: bool
    candidate_unowned_faces: int
    exact_rollback: bool


def retriangulate_if_strictly_safer(
    source_points: np.ndarray,
    source_faces: np.ndarray,
    before_points: np.ndarray,
    before_tets: np.ndarray,
) -> SameSideRetriangulation:
    """Rebuild connectivity only when strict source and validity debts improve.

    Qhull is used only to propose a connectivity candidate over unchanged
    coordinates.  It cannot move source geometry.  A non-convex or otherwise
    unconstrained candidate normally fails source-boundary ownership and is
    rolled back exactly; this is intentionally not a general CDT fallback.
    """
    from core.generator.native_tet.rescue_gate import (
        audit_source_component_bijection,
        audit_tet_boundary,
    )

    before_boundary = audit_tet_boundary(before_points, before_tets)
    before_source = audit_source_component_bijection(
        source_points,
        source_faces,
        before_points,
        before_tets,
    )

    def rejected(reason: str, candidate_boundary=None, candidate_source=None):
        boundary = candidate_boundary or before_boundary
        source = candidate_source or before_source
        return SameSideRetriangulation(
            points=before_points,
            tets=before_tets,
            accepted=False,
            reason=reason,
            before_same_side_internal_faces=int(
                before_boundary.n_same_side_internal_faces
            ),
            candidate_same_side_internal_faces=int(
                boundary.n_same_side_internal_faces
            ),
            before_ambiguous_internal_faces=int(
                before_boundary.n_ambiguous_internal_faces
            ),
            candidate_ambiguous_internal_faces=int(
                boundary.n_ambiguous_internal_faces
            ),
            before_inverted_tets=int(before_boundary.n_inverted_tets),
            candidate_inverted_tets=int(boundary.n_inverted_tets),
            source_component_bijective=bool(source.bijective),
            source_faces_preserved=bool(source.source_faces_preserved),
            candidate_unowned_faces=int(source.n_unowned_candidate_faces),
            exact_rollback=True,
        )

    if before_boundary.n_same_side_internal_faces == 0:
        return rejected("no_same_side_internal_face_debt")
    try:
        from scipy.spatial import Delaunay

        from core.generator.native_tet.stellar import validate_and_fix_orientations

        candidate_tets = np.ascontiguousarray(
            Delaunay(np.asarray(before_points, dtype=np.float64)).simplices,
            dtype=np.int64,
        )
        candidate_tets, _, _ = validate_and_fix_orientations(
            before_points,
            candidate_tets,
        )
    except Exception as exc:
        return rejected(f"delaunay_candidate_failed:{type(exc).__name__}")

    candidate_boundary = audit_tet_boundary(before_points, candidate_tets)
    candidate_source = audit_source_component_bijection(
        source_points,
        source_faces,
        before_points,
        candidate_tets,
    )
    accepted = bool(
        candidate_source.bijective
        and candidate_source.source_faces_preserved
        and candidate_source.n_unowned_candidate_faces == 0
        and candidate_boundary.n_open_edges
        <= before_boundary.n_open_edges
        and candidate_boundary.n_nonmanifold_edges
        <= before_boundary.n_nonmanifold_edges
        and candidate_boundary.n_nonmanifold_faces
        <= before_boundary.n_nonmanifold_faces
        and candidate_boundary.n_duplicate_tets
        <= before_boundary.n_duplicate_tets
        and candidate_boundary.n_degenerate_tets
        <= before_boundary.n_degenerate_tets
        and candidate_boundary.n_inverted_tets
        <= before_boundary.n_inverted_tets
        and candidate_boundary.n_ambiguous_internal_faces
        <= before_boundary.n_ambiguous_internal_faces
        and candidate_boundary.n_same_side_internal_faces
        < before_boundary.n_same_side_internal_faces
    )
    if not accepted:
        return rejected(
            "candidate_did_not_preserve_source_or_strictly_reduce_same_side",
            candidate_boundary,
            candidate_source,
        )
    return SameSideRetriangulation(
        points=before_points,
        tets=candidate_tets,
        accepted=True,
        reason="delaunay_connectivity_strictly_reduced_same_side",
        before_same_side_internal_faces=int(
            before_boundary.n_same_side_internal_faces
        ),
        candidate_same_side_internal_faces=int(
            candidate_boundary.n_same_side_internal_faces
        ),
        before_ambiguous_internal_faces=int(
            before_boundary.n_ambiguous_internal_faces
        ),
        candidate_ambiguous_internal_faces=int(
            candidate_boundary.n_ambiguous_internal_faces
        ),
        before_inverted_tets=int(before_boundary.n_inverted_tets),
        candidate_inverted_tets=int(candidate_boundary.n_inverted_tets),
        source_component_bijective=True,
        source_faces_preserved=True,
        candidate_unowned_faces=0,
        exact_rollback=False,
    )
