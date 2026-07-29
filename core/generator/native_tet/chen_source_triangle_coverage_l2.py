"""Exact global source-triangle coverage audit over immutable parent tetrahedra.

Local Chen fragments cannot establish input-surface preservation by themselves:
their boundary segments cross parent faces and must close through the whole
source-triangle cavity.  This report-only L2 card clips the source triangle in
every parent tet, triangulates each exact convex fragment without new points,
and delegates the union to the existing conforming L1 subdivision certificate.
It is a precondition audit, not a recovery operation.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from fractions import Fraction

from core.generator.native_tet.chen_penetration_l0 import RationalPoint, _point
from core.generator.native_tet.chen_source_subdivision_l0 import (
    ChenSourceSubdivisionCoverageAudit,
    audit_source_triangle_subdivision_l1,
)
from core.generator.native_tet.chen_source_triangle_fragment_l1 import (
    ChenSourceTriangleFragmentResult,
    audit_source_triangle_fragment_l1,
)

IndexTet = tuple[int, int, int, int]


@dataclass(frozen=True)
class ChenSourceTriangleCoverageResult:
    """Whole-source coverage report; no input or production state is changed."""

    accepted: bool
    reason: str
    fragment_parent_indices: tuple[int, ...]
    candidate_fragment_triangles: int
    subdivision: ChenSourceSubdivisionCoverageAudit | None
    source_points_unchanged: bool
    production_mesh_changed: bool


def _as_tet(tet: Sequence[int]) -> IndexTet | None:
    values = tuple(int(value) for value in tet)
    if len(values) != 4 or len(set(values)) != 4:
        return None
    return values[0], values[1], values[2], values[3]


def certify_source_triangle_coverage_l2(
    points: Sequence[Sequence[float | int | Fraction]],
    parent_tets: Sequence[Sequence[int]],
    source_triangle: Sequence[Sequence[float | int | Fraction]],
) -> ChenSourceTriangleCoverageResult:
    """Require the exact union of all positive parent fragments to cover one source face."""
    before = tuple(_point(point) for point in points)
    source = tuple(_point(point) for point in source_triangle)
    if len(source) != 3:
        raise ValueError("a source triangle requires exactly three points")
    typed_tets = tuple(_as_tet(tet) for tet in parent_tets)
    if not typed_tets or any(tet is None for tet in typed_tets):
        return ChenSourceTriangleCoverageResult(
            False, "invalid_parent_tetrahedron", (), 0, None, True, False
        )
    tets = tuple(tet for tet in typed_tets if tet is not None)
    if any(vertex < 0 or vertex >= len(before) for tet in tets for vertex in tet):
        return ChenSourceTriangleCoverageResult(
            False, "parent_index_out_of_range", (), 0, None, True, False
        )
    assembled = list(before)
    point_ids = {point: index for index, point in enumerate(assembled)}

    def point_id(point: RationalPoint) -> int:
        if point not in point_ids:
            point_ids[point] = len(assembled)
            assembled.append(point)
        return point_ids[point]

    source_face = tuple(point_id(point) for point in source)
    candidates: list[tuple[int, int, int]] = []
    fragment_parents: list[int] = []
    for parent_index, tet in enumerate(tets):
        fragment: ChenSourceTriangleFragmentResult = audit_source_triangle_fragment_l1(
            tuple(before[index] for index in tet), source
        )
        if not fragment.accepted:
            if fragment.reason == "source_triangle_has_no_positive_area_inside_parent":
                continue
            return ChenSourceTriangleCoverageResult(
                False,
                f"fragment_failed:{parent_index}:{fragment.reason}",
                (),
                0,
                None,
                before == tuple(_point(point) for point in points),
                False,
            )
        fragment_ids = tuple(point_id(point) for point in fragment.vertices)
        fragment_parents.append(parent_index)
        for index in range(1, len(fragment_ids) - 1):
            candidates.append((fragment_ids[0], fragment_ids[index], fragment_ids[index + 1]))
    unchanged = before == tuple(_point(point) for point in points)
    if not candidates:
        return ChenSourceTriangleCoverageResult(
            False, "source_triangle_has_no_positive_area_in_parent_mesh", (), 0, None, unchanged, False
        )
    subdivision = audit_source_triangle_subdivision_l1(assembled, (source_face,), candidates)
    return ChenSourceTriangleCoverageResult(
        subdivision.accepted and unchanged,
        "accepted" if subdivision.accepted and unchanged else f"source_fragment_union_failed:{subdivision.reason}",
        tuple(fragment_parents),
        len(candidates),
        subdivision,
        unchanged,
        False,
    )
