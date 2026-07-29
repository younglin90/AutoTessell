"""Test-only local NOD_EDG Table-5 transaction over immutable staged state.

This L1 card combines exactly one geometric NOD_EDG pipel with the Table-5
child list, two documented Phi requests, and atomic boundary staging.  Adjacent
candidate children are topology witnesses only: their own source-edge
provenance is intentionally not inferred here, so this is not an end-to-end
missing-edge recovery algorithm.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from fractions import Fraction

from core.generator.native_tet.chen_phi_api_l0 import ChenPhiLookupResult, chen_phi_neighbor_lookup
from core.generator.native_tet.chen_pipe_cluster_l0 import IndexTet, _point, _positive_orientation
from core.generator.native_tet.chen_pipel_type_l0 import classify_pipel_type
from core.generator.native_tet.chen_source_edge_incidence_l1 import (
    ChenSourceEdgeIncidence,
    build_source_edge_incidence,
)
from core.generator.native_tet.chen_staged_state_l0 import (
    ChenStagedCommitResult,
    certify_atomic_staged_replacement,
)


@dataclass(frozen=True)
class ChenNodEdgTransactionResult:
    """Test-only local transaction result; rejected cases commit nothing."""

    accepted: bool
    reason: str
    target_children: tuple[IndexTet, ...]
    phi_results: tuple[ChenPhiLookupResult, ...]
    staged_commit: ChenStagedCommitResult | None
    source_incidence: ChenSourceEdgeIncidence | None = None


def _as_tet(tet: Sequence[int]) -> IndexTet | None:
    values = tuple(int(vertex) for vertex in tet)
    if len(values) != 4 or len(set(values)) != 4:
        return None
    return values[0], values[1], values[2], values[3]


def certify_local_nod_edg_transaction(
    points: Sequence[Sequence[float | int | Fraction]],
    active_parents: Mapping[int, Sequence[int]],
    source_boundary_faces: Sequence[Sequence[int]],
    candidate_children: Mapping[int, Sequence[Sequence[int]]],
    *,
    target_parent: int,
    source_node: int,
    cut_edge: tuple[int, int],
    intersection_point: int,
) -> ChenNodEdgTransactionResult:
    """Construct one exact NOD_EDG Table-5 candidate and atomically certify it."""
    target_raw = active_parents.get(int(target_parent))
    target = _as_tet(target_raw) if target_raw is not None else None
    if target is None:
        return ChenNodEdgTransactionResult(False, "invalid_target_parent", (), (), None)
    rational_points = tuple(_point(point) for point in points)
    source = int(source_node)
    cut_start, cut_end = int(cut_edge[0]), int(cut_edge[1])
    intersection = int(intersection_point)
    if (
        source not in target
        or cut_start == cut_end
        or cut_start not in target
        or cut_end not in target
        or source in {cut_start, cut_end}
        or intersection in target
        or min(source, cut_start, cut_end, intersection) < 0
        or max(source, cut_start, cut_end, intersection) >= len(rational_points)
    ):
        return ChenNodEdgTransactionResult(False, "invalid_nod_edg_indices", (), (), None)
    other = tuple(vertex for vertex in target if vertex not in {source, cut_start, cut_end})
    if len(other) != 1:
        return ChenNodEdgTransactionResult(
            False, "target_does_not_have_one_other_vertex", (), (), None
        )
    pipel_type = classify_pipel_type(
        tuple(rational_points[index] for index in target),
        rational_points[source],
        rational_points[intersection],
    )
    if not pipel_type.accepted or pipel_type.pipel_case != "CASE1":
        return ChenNodEdgTransactionResult(False, "target_is_not_table5_nod_edg", (), (), None)

    # The Table-5 endpoint must be derived from an actual, complete source-edge
    # incidence record.  This local card supports only the cofacial NOD_EDG
    # form; an open interior pipel must use its own documented template.
    parent_ids = tuple(sorted(active_parents))
    parent_positions = {identifier: position for position, identifier in enumerate(parent_ids)}
    ordered_parents = tuple(active_parents[identifier] for identifier in parent_ids)
    target_position = parent_positions[int(target_parent)]
    source_edge = build_source_edge_incidence(
        points,
        ordered_parents,
        rational_points[source],
        rational_points[intersection],
    )
    if (
        not source_edge.accepted
        or source_edge.incidence is None
        or source_edge.incidence.mode != "boundary_aligned"
        or source_edge.incidence.boundary_incidence is None
        or target_position not in source_edge.incidence.boundary_incidence.owner_tets
    ):
        return ChenNodEdgTransactionResult(
            False, "target_is_not_a_boundary_aligned_table5_owner", (), (), None
        )
    owner_parent_ids = tuple(
        parent_ids[position] for position in source_edge.incidence.boundary_incidence.owner_tets
    )
    if any(not candidate_children.get(identifier) for identifier in owner_parent_ids):
        return ChenNodEdgTransactionResult(
            False, "boundary_aligned_owner_children_missing", (), (), None
        )

    # Table 5: t=ABCD, P on B-D -> ABCP and APCD, with A=source and C=other.
    raw_children = (
        (source, cut_start, other[0], intersection),
        (source, intersection, other[0], cut_end),
    )
    oriented = tuple(_positive_orientation(rational_points, child) for child in raw_children)
    if any(child is None for child in oriented):
        return ChenNodEdgTransactionResult(False, "table5_child_has_zero_volume", (), (), None)
    target_children = tuple(child for child in oriented if child is not None)
    supplied_target = tuple(
        _as_tet(child) for child in candidate_children.get(int(target_parent), ())
    )
    if tuple(sorted(target_children)) != tuple(
        sorted(child for child in supplied_target if child is not None)
    ):
        return ChenNodEdgTransactionResult(
            False, "candidate_target_children_do_not_match_table5", (), (), None
        )

    # Phi uses dense parent-array positions, while staged state intentionally
    # permits stable non-contiguous parent IDs.  Reindex only for the lookup.
    children_by_position = {
        parent_positions[identifier]: children
        for identifier, children in candidate_children.items()
        if identifier in parent_positions
    }
    # The two Phi requests in Table 5 resolve children across faces BCP and ABP.
    phi_results = (
        chen_phi_neighbor_lookup(
            ordered_parents,
            children_by_position,
            target_position,
            source,
            (cut_start, other[0], intersection),
        ),
        chen_phi_neighbor_lookup(
            ordered_parents,
            children_by_position,
            target_position,
            other[0],
            (source, cut_start, intersection),
        ),
    )
    if not all(result.resolved for result in phi_results):
        return ChenNodEdgTransactionResult(
            False, "table5_phi_relation_unresolved", (), phi_results, None
        )
    staged = certify_atomic_staged_replacement(
        points,
        active_parents,
        source_boundary_faces,
        candidate_children,
        required_source_edge=(source, intersection),
    )
    return ChenNodEdgTransactionResult(
        staged.accepted,
        "accepted" if staged.accepted else staged.reason,
        target_children if staged.accepted else (),
        phi_results,
        staged,
        source_edge.incidence,
    )
