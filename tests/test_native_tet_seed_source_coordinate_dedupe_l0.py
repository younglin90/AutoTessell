"""Exact source/grid coordinate-collision filter contracts."""

from __future__ import annotations

from fractions import Fraction

from core.generator.native_tet.seed_source_coordinate_dedupe_l0 import (
    plan_seed_source_coordinate_dedupe_l0,
)


def test_removes_only_exact_source_coordinate_collisions_in_stable_order() -> None:
    result = plan_seed_source_coordinate_dedupe_l0(
        ((0, 0, 0), (1, 0, 0)),
        ((0, 0, 0), (0.5, 0, 0), (1, 0, 0), (0, 1, 0)),
    )
    assert result.accepted
    assert result.kept_grid_indices == (1, 3)
    assert result.removed_grid_indices == (0, 2)
    assert result.filtered_grid_points == (
        (Fraction(1, 2), Fraction(0), Fraction(0)),
        (Fraction(0), Fraction(1), Fraction(0)),
    )
    assert result.source_points_unchanged and result.grid_points_unchanged
    assert not result.production_mesh_changed


def test_empty_source_rejects_without_a_filter_plan() -> None:
    result = plan_seed_source_coordinate_dedupe_l0((), ((0, 0, 0),))
    assert not result.accepted
    assert result.reason == "empty_source_points"
