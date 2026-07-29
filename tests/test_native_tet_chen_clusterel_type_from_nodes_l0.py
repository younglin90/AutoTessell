"""Figure-4 cut-edge count tests over exact five-way Chen node ledgers."""

from __future__ import annotations

from core.generator.native_tet.chen_clusterel_node_state_l0 import (
    classify_clusterel_node_states_l0,
)
from core.generator.native_tet.chen_clusterel_type_from_nodes_l0 import (
    classify_clusterel_type_from_nodes_l0,
)


def test_endpoint_contacts_do_not_turn_a_recovered_source_boundary_into_cutting_edges() -> None:
    source = ((0, 0, 0), (2, 0, 0), (0, 2, 0))
    tetrahedron = ((0, 0, 0), (2, 0, 0), (1, 1, 2), (-2, 0, -3))
    nodes = classify_clusterel_node_states_l0(tetrahedron, source)
    result = classify_clusterel_type_from_nodes_l0(nodes)

    assert result.accepted, result.reason
    assert result.clusterel_type == "CO_PLAN"
    assert not result.cutting_local_edges


def test_open_midpoint_crossing_is_the_only_counted_cutting_edge() -> None:
    source = ((0, 0, 0), (4, 0, 0), (0, 4, 0))
    tetrahedron = ((0, 0, 0), (4, 0, 0), (2, 2, 3), (-1, -1, -2))
    nodes = classify_clusterel_node_states_l0(tetrahedron, source)
    result = classify_clusterel_type_from_nodes_l0(nodes)

    assert result.accepted, result.reason
    assert result.clusterel_type == "ONE_EDG"
    assert result.cutting_local_edges == ((2, 3),)


def test_rejected_node_ledger_cannot_supply_a_clusterel_type() -> None:
    source = ((0, 0, 0), (2, 0, 0), (0, 2, 0))
    nodes = classify_clusterel_node_states_l0(((0, 0, 0), (1, 1, 0), (0, 0, 2), (-2, 0, -3)), source)
    result = classify_clusterel_type_from_nodes_l0(nodes)

    assert not result.accepted
    assert result.reason == "node_ledger_failed:coplanar_interior_edge_overlap"
