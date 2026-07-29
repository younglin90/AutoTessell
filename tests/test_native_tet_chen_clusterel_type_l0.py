"""L0 exact Chen clusterel classification tests; no recovery mutation occurs."""

from __future__ import annotations

import pytest

from core.generator.native_tet.chen_clusterel_type_l0 import classify_clusterel_type

TRIANGLE = ((-8, -8, 0), (8, -8, 0), (0, 8, 0))
ONE_EDGE_TRIANGLE = ((-1, -1, 0), (1, -1, 0), (0, 1, 0))


@pytest.mark.parametrize(
    ("tetrahedron", "triangle", "expected"),
    [
        (((0, 0, -1), (4, 0, -1), (0, 4, -1), (0, 0, 1)), ONE_EDGE_TRIANGLE, "ONE_EDG"),
        (((-4, -4, -3), (-4, -2, -3), (2, 2, -3), (4, 4, 3)), TRIANGLE, "TWO_EDG"),
        (((-1, 0, -1), (1, 0, -1), (0, 1, -1), (0, 0, 1)), TRIANGLE, "THR_EDG"),
        (((-4, -4, -3), (-4, -4, 3), (-4, -2, -3), (-2, -4, 3)), TRIANGLE, "FOU_EDG"),
    ],
)
def test_all_strict_clusterel_edge_counts_map_to_the_documented_type(
    tetrahedron: tuple[tuple[int, int, int], ...],
    triangle: tuple[tuple[int, int, int], ...],
    expected: str,
) -> None:
    result = classify_clusterel_type(tetrahedron, triangle)

    assert result.accepted, result.reason
    assert result.clusterel_type == expected


def test_coplanar_subface_is_coplanar_clusterel_not_an_edge_cut() -> None:
    result = classify_clusterel_type(
        ((-1, -1, 0), (1, -1, 0), (0, 1, 0), (0, 0, 1)),
        TRIANGLE,
    )

    assert result.accepted
    assert result.clusterel_type == "CO_PLAN"


def test_degenerate_or_constraint_boundary_contact_fails_closed() -> None:
    degenerate = classify_clusterel_type(((0, 0, -1), (1, 0, -1), (0, 1, -1), (1, 1, -1)), TRIANGLE)
    contact = classify_clusterel_type(
        ((0, 0, -1), (4, 0, -1), (0, 4, -1), (0, 0, 1)),
        ((-1, -1, 0), (1, -1, 0), (0, 0, 0)),
    )

    assert not degenerate.accepted
    assert degenerate.reason == "degenerate_clusterel_tetrahedron"
    assert not contact.accepted
    assert contact.reason == "constraint_boundary_touch"
