"""L0 exact certificate for the minimal Chen-compatible pipe cluster."""

from __future__ import annotations

from fractions import Fraction

from core.generator.native_tet.chen_pipe_cluster_l0 import certify_swap23_pipe_cluster


def _positive_cluster() -> (
    tuple[tuple[tuple[float, float, float], ...], tuple[tuple[int, int, int, int], ...]]
):
    points = (
        (0.0, 0.0, 0.0),
        (1.0, 0.0, 0.0),
        (0.0, 1.0, 0.0),
        (0.2, 0.2, 1.0),
        (0.3, 0.3, -1.0),
    )
    return points, ((0, 1, 2, 3), (0, 2, 1, 4))


def test_swap23_recovers_missing_pipe_edge_with_exact_local_contracts() -> None:
    points, parents = _positive_cluster()

    result = certify_swap23_pipe_cluster(points, parents, (3, 4))

    assert result.accepted, result.reason
    assert result.recovered_source_edge
    assert result.external_boundary_preserved
    assert result.parent_volume6 == result.replacement_volume6 == Fraction(2)
    assert len(result.replacement_tets) == 3


def test_outside_shared_face_crossing_rejects_without_replacement() -> None:
    points, parents = _positive_cluster()
    outside_points = points[:3] + ((2.0, 2.0, 1.0), (2.0, 2.0, -1.0))

    result = certify_swap23_pipe_cluster(outside_points, parents, (3, 4))

    assert not result.accepted
    assert result.reason == "source_edge_must_cross_shared_face_strictly"
    assert not result.replacement_tets


def test_nonadjacent_parent_pair_rejects_without_replacement() -> None:
    points, _parents = _positive_cluster()
    nonadjacent_points = points + ((1.0, 1.0, 1.0),)
    nonadjacent = ((0, 1, 2, 3), (0, 1, 4, 5))

    result = certify_swap23_pipe_cluster(nonadjacent_points, nonadjacent, (2, 4))

    assert not result.accepted
    assert result.reason == "parents_do_not_share_one_face"
    assert not result.replacement_tets


def test_pipe_certificate_is_value_identical_on_repeat() -> None:
    points, parents = _positive_cluster()

    assert certify_swap23_pipe_cluster(points, parents, (3, 4)) == certify_swap23_pipe_cluster(
        points, parents, (3, 4)
    )
