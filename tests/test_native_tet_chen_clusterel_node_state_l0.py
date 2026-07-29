"""Exact five-way Chen clusterel-node predicate tests."""

from __future__ import annotations

from core.generator.native_tet.chen_clusterel_node_state_l0 import (
    classify_clusterel_node_states_l0,
)


_SOURCE = ((0, 0, 0), (2, 0, 0), (0, 2, 0))


def test_recovered_source_boundary_edge_is_nul_while_endpoint_contacts_are_recorded() -> None:
    tetrahedron = ((0, 0, 0), (2, 0, 0), (1, 1, 2), (-2, 0, -3))
    result = classify_clusterel_node_states_l0(tetrahedron, _SOURCE)

    assert result.accepted, result.reason
    nodes = {node.local_edge: node for node in result.nodes}
    assert nodes[(0, 1)].node_type == "NOD_NUL"  # recovered source edge AB
    assert nodes[(0, 2)].node_type == "NOD_BEG"
    assert nodes[(1, 2)].node_type == "NOD_BEG"
    assert result.source_points_unchanged
    assert not result.production_mesh_changed


def test_end_and_extension_states_are_exactly_distinguished() -> None:
    tetrahedron = ((0, 0, 1), (2, 0, 0), (0, 0, 2), (0, 2, 0))
    result = classify_clusterel_node_states_l0(tetrahedron, _SOURCE)

    assert result.accepted, result.reason
    nodes = {node.local_edge: node for node in result.nodes}
    assert nodes[(0, 1)].node_type == "NOD_END"
    assert nodes[(0, 2)].node_type == "NOD_EXT"
    assert nodes[(0, 2)].line_parameter == -1


def test_open_edge_intersection_is_mid() -> None:
    tetrahedron = ((-1, 0, -1), (1, 0, 1), (0, -1, -1), (0, 1, -1))
    source = ((-2, -2, 0), (2, -2, 0), (0, 2, 0))
    result = classify_clusterel_node_states_l0(tetrahedron, source)

    assert result.accepted, result.reason
    assert any(node.node_type == "NOD_MID" for node in result.nodes)


def test_coplanar_edge_through_source_interior_rejects_instead_of_becoming_nul() -> None:
    tetrahedron = ((0, 0, 0), (1, 1, 0), (0, 0, 2), (-2, 0, -3))
    result = classify_clusterel_node_states_l0(tetrahedron, _SOURCE)

    assert not result.accepted
    assert result.reason == "coplanar_interior_edge_overlap"


def test_five_way_node_ledger_is_value_identical_on_repeat() -> None:
    tetrahedron = ((0, 0, 0), (2, 0, 0), (1, 1, 2), (-2, 0, -3))

    assert classify_clusterel_node_states_l0(tetrahedron, _SOURCE) == classify_clusterel_node_states_l0(
        tetrahedron, _SOURCE
    )
