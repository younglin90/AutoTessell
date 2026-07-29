"""Fail-closed L1 audit for one Chen post-edge-recovery clusterel record.

This does not infer a clusterel decomposition.  It requires the source facet
vertices and all three recovered source edges to exist in the immutable parent
mesh, then regenerates the five-way local node ledger exactly.  A supplied
record must be value-identical to that oracle result.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from fractions import Fraction

from core.generator.native_tet.chen_clusterel_node_state_l0 import (
    ChenClusterelEdgeNode,
    ChenClusterelNodeStateResult,
    classify_clusterel_node_states_l0,
)


@dataclass(frozen=True)
class ChenPostEdgeRecoveryClusterelRecord:
    """Caller-supplied node state for exactly one immutable parent tet."""

    parent_index: int
    nodes: tuple[ChenClusterelEdgeNode, ...]


@dataclass(frozen=True)
class ChenPostEdgeRecoveryStateResult:
    """Read-only result; rejection exposes no trusted recovered state."""

    accepted: bool
    reason: str
    regenerated_nodes: ChenClusterelNodeStateResult | None
    source_points_unchanged: bool
    production_mesh_changed: bool


def _mesh_edges(parent_tets: Sequence[Sequence[int]]) -> set[tuple[int, int]]:
    edges: set[tuple[int, int]] = set()
    for tet in parent_tets:
        for first in range(4):
            for second in range(first + 1, 4):
                left, right = int(tet[first]), int(tet[second])
                edges.add((min(left, right), max(left, right)))
    return edges


def certify_post_edge_recovery_clusterel_state_l1(
    points: Sequence[Sequence[float | int | Fraction]],
    parent_tets: Sequence[Sequence[int]],
    source_vertex_indices: tuple[int, int, int],
    record: ChenPostEdgeRecoveryClusterelRecord,
) -> ChenPostEdgeRecoveryStateResult:
    """Require recovered source-edge presence and an exact five-way node record."""
    before = tuple(tuple(point) for point in points)
    if len(parent_tets) == 0 or len(set(source_vertex_indices)) != 3:
        return ChenPostEdgeRecoveryStateResult(False, "invalid_source_or_empty_parent_mesh", None, True, False)
    if any(index < 0 or index >= len(points) for index in source_vertex_indices):
        return ChenPostEdgeRecoveryStateResult(False, "source_vertex_index_out_of_range", None, True, False)
    typed_tets = tuple(tuple(int(vertex) for vertex in tet) for tet in parent_tets)
    if any(len(tet) != 4 or len(set(tet)) != 4 for tet in typed_tets):
        return ChenPostEdgeRecoveryStateResult(False, "invalid_parent_tetrahedron", None, True, False)
    if any(vertex < 0 or vertex >= len(points) for tet in typed_tets for vertex in tet):
        return ChenPostEdgeRecoveryStateResult(False, "parent_index_out_of_range", None, True, False)
    source_edges = {
        tuple(sorted((source_vertex_indices[index], source_vertex_indices[(index + 1) % 3])))
        for index in range(3)
    }
    if not source_edges <= _mesh_edges(typed_tets):
        return ChenPostEdgeRecoveryStateResult(False, "source_edges_are_not_all_recovered", None, True, False)
    if not 0 <= record.parent_index < len(typed_tets):
        return ChenPostEdgeRecoveryStateResult(False, "record_parent_index_out_of_range", None, True, False)
    source = tuple(points[index] for index in source_vertex_indices)
    regenerated = classify_clusterel_node_states_l0(
        tuple(points[index] for index in typed_tets[record.parent_index]), source
    )
    unchanged = before == tuple(tuple(point) for point in points)
    if not regenerated.accepted:
        return ChenPostEdgeRecoveryStateResult(
            False, f"five_way_node_predicate_failed:{regenerated.reason}", regenerated, unchanged, False
        )
    if record.nodes != regenerated.nodes:
        return ChenPostEdgeRecoveryStateResult(
            False, "recorded_nodes_do_not_match_exact_predicate", regenerated, unchanged, False
        )
    return ChenPostEdgeRecoveryStateResult(True, "accepted", regenerated, unchanged, False)
