"""Pairing precondition tests for sparse adaptive-octree leaves."""

from core.generator.native_hex.sparse_leaf_partition_l0 import SparseLeafKey
from core.generator.native_hex.sparse_pairing_l0 import audit_sparse_octree_pairing


def _uniform(level: int) -> tuple[SparseLeafKey, ...]:
    width = 1 << level
    return tuple(
        SparseLeafKey(level, i, j, k)
        for i in range(width)
        for j in range(width)
        for k in range(width)
    )


def test_uniform_refinement_satisfies_strong_octree_pairing() -> None:
    report = audit_sparse_octree_pairing(_uniform(2), max_level=2)

    assert report.status == "pass_strong_octree_pairing"
    assert report.unpaired_parent_count == 0
    assert not report.production_octree_changed


def test_one_refined_sibling_cluster_is_detected_as_unpaired() -> None:
    leaves = [SparseLeafKey(1, i, j, k) for i in range(2) for j in range(2) for k in range(2)]
    leaves.remove(SparseLeafKey(1, 0, 0, 0))
    leaves.extend(SparseLeafKey(2, i, j, k) for i in range(2) for j in range(2) for k in range(2))

    report = audit_sparse_octree_pairing(tuple(leaves), max_level=2)

    assert report.status == "reject_strong_octree_pairing"
    assert report.unpaired_parent_count == 1
    assert report.first_unpaired_parent == SparseLeafKey(0, 0, 0, 0)
    assert report.first_unpaired_refined_child_mask == 1
