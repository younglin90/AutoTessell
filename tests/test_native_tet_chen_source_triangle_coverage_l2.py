"""L2 exact union coverage tests for one immutable source triangle."""

from __future__ import annotations

from core.generator.native_tet.chen_source_triangle_coverage_l2 import (
    certify_source_triangle_coverage_l2,
)


def test_one_parent_that_contains_the_full_source_triangle_passes_exact_coverage() -> None:
    result = certify_source_triangle_coverage_l2(
        ((-2, -2, -1), (2, -2, -1), (0, 2, -1), (0, 0, 2)),
        ((0, 1, 2, 3),),
        ((-1 / 2, -1 / 2, 0), (1 / 2, -1 / 2, 0), (0, 1 / 2, 0)),
    )

    assert result.accepted, result.reason
    assert result.fragment_parent_indices == (0,)
    assert result.candidate_fragment_triangles == 1
    assert result.subdivision is not None and result.subdivision.accepted
    assert result.source_points_unchanged
    assert not result.production_mesh_changed


def test_one_edge_fragment_that_leaves_the_parent_mesh_fails_full_source_coverage() -> None:
    result = certify_source_triangle_coverage_l2(
        ((0, 0, -1), (4, 0, -1), (0, 4, -1), (0, 0, 1)),
        ((0, 1, 2, 3),),
        ((-1, -1, 0), (1, -1, 0), (0, 1, 0)),
    )

    assert not result.accepted
    assert result.reason == "source_fragment_union_failed:source_area_partition_failed"
    assert result.fragment_parent_indices == (0,)
    assert result.candidate_fragment_triangles == 1
    assert result.subdivision is not None and not result.subdivision.accepted
    assert result.source_points_unchanged


def test_overlapping_parent_fragments_fail_instead_of_double_covering_the_source() -> None:
    result = certify_source_triangle_coverage_l2(
        ((-2, -2, -1), (2, -2, -1), (0, 2, -1), (0, 0, 2)),
        ((0, 1, 2, 3), (0, 1, 2, 3)),
        ((-1 / 2, -1 / 2, 0), (1 / 2, -1 / 2, 0), (0, 1 / 2, 0)),
    )

    assert not result.accepted
    assert result.reason == "source_fragment_union_failed:source_area_partition_failed"
    assert result.subdivision is not None and not result.subdivision.accepted


def test_source_triangle_coverage_is_value_identical_on_repeat() -> None:
    points = ((-2, -2, -1), (2, -2, -1), (0, 2, -1), (0, 0, 2))
    parents = ((0, 1, 2, 3),)
    source = ((-1 / 2, -1 / 2, 0), (1 / 2, -1 / 2, 0), (0, 1 / 2, 0))

    assert certify_source_triangle_coverage_l2(points, parents, source) == certify_source_triangle_coverage_l2(
        points, parents, source
    )
