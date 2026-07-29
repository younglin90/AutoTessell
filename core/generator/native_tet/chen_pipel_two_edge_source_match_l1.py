"""L1 provenance binding for the literal Chen--Zheng Table-6 Case-2 rows.

The local Table-6 geometry alone cannot establish that P1/P2 are intersections
of one real source edge.  Opposite-edge Case-2 has an interior pipel owner;
neighbouring-edge Case-2 is necessarily cofacial and therefore has a shared
face owner.  This adapter accepts only those two exact ownership modes before
delegating to the literal L0 child-list certificate.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from fractions import Fraction

from core.generator.native_tet.chen_pipel_two_edge_l0 import (
    Case2Scheme,
    ChenTwoEdgePipelResult,
    certify_two_edge_pipel_template,
)
from core.generator.native_tet.chen_source_edge_incidence_l1 import (
    ChenSourceEdgeIncidenceResult,
    build_source_edge_incidence,
)


@dataclass(frozen=True)
class ChenTwoEdgeSourceMatchResult:
    """Read-only proof that one Table-6 target has real source-edge ownership."""

    accepted: bool
    reason: str
    incidence: ChenSourceEdgeIncidenceResult | None
    template: ChenTwoEdgePipelResult | None
    source_points_unchanged: bool
    production_mesh_changed: bool


def certify_two_edge_pipel_source_match_l1(
    points: Sequence[Sequence[float | int | Fraction]],
    parent_tets: Sequence[Sequence[int]],
    source_start: Sequence[float | int | Fraction],
    source_end: Sequence[float | int | Fraction],
    *,
    target_parent_index: int,
    ordered_parent: Sequence[int],
    first_intersection: int,
    second_intersection: int,
    scheme: Case2Scheme,
) -> ChenTwoEdgeSourceMatchResult:
    """Bind explicit P1/P2 indices to a Case-2 source edge without mutation."""
    before = tuple(tuple(point) for point in points)
    if not 0 <= int(first_intersection) < len(points) or not 0 <= int(second_intersection) < len(points):
        return ChenTwoEdgeSourceMatchResult(
            False, "intersection_index_out_of_range", None, None, before == tuple(points), False
        )
    if tuple(source_start) != tuple(points[first_intersection]) or tuple(source_end) != tuple(points[second_intersection]):
        return ChenTwoEdgeSourceMatchResult(
            False, "source_endpoints_must_equal_declared_p1_p2", None, None, before == tuple(points), False
        )
    if not 0 <= int(target_parent_index) < len(parent_tets):
        return ChenTwoEdgeSourceMatchResult(
            False, "target_parent_index_out_of_range", None, None, before == tuple(points), False
        )
    # Table 6 labels A/B/C/D geometrically.  Input tet array order has no
    # such meaning, so require an explicit permutation of the target parent
    # rather than byte-identical ordering.
    if set(int(vertex) for vertex in ordered_parent) != set(int(vertex) for vertex in parent_tets[target_parent_index]) or len(tuple(ordered_parent)) != 4:
        return ChenTwoEdgeSourceMatchResult(
            False, "ordered_parent_must_be_target_parent_permutation", None, None, before == tuple(points), False
        )
    incidence = build_source_edge_incidence(points, parent_tets, source_start, source_end)
    if not incidence.accepted or incidence.incidence is None:
        return ChenTwoEdgeSourceMatchResult(
            False, f"source_edge_incidence_failed:{incidence.reason}", incidence, None, before == tuple(points), False
        )
    if scheme == "OPPOSITE":
        matching = tuple(
            pipel
            for pipel in incidence.incidence.interior_pipels
            if pipel.parent_index == target_parent_index and pipel.pipel_type.pipel_case == "CASE2"
        )
        if incidence.incidence.mode != "interior" or len(matching) != 1:
            return ChenTwoEdgeSourceMatchResult(
                False, "opposite_table6_requires_one_interior_case2_owner", incidence, None, before == tuple(points), False
            )
    else:
        boundary = incidence.incidence.boundary_incidence
        if (
            incidence.incidence.mode != "boundary_aligned"
            or boundary is None
            or target_parent_index not in boundary.owner_tets
            or any(owner_type.pipel_case != "CASE2" for owner_type in boundary.owner_pipel_types)
        ):
            return ChenTwoEdgeSourceMatchResult(
                False, "neighbour_table6_requires_shared_face_case2_owners", incidence, None, before == tuple(points), False
            )
    template = certify_two_edge_pipel_template(
        points, ordered_parent, first_intersection, second_intersection, scheme
    )
    unchanged = before == tuple(tuple(point) for point in points)
    return ChenTwoEdgeSourceMatchResult(
        template.accepted and unchanged,
        "accepted" if template.accepted and unchanged else f"table6_template_failed:{template.reason}",
        incidence,
        template,
        unchanged,
        False,
    )
