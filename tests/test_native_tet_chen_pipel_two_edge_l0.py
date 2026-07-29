"""Literal Chen--Zheng-2006 Table-6 Case-2 geometry tests."""

from __future__ import annotations

from fractions import Fraction

from core.generator.native_tet.chen_pipel_two_edge_l0 import (
    certify_two_edge_pipel_template,
)


_POINTS = (
    (0, 0, 0),  # A
    (2, 0, 0),  # B
    (0, 2, 0),  # C
    (0, 0, 2),  # D
    (0, 0, 1),  # P1 on AD
    (1, 1, 0),  # P2 on BC
    (1, 0, 1),  # P2 on BD
)
_PARENT = (0, 1, 2, 3)


def test_table6_opposite_edge_children_preserve_exact_parent_boundary_and_volume() -> None:
    result = certify_two_edge_pipel_template(_POINTS, _PARENT, 4, 5, "OPPOSITE")

    assert result.accepted, result.reason
    assert len(result.replacement_tets) == 4
    assert result.parent_volume6 == result.replacement_volume6
    assert result.external_boundary_preserved


def test_table6_neighbouring_s_and_z_children_each_preserve_exact_contract() -> None:
    s_type = certify_two_edge_pipel_template(_POINTS, _PARENT, 4, 6, "NEIGHBOR_S")
    z_type = certify_two_edge_pipel_template(_POINTS, _PARENT, 4, 6, "NEIGHBOR_Z")

    assert s_type.accepted, s_type.reason
    assert z_type.accepted, z_type.reason
    assert len(s_type.replacement_tets) == len(z_type.replacement_tets) == 3
    assert s_type.parent_volume6 == s_type.replacement_volume6
    assert z_type.parent_volume6 == z_type.replacement_volume6
    assert s_type.external_boundary_preserved and z_type.external_boundary_preserved
    assert s_type.replacement_tets != z_type.replacement_tets


def test_table6_rejects_scheme_when_points_do_not_match_its_literal_edges() -> None:
    result = certify_two_edge_pipel_template(_POINTS, _PARENT, 4, 5, "NEIGHBOR_S")

    assert not result.accepted
    assert result.reason == "intersections_do_not_match_literal_table6_edges"


def test_table6_result_is_value_identical_on_repeat() -> None:
    first = certify_two_edge_pipel_template(_POINTS, _PARENT, 4, 5, "OPPOSITE")
    second = certify_two_edge_pipel_template(_POINTS, _PARENT, 4, 5, "OPPOSITE")

    assert first == second


def test_table6_two_intersection_row_recovers_only_a_segment_not_a_source_facet() -> None:
    # With exactly P1/P2 on the source plane, no child tet face can be a
    # two-dimensional source subface. Table 6 is a missing-edge pipel row;
    # promoting this local split directly to a recovered-facet claim would be
    # a category error.
    points = (
        (0, 0, -2), (-2, -1, -1), (2, 1, 2), (1, 0, 2),
        (Fraction(1, 2), 0, 0), (Fraction(-2, 3), Fraction(-1, 3), 0),
    )
    result = certify_two_edge_pipel_template(points, (0, 1, 2, 3), 4, 5, "OPPOSITE")

    assert result.accepted, result.reason
    source_plane_faces = [
        tuple(tet[index] for index in range(4) if index != omitted)
        for tet in result.replacement_tets
        for omitted in range(4)
        if all(points[vertex][2] == 0 for vertex in tuple(tet[index] for index in range(4) if index != omitted))
    ]
    assert not source_plane_faces
