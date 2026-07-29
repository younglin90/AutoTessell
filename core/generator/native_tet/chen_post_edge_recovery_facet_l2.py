"""L2 complete post-edge-recovery source-facet state audit, test-only.

Before a Chen facet template can be considered, every active parent around a
missing source face must expose regenerated node/type provenance, the three
source edges must already exist, the source face itself must remain absent,
and the immutable source triangle must be exactly covered by the parent mesh.
This module measures that conjunction without changing connectivity.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from fractions import Fraction

from core.generator.native_tet.chen_clusterel_node_state_l0 import (
    ChenClusterelNodeStateResult,
    classify_clusterel_node_states_l0,
)
from core.generator.native_tet.chen_clusterel_type_from_nodes_l0 import (
    ChenClusterelTypeFromNodesResult,
    classify_clusterel_type_from_nodes_l0,
)
from core.generator.native_tet.chen_post_edge_recovery_state_l1 import (
    ChenPostEdgeRecoveryClusterelRecord,
    ChenPostEdgeRecoveryStateResult,
    certify_post_edge_recovery_clusterel_state_l1,
)
from core.generator.native_tet.chen_source_triangle_coverage_l2 import (
    ChenSourceTriangleCoverageResult,
    certify_source_triangle_coverage_l2,
)


@dataclass(frozen=True)
class ChenPostEdgeRecoveryFacetStateResult:
    """Complete immutable source-facet state; no recovery candidate is emitted."""

    accepted: bool
    reason: str
    active_parent_types: tuple[tuple[int, str], ...]
    records: tuple[ChenPostEdgeRecoveryStateResult, ...]
    coverage: ChenSourceTriangleCoverageResult | None
    source_points_unchanged: bool
    production_mesh_changed: bool


def certify_post_edge_recovery_facet_state_l2(
    points: Sequence[Sequence[float | int | Fraction]],
    parent_tets: Sequence[Sequence[int]],
    source_vertex_indices: tuple[int, int, int],
    records: Sequence[ChenPostEdgeRecoveryClusterelRecord],
) -> ChenPostEdgeRecoveryFacetStateResult:
    """Require exact complete precondition state for one missing source facet."""
    before = tuple(tuple(point) for point in points)
    if len(set(source_vertex_indices)) != 3 or any(index < 0 or index >= len(points) for index in source_vertex_indices):
        return ChenPostEdgeRecoveryFacetStateResult(False, "invalid_source_vertex_indices", (), (), None, True, False)
    typed_tets = tuple(tuple(int(vertex) for vertex in tet) for tet in parent_tets)
    if not typed_tets or any(len(tet) != 4 or len(set(tet)) != 4 for tet in typed_tets):
        return ChenPostEdgeRecoveryFacetStateResult(False, "invalid_parent_tetrahedron", (), (), None, True, False)
    if any(vertex < 0 or vertex >= len(points) for tet in typed_tets for vertex in tet):
        return ChenPostEdgeRecoveryFacetStateResult(False, "parent_index_out_of_range", (), (), None, True, False)
    source_set = set(source_vertex_indices)
    if any(source_set <= set(tet) for tet in typed_tets):
        return ChenPostEdgeRecoveryFacetStateResult(False, "source_face_is_already_a_parent_face", (), (), None, True, False)
    source = tuple(points[index] for index in source_vertex_indices)
    active: list[tuple[int, str]] = []
    for parent_index, tet in enumerate(typed_tets):
        node_state: ChenClusterelNodeStateResult = classify_clusterel_node_states_l0(
            tuple(points[index] for index in tet), source
        )
        type_state: ChenClusterelTypeFromNodesResult = classify_clusterel_type_from_nodes_l0(node_state)
        if not type_state.accepted or type_state.clusterel_type is None:
            return ChenPostEdgeRecoveryFacetStateResult(
                False, f"parent_node_type_failed:{parent_index}:{type_state.reason}", (), (), None, before == tuple(tuple(point) for point in points), False
            )
        if type_state.clusterel_type != "CO_PLAN":
            active.append((parent_index, type_state.clusterel_type))
    supplied = tuple(record.parent_index for record in records)
    if len(set(supplied)) != len(supplied) or set(supplied) != {index for index, _type in active}:
        return ChenPostEdgeRecoveryFacetStateResult(
            False, "records_must_cover_exactly_all_active_parents", tuple(active), (), None, before == tuple(tuple(point) for point in points), False
        )
    record_results: list[ChenPostEdgeRecoveryStateResult] = []
    for record in sorted(records, key=lambda item: item.parent_index):
        state = certify_post_edge_recovery_clusterel_state_l1(
            points, typed_tets, source_vertex_indices, record
        )
        if not state.accepted:
            return ChenPostEdgeRecoveryFacetStateResult(
                False, f"record_failed:{record.parent_index}:{state.reason}", tuple(active), tuple(record_results), None, before == tuple(tuple(point) for point in points), False
            )
        record_results.append(state)
    coverage = certify_source_triangle_coverage_l2(points, typed_tets, source)
    unchanged = before == tuple(tuple(point) for point in points)
    return ChenPostEdgeRecoveryFacetStateResult(
        coverage.accepted and unchanged,
        "accepted" if coverage.accepted and unchanged else f"source_coverage_failed:{coverage.reason}",
        tuple(active),
        tuple(record_results),
        coverage,
        unchanged,
        False,
    )
