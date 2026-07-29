"""Report-only strong octree-pairing census for sparse terminal leaves.

Pitzalis et al. (2021) distinguish 2:1 balancing from pairing.  This module
measures the conventional octree-pairing precondition only: at every parent,
its eight immediate child regions must be either all terminal or all refined.
It neither refines leaves nor claims the generalized ILP pairing condition.
"""

from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import dataclass

from .sparse_leaf_partition_l0 import SparseLeafKey


@dataclass(frozen=True)
class SparsePairingReport:
    """Census of conventional all-siblings-refined octree pairing."""

    status: str
    parent_count: int
    paired_parent_count: int
    unpaired_parent_count: int
    refined_child_mask_histogram: dict[int, int]
    first_unpaired_parent: SparseLeafKey | None
    first_unpaired_refined_child_mask: int | None
    topology_ready: bool
    production_octree_changed: bool


def _child_bit(child: SparseLeafKey, parent: SparseLeafKey) -> int:
    """Encode an immediate child position of ``parent`` in an octant mask."""
    return (child.i - 2 * parent.i) + 2 * (child.j - 2 * parent.j) + 4 * (child.k - 2 * parent.k)


def audit_sparse_octree_pairing(
    leaves: tuple[SparseLeafKey, ...], *, max_level: int
) -> SparsePairingReport:
    """Measure the sibling-refinement condition without changing the partition."""
    if max_level < 0 or any(leaf.level < 0 or leaf.level > max_level for leaf in leaves):
        raise ValueError("leaf levels must lie inside the bounded audit depth")
    child_states: dict[SparseLeafKey, dict[int, bool]] = defaultdict(dict)
    for leaf in leaves:
        for parent_level in range(leaf.level):
            parent_scale = 1 << (leaf.level - parent_level)
            child_scale = parent_scale // 2
            parent = SparseLeafKey(
                parent_level,
                leaf.i // parent_scale,
                leaf.j // parent_scale,
                leaf.k // parent_scale,
            )
            child = SparseLeafKey(
                parent_level + 1,
                leaf.i // child_scale,
                leaf.j // child_scale,
                leaf.k // child_scale,
            )
            bit = _child_bit(child, parent)
            is_refined = leaf.level > parent_level + 1
            previous = child_states[parent].get(bit)
            if previous is not None and previous != is_refined:
                raise ValueError("terminal leaves cannot overlap a child region")
            child_states[parent][bit] = is_refined

    masks: Counter[int] = Counter()
    unpaired: list[tuple[SparseLeafKey, int]] = []
    for parent, states in child_states.items():
        if len(states) != 8:
            raise ValueError("complete sparse partition must cover every parent child")
        mask = sum(1 << bit for bit, refined in states.items() if refined)
        masks[mask] += 1
        if mask not in (0, 0xFF):
            unpaired.append((parent, mask))
    unpaired.sort()
    return SparsePairingReport(
        status=("pass_strong_octree_pairing" if not unpaired else "reject_strong_octree_pairing"),
        parent_count=len(child_states),
        paired_parent_count=len(child_states) - len(unpaired),
        unpaired_parent_count=len(unpaired),
        refined_child_mask_histogram=dict(sorted(masks.items())),
        first_unpaired_parent=unpaired[0][0] if unpaired else None,
        first_unpaired_refined_child_mask=unpaired[0][1] if unpaired else None,
        topology_ready=False,
        production_octree_changed=False,
    )
