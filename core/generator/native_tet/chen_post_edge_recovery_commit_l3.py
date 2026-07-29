"""Atomic L3 Chen missing-facet precondition and recovered-face certificate.

This test-only composition requires a complete post-edge-recovery source
facet state, atomically stages every active parent replacement, and verifies
the resulting source facet as a two-owner conforming internal face complex.
It emits no production CDT mutation or writer output.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from fractions import Fraction

from core.generator.native_tet.chen_post_edge_recovery_facet_l2 import (
    ChenPostEdgeRecoveryFacetStateResult,
    certify_post_edge_recovery_facet_state_l2,
)
from core.generator.native_tet.chen_post_edge_recovery_state_l1 import (
    ChenPostEdgeRecoveryClusterelRecord,
)
from core.generator.native_tet.chen_source_triangle_conforming_faces_l3 import (
    ChenConformingSourceFaceResult,
    certify_conforming_source_triangle_faces_l3,
)
from core.generator.native_tet.chen_staged_state_l0 import _boundary_faces
from core.generator.native_tet.chen_subdivided_staged_state_l3 import (
    ChenSubdividedStagedCommitResult,
    certify_atomic_subdivided_boundary_replacement_l3,
)


@dataclass(frozen=True)
class ChenPostEdgeRecoveryCommitResult:
    """Complete source-facet certificate; no production candidate is committed."""

    accepted: bool
    reason: str
    before_state: ChenPostEdgeRecoveryFacetStateResult | None
    staging: ChenSubdividedStagedCommitResult | None
    after_faces: ChenConformingSourceFaceResult | None
    source_points_unchanged: bool
    production_mesh_changed: bool


def certify_post_edge_recovery_commit_l3(
    points: Sequence[Sequence[float | int | Fraction]],
    parent_tets: Sequence[Sequence[int]],
    source_vertex_indices: tuple[int, int, int],
    records: Sequence[ChenPostEdgeRecoveryClusterelRecord],
    candidate_children: Mapping[int, Sequence[Sequence[int]]],
) -> ChenPostEdgeRecoveryCommitResult:
    """Certify complete before state, atomic replacement, then recovered faces."""
    before = tuple(tuple(point) for point in points)
    state = certify_post_edge_recovery_facet_state_l2(
        points, parent_tets, source_vertex_indices, records
    )
    if not state.accepted:
        return ChenPostEdgeRecoveryCommitResult(
            False, f"before_state_failed:{state.reason}", state, None, None, before == tuple(tuple(point) for point in points), False
        )
    active_indices = tuple(index for index, _type in state.active_parent_types)
    active = {index: parent_tets[index] for index in active_indices}
    try:
        boundary = tuple(sorted(_boundary_faces(tuple(active.values()))))
    except ValueError:
        return ChenPostEdgeRecoveryCommitResult(
            False, "active_parent_boundary_failed", state, None, None, before == tuple(tuple(point) for point in points), False
        )
    staging = certify_atomic_subdivided_boundary_replacement_l3(
        points, active, boundary, candidate_children
    )
    if not staging.accepted:
        return ChenPostEdgeRecoveryCommitResult(
            False, f"staging_failed:{staging.reason}", state, staging, None, before == tuple(tuple(point) for point in points), False
        )
    untouched = tuple(tet for index, tet in enumerate(parent_tets) if index not in set(active_indices))
    after_tets = (*untouched, *(tet for _identifier, tet in staging.committed_tets))
    after = certify_conforming_source_triangle_faces_l3(points, after_tets, source_vertex_indices)
    unchanged = before == tuple(tuple(point) for point in points)
    return ChenPostEdgeRecoveryCommitResult(
        after.accepted and unchanged,
        "accepted" if after.accepted and unchanged else f"after_source_face_failed:{after.reason}",
        state,
        staging,
        after,
        unchanged,
        False,
    )
