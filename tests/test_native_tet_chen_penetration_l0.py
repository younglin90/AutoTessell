"""L0 exact/read-only tests for Chen-2011 penetration classification."""

from __future__ import annotations

from fractions import Fraction

from core.generator.native_tet.chen_penetration_l0 import (
    classify_constraint_triangle_penetration,
)


def test_one_strict_penetrating_edge_is_classified_without_template_mutation() -> None:
    tetrahedron = ((0, 0, -1), (4, 0, -1), (0, 4, -1), (0, 0, 1))
    constraint = ((-1, -1, 0), (1, -1, 0), (0, 1, 0))

    result = classify_constraint_triangle_penetration(tetrahedron, constraint)

    assert result.status == "unique"
    assert result.penetrating_edges == ((0, 3),)
    assert result.intersection_points == ((Fraction(0), Fraction(0), Fraction(0)),)


def test_three_edge_case_is_distinct_from_one_edge_template() -> None:
    tetrahedron = ((-1, 0, -1), (1, 0, -1), (0, 1, -1), (0, 0, 1))
    constraint = ((-4, -4, 0), (4, -4, 0), (0, 4, 0))

    result = classify_constraint_triangle_penetration(tetrahedron, constraint)

    assert result.status == "unique"
    assert result.n_penetrating_edges == 3
    assert result.penetrating_edges == ((0, 3), (1, 3), (2, 3))


def test_existing_coplanar_subface_is_not_misclassified_as_a_split() -> None:
    tetrahedron = ((-0.5, -0.5, 0), (0.5, -0.5, 0), (0, 0.5, 0), (0, 0, 1))
    constraint = ((-1, -1, 0), (1, -1, 0), (0, 1, 0))

    result = classify_constraint_triangle_penetration(tetrahedron, constraint)

    assert result.status == "subface"
    assert result.n_penetrating_edges == 0


def test_constraint_boundary_touch_is_rejected_as_nonunique() -> None:
    tetrahedron = ((0, 0, -1), (4, 0, -1), (0, 4, -1), (0, 0, 1))
    constraint = ((-1, -1, 0), (1, -1, 0), (0, 0, 0))

    result = classify_constraint_triangle_penetration(tetrahedron, constraint)

    assert result.status == "constraint_boundary_touch"
    assert result.n_penetrating_edges == 0


def test_classification_is_value_identical_on_repeat() -> None:
    tetrahedron = ((0, 0, -1), (4, 0, -1), (0, 4, -1), (0, 0, 1))
    constraint = ((-1, -1, 0), (1, -1, 0), (0, 1, 0))

    assert classify_constraint_triangle_penetration(
        tetrahedron, constraint
    ) == classify_constraint_triangle_penetration(tetrahedron, constraint)
