"""L1 exact facet ownership tests for boundary-aligned Chen source segments."""

from __future__ import annotations

from core.generator.native_tet.chen_boundary_aligned_l1 import (
    classify_boundary_aligned_source_segment,
)


def test_nod_edg_segment_is_owned_by_its_shared_facet_and_two_tets() -> None:
    # Face A-B-D is shared by tetrahedra on opposite y sides.  A to the
    # midpoint of B-D lies in the strict interior of that facet.
    points = ((1, 0, 0), (0, 0, -1), (0, 1, 0), (0, 0, 1), (0, -1, 0))
    result = classify_boundary_aligned_source_segment(
        points,
        ((0, 1, 2, 3), (0, 1, 3, 4)),
        points[0],
        (0, 0, 0),
    )

    assert result.accepted, result.reason
    assert result.incidence is not None
    assert result.incidence.face == (0, 1, 3)
    assert result.incidence.owner_tets == (0, 1)
    assert tuple(item.pipel_case for item in result.incidence.owner_pipel_types) == (
        "CASE1",
        "CASE1",
    )


def test_edge_aligned_segment_is_ambiguous_across_multiple_tet_faces() -> None:
    points = ((1, 0, 0), (0, 0, -1), (0, 1, 0), (0, 0, 1), (0, -1, 0))
    result = classify_boundary_aligned_source_segment(
        points,
        ((0, 1, 2, 3), (0, 1, 3, 4)),
        points[1],
        points[3],
    )

    assert not result.accepted
    assert result.reason == "segment_is_not_on_one_unique_face"


def test_interior_segment_is_not_relabelled_as_boundary_aligned() -> None:
    points = ((-1, 0, 0), (0, -1, -1), (0, 1, -1), (0, 0, 1), (1, 0, 0))
    result = classify_boundary_aligned_source_segment(
        points,
        ((0, 1, 2, 3), (4, 1, 2, 3)),
        points[0],
        points[4],
    )

    assert not result.accepted
    assert result.reason == "source_segment_not_boundary_aligned"
