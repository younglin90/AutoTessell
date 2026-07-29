"""Atomic before/after exact source-triangle coverage certificate.

This test-only L3 layer combines two independent requirements: a candidate
must first pass the existing full-cavity positive-volume/exterior-subdivision
staging contract, then the whole mesh's exact source-triangle coverage before
and after that replacement must both pass.  It does not choose a Chen row or
write any production CDT state.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from fractions import Fraction

from core.generator.native_tet.chen_penetration_l0 import _point
from core.generator.native_tet.chen_source_triangle_coverage_l2 import (
    ChenSourceTriangleCoverageResult,
    certify_source_triangle_coverage_l2,
)
from core.generator.native_tet.chen_staged_state_l0 import _boundary_faces
from core.generator.native_tet.chen_subdivided_staged_state_l3 import (
    ChenSubdividedStagedCommitResult,
    certify_atomic_subdivided_boundary_replacement_l3,
)


@dataclass(frozen=True)
class ChenSourceTriangleReplacementCoverageResult:
    """Atomic report-only comparison against one immutable source triangle."""

    accepted: bool
    reason: str
    staging: ChenSubdividedStagedCommitResult | None
    before_coverage: ChenSourceTriangleCoverageResult | None
    after_coverage: ChenSourceTriangleCoverageResult | None
    source_points_unchanged: bool
    production_mesh_changed: bool


def certify_source_triangle_replacement_coverage_l3(
    points: Sequence[Sequence[float | int | Fraction]],
    parent_tets: Sequence[Sequence[int]],
    source_triangle: Sequence[Sequence[float | int | Fraction]],
    active_parent_indices: Sequence[int],
    candidate_children: Mapping[int, Sequence[Sequence[int]]],
) -> ChenSourceTriangleReplacementCoverageResult:
    """Require source coverage before and after one fully staged cavity replacement."""
    before_points = tuple(_point(point) for point in points)
    if not active_parent_indices or len(set(active_parent_indices)) != len(active_parent_indices):
        return ChenSourceTriangleReplacementCoverageResult(
            False, "invalid_active_parent_indices", None, None, None, True, False
        )
    if any(index < 0 or index >= len(parent_tets) for index in active_parent_indices):
        return ChenSourceTriangleReplacementCoverageResult(
            False, "active_parent_index_out_of_range", None, None, None, True, False
        )
    active = {int(index): parent_tets[int(index)] for index in active_parent_indices}
    try:
        boundary = tuple(sorted(_boundary_faces(tuple(active.values()))))
    except ValueError:
        return ChenSourceTriangleReplacementCoverageResult(
            False, "invalid_active_parent", None, None, None, True, False
        )
    staging = certify_atomic_subdivided_boundary_replacement_l3(
        points, active, boundary, candidate_children
    )
    if not staging.accepted:
        return ChenSourceTriangleReplacementCoverageResult(
            False,
            f"cavity_staging_failed:{staging.reason}",
            staging,
            None,
            None,
            before_points == tuple(_point(point) for point in points),
            False,
        )
    before_coverage = certify_source_triangle_coverage_l2(points, parent_tets, source_triangle)
    if not before_coverage.accepted:
        return ChenSourceTriangleReplacementCoverageResult(
            False,
            f"before_source_coverage_failed:{before_coverage.reason}",
            staging,
            before_coverage,
            None,
            before_points == tuple(_point(point) for point in points),
            False,
        )
    untouched = tuple(tet for index, tet in enumerate(parent_tets) if index not in active)
    after_tets = (*untouched, *(tet for _identifier, tet in staging.committed_tets))
    after_coverage = certify_source_triangle_coverage_l2(points, after_tets, source_triangle)
    unchanged = before_points == tuple(_point(point) for point in points)
    return ChenSourceTriangleReplacementCoverageResult(
        after_coverage.accepted and unchanged,
        "accepted" if after_coverage.accepted and unchanged else f"after_source_coverage_failed:{after_coverage.reason}",
        staging,
        before_coverage,
        after_coverage,
        unchanged,
        False,
    )
