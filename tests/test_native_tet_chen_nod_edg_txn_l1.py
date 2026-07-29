"""L1 local NOD_EDG transaction tests; no production recovery is invoked."""

from __future__ import annotations

from core.generator.native_tet.chen_nod_edg_txn_l1 import certify_local_nod_edg_transaction


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


def test_local_nod_edg_table5_transaction_is_atomic_and_boundary_preserving() -> None:
    points, parents, source_boundary, children = _local_neighborhood()

    result = certify_local_nod_edg_transaction(
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
    assert len(result.target_children) == 2
    assert all(phi.resolved for phi in result.phi_results)
    assert result.staged_commit is not None and result.staged_commit.boundary_preserved
    assert result.source_incidence is not None
    assert result.source_incidence.mode == "boundary_aligned"
    assert result.source_incidence.boundary_incidence is not None
    assert result.source_incidence.boundary_incidence.owner_tets == (0, 2)


def test_nod_edg_rejects_an_intersection_not_on_the_declared_cut_edge() -> None:
    points, parents, source_boundary, children = _local_neighborhood()
    points_off_edge = (*points, (1, 1, 1))

    result = certify_local_nod_edg_transaction(
        points_off_edge,
        parents,
        source_boundary,
        children,
        target_parent=0,
        source_node=0,
        cut_edge=(1, 3),
        intersection_point=6,
    )

    assert not result.accepted
    assert result.reason == "target_is_not_table5_nod_edg"
    assert not result.target_children


def test_nod_edg_rejects_partial_candidate_even_when_local_table5_children_match() -> None:
    points, parents, source_boundary, children = _local_neighborhood()
    partial = {0: children[0]}

    result = certify_local_nod_edg_transaction(
        points,
        parents,
        source_boundary,
        partial,
        target_parent=0,
        source_node=0,
        cut_edge=(1, 3),
        intersection_point=5,
    )

    assert not result.accepted
    assert result.reason == "boundary_aligned_owner_children_missing"
    assert not result.target_children


def test_nod_edg_phi_uses_parent_positions_not_external_parent_ids() -> None:
    points, parents, source_boundary, children = _local_neighborhood()
    parent_ids = (10, 30, 70)
    remapped_parents = {
        new_id: parents[old_id] for new_id, old_id in zip(parent_ids, sorted(parents), strict=True)
    }
    remapped_children = {
        new_id: children[old_id]
        for new_id, old_id in zip(parent_ids, sorted(children), strict=True)
    }

    result = certify_local_nod_edg_transaction(
        points,
        remapped_parents,
        source_boundary,
        remapped_children,
        target_parent=10,
        source_node=0,
        cut_edge=(1, 3),
        intersection_point=5,
    )

    assert result.accepted, result.reason
    assert all(phi.resolved for phi in result.phi_results)
