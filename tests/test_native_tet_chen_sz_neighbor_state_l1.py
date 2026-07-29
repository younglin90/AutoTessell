"""L1 exact parent-face DType ledger tests."""

from __future__ import annotations

from core.generator.native_tet.chen_sz_neighbor_state_l1 import (
    eligible_sz_types_from_parent_state_l1,
)

_PARENTS = ((0, 1, 2, 3), (4, 1, 2, 3))
_SHARED = (1, 2, 3)


def test_actual_decomposed_neighbour_face_forces_the_opposite_sz_type() -> None:
    result = eligible_sz_types_from_parent_state_l1(
        _PARENTS,
        {(1, _SHARED): "S"},
        tet_index=0,
        opposite_vertex=0,
    )

    assert result.accepted, result.reason
    assert result.shared_parent_face == _SHARED
    assert result.neighbour_tet == 1
    assert result.choice is not None
    assert result.choice.eligible_types == {"Z"}
    assert result.choice.forced_by_neighbour
    assert not result.production_mesh_changed


def test_missing_dtype_for_real_neighbour_keeps_both_types_explicitly_eligible() -> None:
    result = eligible_sz_types_from_parent_state_l1(
        _PARENTS,
        {},
        tet_index=0,
        opposite_vertex=0,
    )

    assert result.accepted, result.reason
    assert result.choice is not None
    assert result.choice.eligible_types == {"S", "Z"}
    assert not result.choice.forced_by_neighbour


def test_dtype_cannot_be_attached_to_an_unowned_or_nonexistent_parent_face() -> None:
    result = eligible_sz_types_from_parent_state_l1(
        _PARENTS,
        {(1, (0, 1, 4)): "S"},
        tet_index=0,
        opposite_vertex=0,
    )

    assert not result.accepted
    assert result.reason == "dtype_record_not_on_parent_face"
    assert result.choice is None
