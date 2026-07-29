"""Read-only exact filter for grid seeds duplicating an input source vertex."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from fractions import Fraction

from core.generator.native_tet.chen_penetration_l0 import _point

Point = tuple[Fraction, Fraction, Fraction]


@dataclass(frozen=True)
class SeedSourceCoordinateDedupeL0:
    """Stable grid-filter plan; callers choose whether to apply it later."""

    accepted: bool
    reason: str
    filtered_grid_points: tuple[Point, ...]
    kept_grid_indices: tuple[int, ...]
    removed_grid_indices: tuple[int, ...]
    source_points_unchanged: bool
    grid_points_unchanged: bool
    production_mesh_changed: bool


def plan_seed_source_coordinate_dedupe_l0(
    source_points: Sequence[Sequence[float | int | Fraction]],
    grid_points: Sequence[Sequence[float | int | Fraction]],
) -> SeedSourceCoordinateDedupeL0:
    """Filter only exact grid/source coordinate collisions in stable order."""
    source = tuple(_point(point) for point in source_points)
    grid = tuple(_point(point) for point in grid_points)
    if not source:
        return SeedSourceCoordinateDedupeL0(
            False, "empty_source_points", (), (), (), True, True, False
        )
    source_keys = set(source)
    kept = tuple(index for index, point in enumerate(grid) if point not in source_keys)
    removed = tuple(index for index, point in enumerate(grid) if point in source_keys)
    unchanged_source = source == tuple(_point(point) for point in source_points)
    unchanged_grid = grid == tuple(_point(point) for point in grid_points)
    return SeedSourceCoordinateDedupeL0(
        unchanged_source and unchanged_grid,
        "accepted" if unchanged_source and unchanged_grid else "input_points_changed",
        tuple(grid[index] for index in kept),
        kept,
        removed,
        unchanged_source,
        unchanged_grid,
        False,
    )
