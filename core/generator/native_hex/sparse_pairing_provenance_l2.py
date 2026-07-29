"""Report-only interleaved strong-pairing, 2:1, and SAT provenance recovery."""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass

import numpy as np

from .sparse_leaf_balance_worklist_l0 import balance_sparse_leaf_keys_worklist
from .sparse_leaf_partition_l0 import SparseLeafKey
from .sparse_mesh_balance_l1 import classify_sparse_mesh_leaf_keys
from .sparse_pairing_l0 import audit_sparse_octree_pairing
from .sparse_pairing_worklist_l1 import pair_sparse_leaf_keys_worklist
from .sparse_partition_provenance_l1 import SparseProvenanceLeaf


@dataclass(frozen=True)
class SparsePairingProvenanceReport:
    """A fully reclassified, paired-and-balanced sparse leaf report."""

    status: str
    initial_leaves: int
    final_leaves: tuple[SparseProvenanceLeaf, ...]
    pairing_refined_terminal_leaves: int
    balance_refined_parent_leaves: int
    interleave_sweeps: int
    final_pairing_status: str
    final_balance_status: str
    provenance_histogram: dict[str, int]
    reclassified_leaves: int
    topology_ready: bool
    production_octree_changed: bool


def interleave_pair_balance_leaf_keys(
    leaves: tuple[SparseLeafKey, ...],
    *,
    root_shape: tuple[int, int, int],
    max_level: int,
    leaf_budget: int,
    max_sweeps: int = 8,
) -> tuple[str, tuple[SparseLeafKey, ...], int, int, int, str, str]:
    """Interleave conventional pairing and face-2:1 balance to a fixed point."""
    if max_sweeps <= 0:
        raise ValueError("max sweeps must be positive")
    keys = tuple(sorted(leaves))
    pairing_refined = 0
    balance_refined = 0
    for sweep in range(1, max_sweeps + 1):
        pairing = pair_sparse_leaf_keys_worklist(keys, max_level=max_level, leaf_budget=leaf_budget)
        pairing_refined += pairing.refined_terminal_leaves
        if pairing.status != "pass_strong_octree_pairing_worklist":
            return (
                pairing.status,
                keys,
                pairing_refined,
                balance_refined,
                sweep,
                pairing.status,
                "not_run",
            )
        balanced = balance_sparse_leaf_keys_worklist(
            pairing.final_leaves, root_shape=root_shape, max_level=max_level
        )
        balance_refined += balanced.refined_leaves
        if not balanced.balanced_2to1 or len(balanced.final_leaves) > leaf_budget:
            return (
                (
                    "reject_pair_balance_leaf_budget"
                    if len(balanced.final_leaves) > leaf_budget
                    else balanced.status
                ),
                keys,
                pairing_refined,
                balance_refined,
                sweep,
                pairing.status,
                balanced.status,
            )
        keys = balanced.final_leaves
        final_pairing = audit_sparse_octree_pairing(keys, max_level=max_level)
        if final_pairing.unpaired_parent_count == 0:
            return (
                "pass_interleaved_pair_balance",
                keys,
                pairing_refined,
                balance_refined,
                sweep,
                final_pairing.status,
                balanced.status,
            )
    return (
        "reject_pair_balance_sweep_budget",
        keys,
        pairing_refined,
        balance_refined,
        max_sweeps,
        audit_sparse_octree_pairing(keys, max_level=max_level).status,
        "pass_incremental_balanced_leaf_keys",
    )


def pair_balance_reclassify_sparse_mesh(
    leaves: tuple[SparseProvenanceLeaf, ...],
    vertices: np.ndarray,
    faces: np.ndarray,
    *,
    root_min: np.ndarray,
    target_edge: float,
    root_shape: tuple[int, int, int],
    max_level: int,
    leaf_budget: int,
    max_sweeps: int = 8,
) -> SparsePairingProvenanceReport:
    """Interleave sparse keys, then classify every newly created leaf from geometry."""
    original = {item.key: item for item in leaves}
    status, keys, pairing_refined, balance_refined, sweeps, pairing_status, balance_status = (
        interleave_pair_balance_leaf_keys(
            tuple(item.key for item in leaves),
            root_shape=root_shape,
            max_level=max_level,
            leaf_budget=leaf_budget,
            max_sweeps=max_sweeps,
        )
    )
    if status != "pass_interleaved_pair_balance":
        return SparsePairingProvenanceReport(
            status=status,
            initial_leaves=len(leaves),
            final_leaves=(),
            pairing_refined_terminal_leaves=pairing_refined,
            balance_refined_parent_leaves=balance_refined,
            interleave_sweeps=sweeps,
            final_pairing_status=pairing_status,
            final_balance_status=balance_status,
            provenance_histogram={},
            reclassified_leaves=0,
            topology_ready=False,
            production_octree_changed=False,
        )
    changed_keys = tuple(key for key in keys if key not in original)
    reclassified = classify_sparse_mesh_leaf_keys(
        changed_keys,
        vertices,
        faces,
        root_min=np.asarray(root_min, dtype=np.float64),
        target_edge=target_edge,
    )
    final = tuple(
        sorted(
            (*(original[key] for key in keys if key in original), *reclassified),
            key=lambda item: item.key,
        )
    )
    if tuple(item.key for item in final) != keys:
        raise RuntimeError("final provenance keys must exactly match interleaved keys")
    return SparsePairingProvenanceReport(
        status="pass_paired_balanced_reclassified_partition",
        initial_leaves=len(leaves),
        final_leaves=final,
        pairing_refined_terminal_leaves=pairing_refined,
        balance_refined_parent_leaves=balance_refined,
        interleave_sweeps=sweeps,
        final_pairing_status=pairing_status,
        final_balance_status=balance_status,
        provenance_histogram=dict(sorted(Counter(item.provenance for item in final).items())),
        reclassified_leaves=len(reclassified),
        topology_ready=False,
        production_octree_changed=False,
    )
