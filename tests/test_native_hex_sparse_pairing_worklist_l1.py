"""Strong-pairing worklist controls remain report-only."""

from core.generator.native_hex.sparse_leaf_partition_l0 import SparseLeafKey
from core.generator.native_hex.sparse_pairing_worklist_l1 import (
    pair_sparse_leaf_keys_worklist,
)


def _one_refined_child() -> tuple[SparseLeafKey, ...]:
    leaves = [SparseLeafKey(1, i, j, k) for i in range(2) for j in range(2) for k in range(2)]
    leaves.remove(SparseLeafKey(1, 0, 0, 0))
    leaves.extend(SparseLeafKey(2, i, j, k) for i in range(2) for j in range(2) for k in range(2))
    return tuple(leaves)


def test_sibling_completion_produces_a_paired_uniform_block() -> None:
    report = pair_sparse_leaf_keys_worklist(_one_refined_child(), max_level=2, leaf_budget=64)

    assert report.status == "pass_strong_octree_pairing_worklist"
    assert len(report.final_leaves) == 64
    assert report.refined_terminal_leaves == 7
    assert report.final_unpaired_parent_count == 0
    assert not report.production_octree_changed


def test_sibling_completion_refuses_before_crossing_leaf_budget() -> None:
    report = pair_sparse_leaf_keys_worklist(_one_refined_child(), max_level=2, leaf_budget=63)

    assert report.status == "reject_strong_pairing_leaf_budget"
    assert len(report.final_leaves) == 15
    assert report.final_unpaired_parent_count == 1
