"""Report-only conservative face-2:1 balancing for sparse leaf keys."""

from __future__ import annotations

from dataclasses import dataclass

from .sparse_leaf_partition_l0 import SparseLeafKey, audit_sparse_leaf_partition


@dataclass(frozen=True)
class SparseLeafBalanceWorklistReport:
    """Balanced terminal-key result; never connected to generation."""

    status: str
    initial_leaf_count: int
    final_leaves: tuple[SparseLeafKey, ...]
    refined_leaves: int
    sweeps: int
    balanced_2to1: bool
    topology_ready: bool
    production_octree_changed: bool


def _children(leaf: SparseLeafKey) -> tuple[SparseLeafKey, ...]:
    return tuple(
        SparseLeafKey(leaf.level + 1, 2 * leaf.i + di, 2 * leaf.j + dj, 2 * leaf.k + dk)
        for di in range(2) for dj in range(2) for dk in range(2)
    )


def _face_neighbours(first: SparseLeafKey, second: SparseLeafKey, *, max_level: int) -> bool:
    def interval(leaf: SparseLeafKey, axis: int) -> tuple[int, int]:
        scale = 1 << (max_level - leaf.level)
        coordinate = (leaf.i, leaf.j, leaf.k)[axis]
        return coordinate * scale, (coordinate + 1) * scale

    first_ranges = tuple(interval(first, axis) for axis in range(3))
    second_ranges = tuple(interval(second, axis) for axis in range(3))
    touching_axes = [axis for axis in range(3) if first_ranges[axis][1] == second_ranges[axis][0] or second_ranges[axis][1] == first_ranges[axis][0]]
    if len(touching_axes) != 1:
        return False
    axis = touching_axes[0]
    return all(
        min(first_ranges[other][1], second_ranges[other][1]) > max(first_ranges[other][0], second_ranges[other][0])
        for other in range(3) if other != axis
    )


def balance_sparse_leaf_keys_worklist(
    leaves: tuple[SparseLeafKey, ...], *, root_shape: tuple[int, int, int], max_level: int
) -> SparseLeafBalanceWorklistReport:
    """Refine only coarser face neighbours until diagnostic 2:1 balance holds."""
    if max_level < 0 or min(root_shape) <= 0:
        raise ValueError("root shape and max level must be valid")
    terminal = set(leaves)
    if len(terminal) != len(leaves):
        raise ValueError("terminal leaf keys must be unique")
    initial = len(terminal)
    refined = 0
    sweeps = 0
    while True:
        partition = audit_sparse_leaf_partition(tuple(sorted(terminal)), root_shape=root_shape, max_level=max_level)
        if partition.balanced_2to1:
            return SparseLeafBalanceWorklistReport(
                status="pass_incremental_balanced_leaf_keys", initial_leaf_count=initial,
                final_leaves=tuple(sorted(terminal)), refined_leaves=refined, sweeps=sweeps,
                balanced_2to1=True, topology_ready=False, production_octree_changed=False,
            )
        candidates = {
            first if first.level < second.level else second
            for first in terminal for second in terminal
            if abs(first.level - second.level) > 1 and _face_neighbours(first, second, max_level=max_level)
        }
        if not candidates or any(leaf.level >= max_level for leaf in candidates):
            return SparseLeafBalanceWorklistReport(
                status="reject_incremental_balance_unresolvable", initial_leaf_count=initial,
                final_leaves=tuple(sorted(terminal)), refined_leaves=refined, sweeps=sweeps,
                balanced_2to1=False, topology_ready=False, production_octree_changed=False,
            )
        for leaf in candidates:
            terminal.remove(leaf)
            terminal.update(_children(leaf))
        refined += len(candidates)
        sweeps += 1
