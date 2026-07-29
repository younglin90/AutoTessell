"""Budgeted, report-only conventional strong-pairing refinement worklist."""

from __future__ import annotations

from dataclasses import dataclass

from .sparse_leaf_partition_l0 import SparseLeafKey
from .sparse_pairing_l0 import audit_sparse_octree_pairing


@dataclass(frozen=True)
class SparsePairingWorklistReport:
    """Result of sibling-completion refinement, disconnected from generation."""

    status: str
    initial_leaf_count: int
    final_leaves: tuple[SparseLeafKey, ...]
    refined_terminal_leaves: int
    sweeps: int
    final_unpaired_parent_count: int
    topology_ready: bool
    production_octree_changed: bool


def _mixed_parent_direct_children(
    leaves: tuple[SparseLeafKey, ...], *, max_level: int
) -> tuple[SparseLeafKey, ...]:
    """Return direct terminal children that must refine to complete sibling sets."""
    terminal = set(leaves)
    to_refine: set[SparseLeafKey] = set()
    for leaf in leaves:
        for parent_level in range(leaf.level):
            scale = 1 << (leaf.level - parent_level)
            parent = SparseLeafKey(
                parent_level,
                leaf.i // scale,
                leaf.j // scale,
                leaf.k // scale,
            )
            if leaf.level != parent_level + 1:
                continue
            direct_children = tuple(
                SparseLeafKey(
                    parent_level + 1,
                    2 * parent.i + di,
                    2 * parent.j + dj,
                    2 * parent.k + dk,
                )
                for di in range(2)
                for dj in range(2)
                for dk in range(2)
            )
            if not all(child in terminal for child in direct_children):
                to_refine.add(leaf)
    return tuple(sorted(to_refine))


def _children(leaf: SparseLeafKey) -> tuple[SparseLeafKey, ...]:
    return tuple(
        SparseLeafKey(leaf.level + 1, 2 * leaf.i + di, 2 * leaf.j + dj, 2 * leaf.k + dk)
        for di in range(2)
        for dj in range(2)
        for dk in range(2)
    )


def pair_sparse_leaf_keys_worklist(
    leaves: tuple[SparseLeafKey, ...],
    *,
    max_level: int,
    leaf_budget: int,
) -> SparsePairingWorklistReport:
    """Refine direct siblings until conventional strong pairing or a safe refusal."""
    if max_level < 0 or leaf_budget <= 0:
        raise ValueError("max level and leaf budget must be positive")
    terminal = set(leaves)
    if len(terminal) != len(leaves):
        raise ValueError("terminal leaf keys must be unique")
    if any(leaf.level < 0 or leaf.level > max_level for leaf in terminal):
        raise ValueError("leaf levels must lie inside the bounded audit depth")
    initial_count = len(terminal)
    refined = 0
    sweeps = 0
    while True:
        report = audit_sparse_octree_pairing(tuple(sorted(terminal)), max_level=max_level)
        if report.unpaired_parent_count == 0:
            return SparsePairingWorklistReport(
                status="pass_strong_octree_pairing_worklist",
                initial_leaf_count=initial_count,
                final_leaves=tuple(sorted(terminal)),
                refined_terminal_leaves=refined,
                sweeps=sweeps,
                final_unpaired_parent_count=0,
                topology_ready=False,
                production_octree_changed=False,
            )
        candidates = _mixed_parent_direct_children(tuple(sorted(terminal)), max_level=max_level)
        if not candidates or any(leaf.level >= max_level for leaf in candidates):
            return SparsePairingWorklistReport(
                status="reject_strong_pairing_unresolvable",
                initial_leaf_count=initial_count,
                final_leaves=tuple(sorted(terminal)),
                refined_terminal_leaves=refined,
                sweeps=sweeps,
                final_unpaired_parent_count=report.unpaired_parent_count,
                topology_ready=False,
                production_octree_changed=False,
            )
        projected = len(terminal) + 7 * len(candidates)
        if projected > leaf_budget:
            return SparsePairingWorklistReport(
                status="reject_strong_pairing_leaf_budget",
                initial_leaf_count=initial_count,
                final_leaves=tuple(sorted(terminal)),
                refined_terminal_leaves=refined,
                sweeps=sweeps,
                final_unpaired_parent_count=report.unpaired_parent_count,
                topology_ready=False,
                production_octree_changed=False,
            )
        for leaf in candidates:
            terminal.remove(leaf)
            terminal.update(_children(leaf))
        refined += len(candidates)
        sweeps += 1
