"""Exact Table-2 pipel kind/case tests; no recovery mutation occurs."""

from __future__ import annotations

import pytest

from core.generator.native_tet.chen_pipel_type_l0 import (
    classify_pipel_type,
    classify_tet_boundary_position,
)

TET = ((0, 0, 0), (6, 0, 0), (0, 6, 0), (0, 0, 6))


@pytest.mark.parametrize(
    ("first", "second", "expected"),
    [
        ((0, 0, 0), (3, 3, 0), "CASE1"),
        ((3, 3, 0), (0, 0, 0), "CASE1"),
        ((3, 3, 0), None, "CASE1"),
        ((3, 3, 0), (3, 0, 3), "CASE2"),
        ((0, 0, 0), (2, 2, 2), "CASE3"),
        ((2, 2, 2), (0, 0, 0), "CASE3"),
        ((3, 3, 0), (2, 2, 2), "CASE4"),
        ((2, 2, 2), (3, 3, 0), "CASE4"),
        ((2, 2, 2), (2, 1, 3), "CASE5"),
    ],
)
def test_table2_pipel_cases_are_classified_exactly(
    first: object, second: object, expected: str
) -> None:
    result = classify_pipel_type(TET, first, second)

    assert result.accepted, result.reason
    assert result.pipel_case == expected


def test_vertex_edge_and_face_are_not_conflated() -> None:
    assert classify_tet_boundary_position(TET, (0, 0, 0)) == "NOD"
    assert classify_tet_boundary_position(TET, (3, 3, 0)) == "EDG"
    assert classify_tet_boundary_position(TET, (2, 2, 2)) == "FAC"


def test_unsupported_or_nonboundary_cases_fail_closed() -> None:
    unsupported = classify_pipel_type(TET, (0, 0, 0), (0, 6, 0))
    outside = classify_pipel_type(TET, (3, 3, 0), (7, 0, 0))

    assert not unsupported.accepted
    assert unsupported.reason == "unsupported_table2_intersection_pair"
    assert not outside.accepted
    assert outside.reason == "intersection_not_on_tet_boundary"
