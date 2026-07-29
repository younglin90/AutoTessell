"""L1 exact source-triangle/tet fragment tests; no recovery mutation."""

from __future__ import annotations

from fractions import Fraction

from core.generator.native_tet.chen_source_triangle_fragment_l1 import (
    audit_source_triangle_fragment_l1,
)


def test_one_edge_clusterel_still_has_a_measurable_positive_area_source_fragment() -> None:
    result = audit_source_triangle_fragment_l1(
        ((0, 0, -1), (4, 0, -1), (0, 4, -1), (0, 0, 1)),
        ((-1, -1, 0), (1, -1, 0), (0, 1, 0)),
    )

    assert result.accepted, result.reason
    assert result.parameter_double_area > 0
    assert (Fraction(0), Fraction(0), Fraction(0)) in result.vertices
    assert len(result.vertices) >= 3
    assert result.source_points_unchanged
    assert not result.production_mesh_changed


def test_three_edge_clusterel_fragment_is_exactly_reported_in_source_parameter_space() -> None:
    result = audit_source_triangle_fragment_l1(
        ((-1, 0, -1), (1, 0, -1), (0, 1, -1), (0, 0, 1)),
        ((-4, -4, 0), (4, -4, 0), (0, 4, 0)),
    )

    assert result.accepted, result.reason
    assert result.parameter_double_area > 0
    assert len(result.parameter_vertices) == 3
    assert len(result.vertices) == 3


def test_disjoint_triangle_has_no_partial_fragment_output() -> None:
    result = audit_source_triangle_fragment_l1(
        ((0, 0, -1), (1, 0, -1), (0, 1, -1), (0, 0, 1)),
        ((10, 10, 0), (11, 10, 0), (10, 11, 0)),
    )

    assert not result.accepted
    assert result.reason == "source_triangle_has_no_positive_area_inside_parent"
    assert not result.vertices


def test_source_triangle_fragment_is_value_identical_on_repeat() -> None:
    tetrahedron = ((0, 0, -1), (4, 0, -1), (0, 4, -1), (0, 0, 1))
    triangle = ((-1, -1, 0), (1, -1, 0), (0, 1, 0))

    assert audit_source_triangle_fragment_l1(tetrahedron, triangle) == audit_source_triangle_fragment_l1(
        tetrahedron, triangle
    )
