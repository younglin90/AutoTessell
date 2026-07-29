"""L0 atomic staging tests for exact source-boundary preservation."""

from __future__ import annotations

from core.generator.native_tet.chen_staged_state_l0 import certify_atomic_staged_replacement


def _closed_star() -> tuple[
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
    source_boundary = (
        (0, 1, 2),
        (0, 2, 3),
        (0, 3, 4),
        (0, 1, 4),
        (1, 2, 4),
        (2, 3, 4),
    )
    children = {
        0: ((1, 0, 2, 5), (5, 0, 2, 3)),
        1: ((1, 2, 4, 5), (5, 2, 4, 3)),
        2: ((0, 1, 4, 5), (0, 5, 4, 3)),
    }
    return points, parents, source_boundary, children


def test_atomic_closure_replacement_preserves_exact_boundary_volume_and_source_subedge() -> None:
    points, parents, source_boundary, children = _closed_star()

    result = certify_atomic_staged_replacement(
        points,
        parents,
        source_boundary,
        children,
        required_source_edge=(0, 5),
    )

    assert result.accepted, result.reason
    assert len(result.committed_tets) == 6
    assert result.boundary_preserved
    assert result.volume_preserved
    assert result.all_positive
    assert result.required_source_edge_recovered


def test_partial_staging_is_rejected_when_it_exposes_a_new_boundary() -> None:
    points, parents, source_boundary, children = _closed_star()

    result = certify_atomic_staged_replacement(points, parents, source_boundary, {0: children[0]})

    assert not result.accepted
    assert not result.boundary_preserved
    assert not result.committed_tets


def test_declared_source_boundary_or_degenerate_child_fails_closed() -> None:
    points, parents, source_boundary, children = _closed_star()
    degenerate = {**children, 0: ((1, 0, 2, 5), (0, 0, 2, 3))}

    mismatched = certify_atomic_staged_replacement(points, parents, source_boundary[:-1], children)
    invalid_child = certify_atomic_staged_replacement(points, parents, source_boundary, degenerate)

    assert not mismatched.accepted
    assert mismatched.reason == "declared_source_boundary_mismatch"
    assert not invalid_child.accepted
    assert invalid_child.reason == "invalid_candidate_child"
