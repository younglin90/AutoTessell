"""L1 tests for the unified, fail-closed Chen source-edge incidence record."""

from __future__ import annotations

from core.generator.native_tet.chen_source_edge_incidence_l1 import build_source_edge_incidence


def test_interior_source_edge_has_only_ordered_interior_pipels() -> None:
    points = ((-1, 0, 0), (0, -1, -1), (0, 1, -1), (0, 0, 1), (1, 0, 0))
    result = build_source_edge_incidence(points, ((0, 1, 2, 3), (4, 1, 2, 3)), points[0], points[4])

    assert result.accepted, result.reason
    assert result.incidence is not None
    assert result.incidence.mode == "interior"
    assert tuple(item.parent_index for item in result.incidence.interior_pipels) == (0, 1)
    assert result.incidence.boundary_incidence is None


def test_facet_sided_nod_edg_has_only_unique_facet_ownership() -> None:
    points = ((1, 0, 0), (0, 0, -1), (0, 1, 0), (0, 0, 1), (0, -1, 0))
    result = build_source_edge_incidence(
        points,
        ((0, 1, 2, 3), (0, 1, 3, 4)),
        points[0],
        (0, 0, 0),
    )

    assert result.accepted, result.reason
    assert result.incidence is not None
    assert result.incidence.mode == "boundary_aligned"
    assert not result.incidence.interior_pipels
    assert result.incidence.boundary_incidence is not None
    assert result.incidence.boundary_incidence.face == (0, 1, 3)


def test_edge_aligned_segment_exposes_no_arbitrary_owner() -> None:
    points = ((1, 0, 0), (0, 0, -1), (0, 1, 0), (0, 0, 1), (0, -1, 0))
    result = build_source_edge_incidence(points, ((0, 1, 2, 3), (0, 1, 3, 4)), points[1], points[3])

    assert not result.accepted
    assert result.reason == "boundary_aligned_rejected:segment_is_not_on_one_unique_face"
    assert result.incidence is None


def test_uncovered_edge_does_not_fall_through_to_boundary_mode() -> None:
    points = ((-1, 0, 0), (0, -1, -1), (0, 1, -1), (0, 0, 1), (1, 0, 0))
    result = build_source_edge_incidence(points, ((0, 1, 2, 3),), points[0], points[4])

    assert not result.accepted
    assert result.reason == "interior_rejected:source_edge_has_gap_or_uncovered_endpoint"
    assert result.incidence is None
