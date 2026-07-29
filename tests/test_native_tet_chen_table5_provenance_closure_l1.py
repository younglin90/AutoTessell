"""L1 tests for exact source-owner plus Table-5 Phi provenance closure."""

from __future__ import annotations

from core.generator.native_tet.chen_table5_provenance_closure_l1 import (
    certify_table5_provenance_closure,
)


def _local_neighborhood() -> tuple[
    tuple[tuple[int, int, int], ...],
    dict[int, tuple[int, int, int, int]],
    tuple[tuple[int, int, int], ...],
    dict[int, tuple[tuple[int, int, int, int], ...]],
]:
    points = (
        (2, 0, 0),
        (0, 0, -1),
        (-1, 2, 0),
        (0, 0, 1),
        (-1, -2, 0),
        (0, 0, 0),
    )
    parents = {0: (0, 1, 2, 3), 1: (2, 1, 4, 3), 2: (4, 1, 0, 3)}
    source_boundary = ((0, 1, 2), (0, 2, 3), (0, 3, 4), (0, 1, 4), (1, 2, 4), (2, 3, 4))
    children: dict[int, tuple[tuple[int, int, int, int], ...]] = {
        0: ((1, 0, 2, 5), (5, 0, 2, 3)),
        1: ((1, 2, 4, 5), (5, 2, 4, 3)),
        2: ((0, 1, 4, 5), (0, 5, 4, 3)),
    }
    return points, parents, source_boundary, children


def test_table5_candidates_equal_source_owner_plus_phi_closure() -> None:
    points, parents, source_boundary, children = _local_neighborhood()
    result = certify_table5_provenance_closure(
        points,
        parents,
        source_boundary,
        children,
        target_parent=0,
        source_node=0,
        cut_edge=(1, 3),
        intersection_point=5,
    )

    assert result.accepted, result.reason
    assert result.authorized_parent_ids == (0, 1, 2)
    assert result.transaction is not None
    assert result.transaction.staged_commit is not None
    assert result.transaction.staged_commit.boundary_preserved


def test_unrelated_active_parent_cannot_be_silently_replaced() -> None:
    points, parents, source_boundary, children = _local_neighborhood()
    expanded_points = (*points, (10, 0, 0), (11, 0, 0), (10, 1, 0), (10, 0, 1))
    expanded_parents = {**parents, 3: (6, 7, 8, 9)}
    expanded_boundary = (
        *source_boundary,
        (6, 7, 8),
        (6, 7, 9),
        (6, 8, 9),
        (7, 8, 9),
    )
    expanded_children = {**children, 3: ((6, 7, 8, 9),)}

    result = certify_table5_provenance_closure(
        expanded_points,
        expanded_parents,
        expanded_boundary,
        expanded_children,
        target_parent=0,
        source_node=0,
        cut_edge=(1, 3),
        intersection_point=5,
    )

    assert not result.accepted
    assert result.reason == "candidate_parent_set_not_exact_phi_closure"
    assert not result.authorized_parent_ids
    assert result.transaction is None
