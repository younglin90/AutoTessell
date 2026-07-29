"""L3 closure tests for a report-only selected sparse leaf union."""

from core.generator.native_hex.sparse_closed_volume_l3 import audit_sparse_closed_volume
from core.generator.native_hex.sparse_leaf_partition_l0 import SparseLeafKey
from core.generator.native_hex.sparse_partition_provenance_l1 import SparseProvenanceLeaf


def _leaf(i: int, j: int, k: int) -> SparseProvenanceLeaf:
    return SparseProvenanceLeaf(SparseLeafKey(0, i, j, k), "inside")


def test_closed_cube_selection_has_two_owner_boundary_edges() -> None:
    leaves = tuple(_leaf(i, j, k) for i in range(2) for j in range(2) for k in range(2))

    report = audit_sparse_closed_volume(leaves, max_level=0)

    assert report.status == "pass_closed_sparse_volume"
    assert report.face_owner_histogram == {1: 24, 2: 12}
    assert report.boundary_edge_owner_histogram == {2: 48}
    assert report.connected_components == 1
    assert report.topology_ready
    assert not report.production_octree_changed


def test_edge_only_contact_rejects_nonmanifold_boundary() -> None:
    leaves = (_leaf(0, 0, 0), _leaf(1, 1, 0))

    report = audit_sparse_closed_volume(leaves, max_level=0)

    assert report.status == "reject_closed_sparse_volume"
    assert not report.closed_exterior_boundary
    assert report.boundary_edge_owner_histogram[4] == 1
    assert report.connected_components == 2


def test_audit_refuses_partial_result_past_explicit_budget() -> None:
    report = audit_sparse_closed_volume((_leaf(0, 0, 0),), max_level=0, face_tile_budget=5)

    assert report.status == "reject_closed_volume_audit_budget"
    assert not report.topology_ready
