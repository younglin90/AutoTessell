"""Interleaved pairing/balance tests before real-STL reclassification."""

import numpy as np

from core.generator.native_hex.sparse_closure_l0 import axis_aligned_box_triangles
from core.generator.native_hex.sparse_leaf_partition_l0 import SparseLeafKey
from core.generator.native_hex.sparse_pairing_provenance_l2 import (
    interleave_pair_balance_leaf_keys,
    pair_balance_reclassify_sparse_mesh,
)
from core.generator.native_hex.sparse_partition_provenance_l1 import SparseProvenanceLeaf


def _one_refined_child() -> tuple[SparseLeafKey, ...]:
    leaves = [SparseLeafKey(1, i, j, k) for i in range(2) for j in range(2) for k in range(2)]
    leaves.remove(SparseLeafKey(1, 0, 0, 0))
    leaves.extend(SparseLeafKey(2, i, j, k) for i in range(2) for j in range(2) for k in range(2))
    return tuple(leaves)


def test_pair_balance_interleave_returns_a_fixed_point() -> None:
    status, leaves, pairing_refined, balance_refined, sweeps, pairing_status, balance_status = (
        interleave_pair_balance_leaf_keys(
            _one_refined_child(), root_shape=(1, 1, 1), max_level=2, leaf_budget=64
        )
    )

    assert status == "pass_interleaved_pair_balance"
    assert len(leaves) == 64
    assert pairing_refined == 7
    assert balance_refined == 0
    assert sweeps == 1
    assert pairing_status == "pass_strong_octree_pairing"
    assert balance_status == "pass_incremental_balanced_leaf_keys"


def test_pair_balance_refuses_a_budget_before_accepting_partial_keys() -> None:
    status, leaves, pairing_refined, balance_refined, _, _, _ = interleave_pair_balance_leaf_keys(
        _one_refined_child(), root_shape=(1, 1, 1), max_level=2, leaf_budget=63
    )

    assert status == "reject_strong_pairing_leaf_budget"
    assert len(leaves) == 15
    assert pairing_refined == 0
    assert balance_refined == 0


def test_new_pairing_leaves_are_reclassified_from_geometry_not_parent_labels() -> None:
    triangles = axis_aligned_box_triangles(
        np.asarray((-0.25, -0.25, -0.25)), np.asarray((0.25, 0.25, 0.25))
    )
    vertices = triangles.reshape(-1, 3)
    faces = np.arange(len(vertices), dtype=np.int64).reshape(-1, 3)
    source = tuple(SparseProvenanceLeaf(key, "outside") for key in _one_refined_child())

    report = pair_balance_reclassify_sparse_mesh(
        source,
        vertices,
        faces,
        root_min=np.asarray((-1.0, -1.0, -1.0)),
        target_edge=2.0,
        root_shape=(1, 1, 1),
        max_level=2,
        leaf_budget=64,
    )

    assert report.status == "pass_paired_balanced_reclassified_partition"
    assert len(report.final_leaves) == 64
    assert report.reclassified_leaves == 56
    assert report.provenance_histogram["surface"] > 0
    assert not report.production_octree_changed
