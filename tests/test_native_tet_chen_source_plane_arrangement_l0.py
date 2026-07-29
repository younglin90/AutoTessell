"""L0 source-plane arrangement tests; no recovery connectivity is changed."""

from __future__ import annotations

from core.generator.native_tet.chen_source_plane_arrangement_l0 import (
    build_source_plane_arrangement_l0,
)


def test_one_thr_clusterel_is_a_literal_template_ready_arrangement() -> None:
    # The z=0 section of this tet is exactly the source triangle.  Its three
    # apex-to-base edges cut the source interior, producing Chen THR_EDG.
    result = build_source_plane_arrangement_l0(
        ((-2, -2, -1), (2, -2, -1), (0, 2, -1), (0, 0, 1)),
        ((0, 1, 2, 3),),
        ((-1, -1, 0), (1, -1, 0), (0, 1, 0)),
    )

    assert result.accepted, result.reason
    assert result.reason == "accepted_literal_template_arrangement"
    assert result.components == ((0,),)
    assert result.boundary_segment_count == 3
    assert result.internal_segment_count == 0
    assert result.fragments[0].clusterel_type == "THR_EDG"
    assert result.literal_template_ready
    assert result.coverage is not None and result.coverage.accepted
    assert result.source_points_unchanged
    assert not result.production_mesh_changed


def test_partial_source_coverage_is_rejected_before_template_selection() -> None:
    result = build_source_plane_arrangement_l0(
        ((0, 0, -1), (4, 0, -1), (0, 4, -1), (0, 0, 1)),
        ((0, 1, 2, 3),),
        ((-1, -1, 0), (1, -1, 0), (0, 1, 0)),
    )

    assert not result.accepted
    assert result.reason == "source_coverage_failed:source_fragment_union_failed:source_area_partition_failed"
    assert not result.literal_template_ready


def test_arrangement_is_value_identical_on_repeat() -> None:
    args = (
        ((-2, -2, -1), (2, -2, -1), (0, 2, -1), (0, 0, 1)),
        ((0, 1, 2, 3),),
        ((-1, -1, 0), (1, -1, 0), (0, 1, 0)),
    )

    assert build_source_plane_arrangement_l0(*args) == build_source_plane_arrangement_l0(*args)
