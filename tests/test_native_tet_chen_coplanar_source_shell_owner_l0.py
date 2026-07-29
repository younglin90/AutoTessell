"""L0 exact owner/side tests for coplanar source-plane subfaces."""

from __future__ import annotations

from core.generator.native_tet.chen_coplanar_source_shell_owner_l0 import (
    audit_coplanar_source_shell_owner_l0,
)


_SOURCE = ((0, 0, 0), (1, 0, 0), (0, 1, 0))


def test_one_coplanar_owner_side_is_accepted_without_interior_label() -> None:
    result = audit_coplanar_source_shell_owner_l0(
        ((0, 0, 0), (1, 0, 0), (0, 1, 0), (0, 0, -1)),
        ((0, 1, 2, 3),),
        _SOURCE,
    )

    assert result.accepted, result.reason
    assert result.reason == "accepted_one_sided_negative"
    assert result.selected_side == -1
    assert len(result.owners) == 1
    assert result.negative_coverage is not None and result.negative_coverage.accepted
    assert result.positive_coverage is None
    assert result.source_points_unchanged
    assert not result.production_mesh_changed


def test_two_opposite_coplanar_owners_are_an_internal_sheet_not_a_boundary() -> None:
    result = audit_coplanar_source_shell_owner_l0(
        ((0, 0, 0), (1, 0, 0), (0, 1, 0), (0, 0, -1), (0, 0, 1)),
        ((0, 1, 2, 3), (0, 2, 1, 4)),
        _SOURCE,
    )

    assert not result.accepted
    assert result.reason == "two_sided_coplanar_shell"
    assert result.selected_side is None
    assert result.positive_coverage is not None and result.positive_coverage.accepted
    assert result.negative_coverage is not None and result.negative_coverage.accepted


def test_owner_side_audit_is_value_identical_on_repeat() -> None:
    args = (
        ((0, 0, 0), (1, 0, 0), (0, 1, 0), (0, 0, -1)),
        ((0, 1, 2, 3),),
        _SOURCE,
    )
    assert audit_coplanar_source_shell_owner_l0(*args) == audit_coplanar_source_shell_owner_l0(*args)
