"""L0 tests for the documented Table-5 Phi neighbour lookup contract."""

from __future__ import annotations

from core.generator.native_tet.chen_phi_api_l0 import chen_phi_neighbor_lookup


def _table5_neighborhood() -> (
    tuple[tuple[tuple[int, int, int, int], ...], dict[int, tuple[tuple[int, int, int, int], ...]]]
):
    # t0=ABCD.  t1=EBCD is across t0's face BCD (opposite A), and
    # t2=FABD is across face ABD (opposite C).  Both neighbours already hold
    # their Table-5 child lists for P=6 on B-D.
    parents = ((0, 1, 2, 3), (4, 1, 2, 3), (5, 0, 1, 3))
    dectets = {
        1: ((4, 1, 2, 6), (4, 6, 2, 3)),
        2: ((0, 1, 5, 6), (0, 6, 5, 3)),
    }
    return parents, dectets


def test_phi_returns_unique_decomposed_neighbor_child_on_requested_face() -> None:
    parents, dectets = _table5_neighborhood()

    across_a = chen_phi_neighbor_lookup(parents, dectets, 0, 0, (1, 2, 6))
    across_c = chen_phi_neighbor_lookup(parents, dectets, 0, 2, (0, 1, 6))

    assert across_a.resolved and across_a.neighbor_tet == 1
    assert across_a.child_tet == (4, 1, 2, 6)
    assert across_c.resolved and across_c.neighbor_tet == 2
    assert across_c.child_tet == (0, 1, 5, 6)


def test_phi_returns_null_when_neighbor_is_undecomposed_or_exterior() -> None:
    parents, _dectets = _table5_neighborhood()

    undecomposed = chen_phi_neighbor_lookup(parents, {}, 0, 0, (1, 2, 6))
    exterior = chen_phi_neighbor_lookup(parents, {}, 0, 1, (0, 2, 6))

    assert not undecomposed.resolved
    assert undecomposed.reason == "neighbor_pipel_not_decomposed"
    assert not exterior.resolved
    assert exterior.reason == "original_neighbor_is_null"


def test_phi_rejects_faces_outside_the_original_shared_face_or_without_unique_child() -> None:
    parents, dectets = _table5_neighborhood()
    duplicated = {1: ((4, 1, 2, 6), (7, 1, 2, 6))}

    off_shared = chen_phi_neighbor_lookup(parents, dectets, 0, 0, (0, 4, 6))
    ambiguous = chen_phi_neighbor_lookup(parents, duplicated, 0, 0, (1, 2, 6))

    assert not off_shared.resolved
    assert off_shared.reason == "requested_face_not_on_original_shared_face"
    assert not ambiguous.resolved
    assert ambiguous.reason == "requested_face_has_no_unique_neighbor_child"
