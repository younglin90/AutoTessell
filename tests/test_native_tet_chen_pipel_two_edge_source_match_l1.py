"""L1 source-edge provenance tests for literal Chen Table-6 Case-2 rows."""

from __future__ import annotations

from fractions import Fraction

from core.generator.native_tet.chen_pipel_two_edge_source_match_l1 import (
    certify_two_edge_pipel_source_match_l1,
)


_POINTS = (
    (0, 0, 0), (2, 0, 0), (0, 2, 0), (0, 0, 2),
    (0, 0, 1),  # P1 on AD
    (1, 1, 0),  # P2 on BC
    (1, 0, 1),  # P2 on BD
    (0, -2, 0),
)
_PARENT = (0, 1, 2, 3)


def test_opposite_table6_row_requires_one_real_interior_case2_pipel() -> None:
    result = certify_two_edge_pipel_source_match_l1(
        _POINTS, (_PARENT,), _POINTS[4], _POINTS[5],
        target_parent_index=0, ordered_parent=_PARENT,
        first_intersection=4, second_intersection=5, scheme="OPPOSITE",
    )

    assert result.accepted, result.reason
    assert result.incidence is not None and result.incidence.incidence is not None
    assert result.incidence.incidence.mode == "interior"
    assert result.template is not None and result.template.accepted
    assert result.source_points_unchanged
    assert not result.production_mesh_changed


def test_neighbouring_table6_row_requires_shared_face_case2_owners() -> None:
    result = certify_two_edge_pipel_source_match_l1(
        _POINTS, (_PARENT, (0, 1, 3, 7)), _POINTS[4], _POINTS[6],
        target_parent_index=0, ordered_parent=_PARENT,
        first_intersection=4, second_intersection=6, scheme="NEIGHBOR_S",
    )

    assert result.accepted, result.reason
    assert result.incidence is not None and result.incidence.incidence is not None
    assert result.incidence.incidence.mode == "boundary_aligned"
    assert result.template is not None and result.template.accepted


def test_declared_intersections_cannot_be_detached_from_the_source_edge() -> None:
    result = certify_two_edge_pipel_source_match_l1(
        _POINTS, (_PARENT,), _POINTS[4], _POINTS[5],
        target_parent_index=0, ordered_parent=_PARENT,
        first_intersection=4, second_intersection=6, scheme="OPPOSITE",
    )

    assert not result.accepted
    assert result.reason == "source_endpoints_must_equal_declared_p1_p2"


def test_case2_source_match_is_value_identical_on_repeat() -> None:
    first = certify_two_edge_pipel_source_match_l1(
        _POINTS, (_PARENT,), _POINTS[4], _POINTS[5],
        target_parent_index=0, ordered_parent=_PARENT,
        first_intersection=4, second_intersection=5, scheme="OPPOSITE",
    )
    second = certify_two_edge_pipel_source_match_l1(
        _POINTS, (_PARENT,), _POINTS[4], _POINTS[5],
        target_parent_index=0, ordered_parent=_PARENT,
        first_intersection=4, second_intersection=5, scheme="OPPOSITE",
    )

    assert first == second


def test_geometric_table6_order_may_be_an_explicit_target_parent_permutation() -> None:
    points = (
        (0, 0, 0), (4, 0, 0), (0, 4, 0), (2, 2, 3), (-1, -1, -2),
        (1, 1, -1), (4, 2, 2), (2, Fraction(4, 3), 0),
        (Fraction(5, 4), Fraction(5, 4), 0),
    )
    parents = (
        (5, 0, 1, 4), (5, 0, 2, 4), (5, 6, 2, 1), (5, 6, 3, 1),
        (5, 0, 3, 1), (5, 6, 3, 2), (5, 0, 3, 2),
    )
    result = certify_two_edge_pipel_source_match_l1(
        points, parents, points[7], points[8],
        target_parent_index=3, ordered_parent=(6, 3, 1, 5),
        first_intersection=7, second_intersection=8, scheme="NEIGHBOR_S",
    )

    assert result.accepted, result.reason
    assert result.incidence is not None and result.incidence.incidence is not None
    assert result.incidence.incidence.mode == "boundary_aligned"
