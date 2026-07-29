"""L1 exact source-edge ownership tests; no connectivity is changed."""

from __future__ import annotations

from fractions import Fraction

from core.generator.native_tet.chen_source_edge_worklist_l1 import build_source_edge_pipel_worklist


def test_source_edge_has_ordered_gap_free_nod_fac_then_fac_nod_pipels() -> None:
    # Two tetrahedra share BCD.  The missing edge A--E crosses the shared face
    # at its strict interior, so the two pipels are NOD_FAC and FAC_NOD.
    points = (
        (-1, 0, 0),  # A
        (0, -1, -1),  # B
        (0, 1, -1),  # C
        (0, 0, 1),  # D
        (1, 0, 0),  # E
    )
    result = build_source_edge_pipel_worklist(
        points, ((0, 1, 2, 3), (4, 1, 2, 3)), points[0], points[4]
    )

    assert result.accepted, result.reason
    assert tuple(pipel.parent_index for pipel in result.pipels) == (0, 1)
    assert tuple(pipel.pipel_type.pipel_case for pipel in result.pipels) == ("CASE3", "CASE3")
    assert result.pipels[0].exit_parameter == result.pipels[1].entry_parameter == Fraction(1, 2)


def test_boundary_aligned_nod_edg_segment_is_not_misreported_as_an_interior_pipel() -> None:
    points = ((2, 0, 0), (0, 0, -1), (0, 2, 0), (0, 0, 1))
    # A to the midpoint of B-D lies in parent face ABD, rather than crossing
    # the tetrahedron interior.  It needs a separate boundary-aligned route.
    result = build_source_edge_pipel_worklist(points, ((0, 1, 2, 3),), points[0], (0, 0, 0))

    assert not result.accepted
    assert result.reason == "cofacial_or_noninterior_pipel_segment"
    assert not result.pipels


def test_uncovered_source_tail_rejects_without_a_partial_worklist() -> None:
    points = ((-1, 0, 0), (0, -1, -1), (0, 1, -1), (0, 0, 1), (1, 0, 0))
    result = build_source_edge_pipel_worklist(points, ((0, 1, 2, 3),), points[0], points[4])

    assert not result.accepted
    assert result.reason == "source_edge_has_gap_or_uncovered_endpoint"
