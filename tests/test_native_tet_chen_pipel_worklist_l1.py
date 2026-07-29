"""L1 exact traversal tests; no production CDT recovery is exercised."""

from __future__ import annotations

from fractions import Fraction

from core.generator.native_tet.chen_pipel_worklist_l1 import certify_source_edge_pipel_traversal


def _three_tet_pipe() -> (
    tuple[tuple[tuple[int, int, int], ...], tuple[tuple[int, int, int, int], ...]]
):
    # t0/t1 share BCD and t1/t2 share ECD.  The source segment passes through
    # strict interior points of both shared faces, not a face edge or vertex.
    points = (
        (-1, -1, -2),  # A
        (0, -3, -3),  # B
        (0, 3, -3),  # C
        (0, 0, 3),  # D
        (3, 0, 0),  # E
        (2, 2, 1),  # F
    )
    return points, ((0, 1, 2, 3), (4, 1, 2, 3), (5, 4, 2, 3))


def test_source_edge_walks_a_unique_three_tet_pipel_without_mutation() -> None:
    points, tets = _three_tet_pipe()

    result = certify_source_edge_pipel_traversal(
        points,
        tets,
        (Fraction(-1, 2), Fraction(-1, 2), Fraction(-3, 2)),
        (Fraction(3, 2), Fraction(3, 2), Fraction(1, 2)),
    )

    assert result.accepted, result.reason
    assert result.visited_tets == (0, 1, 2)
    assert len(result.crossed_faces) == 2
    assert result.crossing_parameters[0] < result.crossing_parameters[1]
    assert result.input_boundary_unchanged


def test_source_edge_rejects_a_face_edge_crossing_as_ambiguous() -> None:
    points, tets = _three_tet_pipe()

    result = certify_source_edge_pipel_traversal(points, tets, (-1, 0, 0), (2, 0, 0))

    assert not result.accepted
    assert result.reason in {
        "traversal_does_not_reach_end_owner",
        "source_endpoints_must_have_unique_interior_owner",
    }
    assert not result.visited_tets


def test_source_edge_rejects_when_end_owner_is_not_reached() -> None:
    points, tets = _three_tet_pipe()

    result = certify_source_edge_pipel_traversal(points, tets, (-1, -1, -2), (2, 2, 1))

    assert not result.accepted
    assert result.reason == "source_endpoints_must_have_unique_interior_owner"
