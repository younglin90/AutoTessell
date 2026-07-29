"""L1 strict Chen cut-node provenance tests; no local template is selected."""

from __future__ import annotations

from fractions import Fraction

from core.generator.native_tet.chen_clusterel_node_type_l1 import (
    classify_strict_clusterel_node_types_l1,
)


def test_one_edge_clusterel_records_its_single_mid_edge_node_on_the_fragment() -> None:
    result = classify_strict_clusterel_node_types_l1(
        ((0, 0, -1), (4, 0, -1), (0, 4, -1), (0, 0, 1)),
        ((-1, -1, 0), (1, -1, 0), (0, 1, 0)),
    )

    assert result.accepted, result.reason
    assert result.classification is not None
    assert result.classification.clusterel_type == "ONE_EDG"
    assert len(result.cut_nodes) == 1
    assert result.cut_nodes[0].local_edge == (0, 3)
    assert result.cut_nodes[0].point == (Fraction(0), Fraction(0), Fraction(0))
    assert result.cut_nodes[0].node_type == "NOD_MID"
    assert result.fragment is not None
    assert result.fragment.vertices[result.cut_nodes[0].fragment_vertex_index] == result.cut_nodes[0].point
    assert result.source_points_unchanged
    assert not result.production_mesh_changed


def test_three_edge_clusterel_records_all_strict_nodes_without_inventing_any_label() -> None:
    result = classify_strict_clusterel_node_types_l1(
        ((-1, 0, -1), (1, 0, -1), (0, 1, -1), (0, 0, 1)),
        ((-4, -4, 0), (4, -4, 0), (0, 4, 0)),
    )

    assert result.accepted, result.reason
    assert result.classification is not None
    assert result.classification.clusterel_type == "THR_EDG"
    assert len(result.cut_nodes) == 3
    assert {node.node_type for node in result.cut_nodes} == {"NOD_MID"}
    assert result.fragment is not None
    assert {node.fragment_vertex_index for node in result.cut_nodes} == {0, 1, 2}


def test_constraint_boundary_contact_exposes_no_partial_node_ledger() -> None:
    result = classify_strict_clusterel_node_types_l1(
        ((0, 0, -1), (4, 0, -1), (0, 4, -1), (0, 0, 1)),
        ((-1, -1, 0), (1, -1, 0), (0, 0, 0)),
    )

    assert not result.accepted
    assert result.reason == "clusterel_has_no_supported_strict_cut_nodes"
    assert not result.cut_nodes


def test_strict_node_ledger_is_value_identical_on_repeat() -> None:
    tetrahedron = ((0, 0, -1), (4, 0, -1), (0, 4, -1), (0, 0, 1))
    triangle = ((-1, -1, 0), (1, -1, 0), (0, 1, 0))

    assert classify_strict_clusterel_node_types_l1(
        tetrahedron, triangle
    ) == classify_strict_clusterel_node_types_l1(tetrahedron, triangle)
