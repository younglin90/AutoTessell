"""L0 contracts for Si--Gärtner-style missing-source-subface planning."""

from __future__ import annotations

from core.generator.native_tet.chen_source_missing_region_plan_l0 import (
    plan_source_missing_region_l0,
)


def _two_sided_hole() -> (
    tuple[tuple[tuple[int, int, int], ...], tuple[tuple[int, int, int, int], ...]]
):
    points = (
        (0, 0, 0),
        (2, 0, 0),
        (0, 2, 0),
        (1, 0, 0),
        (0, 0, 1),
        (2, 2, 2),
        (0, 0, -1),
        (2, 2, -2),
    )
    tets = (
        (0, 3, 4, 5),
        (3, 1, 4, 5),
        (1, 2, 4, 5),
        (2, 0, 4, 5),
        (0, 3, 6, 7),
        (3, 1, 6, 7),
        (1, 2, 6, 7),
        (2, 0, 6, 7),
    )
    return points, tets


def test_plan_accepts_exact_one_sided_two_subface_hole_without_mesh_mutation() -> None:
    points, tets = _two_sided_hole()
    result = plan_source_missing_region_l0(
        points,
        (0, 1, 2),
        ((0, 3, 2), (3, 1, 2)),
        tets,
        positive_shell_owner_ids=(0, 1, 2, 3),
        negative_shell_owner_ids=(),
    )
    assert result.accepted
    assert result.reason == "accepted"
    assert result.missing_interior_edges == ((2, 3),)
    assert result.selected_side == 1
    assert result.source_points_unchanged and not result.production_mesh_changed


def test_plan_rejects_an_already_recovered_interior_subface_edge() -> None:
    points, tets = _two_sided_hole()
    result = plan_source_missing_region_l0(
        points,
        (0, 1, 2),
        ((0, 3, 2), (3, 1, 2)),
        (*tets, (2, 3, 4, 5)),
        positive_shell_owner_ids=(0, 1, 2, 3),
        negative_shell_owner_ids=(),
    )
    assert not result.accepted
    assert result.reason == "interior_subface_edge_already_present"


def test_plan_rejects_overlapping_or_wrong_side_owner_sets() -> None:
    points, tets = _two_sided_hole()
    overlap = plan_source_missing_region_l0(
        points,
        (0, 1, 2),
        ((0, 3, 2), (3, 1, 2)),
        tets,
        positive_shell_owner_ids=(0,),
        negative_shell_owner_ids=(0,),
    )
    wrong_side = plan_source_missing_region_l0(
        points,
        (0, 1, 2),
        ((0, 3, 2), (3, 1, 2)),
        tets,
        positive_shell_owner_ids=(4,),
        negative_shell_owner_ids=(5,),
    )
    assert overlap.reason == "invalid_or_overlapping_cavity_owners"
    assert wrong_side.reason == "cavity_owner_not_strictly_one_sided"


def test_plan_rejects_two_sided_source_shell() -> None:
    points, tets = _two_sided_hole()
    result = plan_source_missing_region_l0(
        points,
        (0, 1, 2),
        ((0, 3, 2), (3, 1, 2)),
        tets,
        positive_shell_owner_ids=(0, 1, 2, 3),
        negative_shell_owner_ids=(4, 5, 6, 7),
    )
    assert not result.accepted
    assert result.reason == "two_sided_source_shell"


def test_plan_accepts_a_single_missing_subface_region() -> None:
    points = (
        (0, 0, 0),
        (2, 0, 0),
        (0, 2, 0),
        (0, 0, 1),
        (2, 2, 2),
    )
    tets = ((0, 1, 3, 4), (1, 2, 3, 4), (2, 0, 3, 4))
    result = plan_source_missing_region_l0(
        points,
        (0, 1, 2),
        ((0, 1, 2),),
        tets,
        positive_shell_owner_ids=(0, 1, 2),
        negative_shell_owner_ids=(),
    )
    assert result.accepted
    assert result.missing_interior_edges == ()
