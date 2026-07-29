"""Surface preservation is measured separately from sparse volume closure."""

import numpy as np

from core.generator.native_hex.sparse_closure_l0 import axis_aligned_box_triangles
from core.generator.native_hex.sparse_leaf_partition_l0 import SparseLeafKey
from core.generator.native_hex.sparse_partition_provenance_l1 import SparseProvenanceLeaf
from core.generator.native_hex.sparse_surface_contract_l0 import (
    audit_sparse_selected_surface_contract,
)


def _box_surface() -> tuple[np.ndarray, np.ndarray]:
    triangles = axis_aligned_box_triangles(np.zeros(3), np.ones(3))
    return triangles.reshape(-1, 3), np.arange(len(triangles) * 3, dtype=np.int64).reshape(-1, 3)


def test_exact_aligned_cube_samples_coincide_but_do_not_prove_strict_contract() -> None:
    vertices, faces = _box_surface()
    report = audit_sparse_selected_surface_contract(
        (SparseProvenanceLeaf(SparseLeafKey(0, 0, 0, 0), "inside"),),
        vertices,
        faces,
        root_min=np.zeros(3),
        target_edge=1.0,
        max_level=0,
        tolerance=1.0e-12,
    )

    assert report.status == "pass_sampled_surface_coincidence"
    assert report.sampled_coincident
    assert not report.strict_surface_contract_proven
    assert not report.production_octree_changed


def test_shifted_candidate_is_rejected_in_both_distance_directions() -> None:
    vertices, faces = _box_surface()
    report = audit_sparse_selected_surface_contract(
        (SparseProvenanceLeaf(SparseLeafKey(0, 0, 0, 0), "inside"),),
        vertices,
        faces,
        root_min=np.asarray((0.1, 0.0, 0.0)),
        target_edge=1.0,
        max_level=0,
        tolerance=1.0e-12,
    )

    assert report.status == "reject_sampled_surface_deviation"
    assert report.candidate_to_source_max > 0.0
    assert report.source_to_candidate_max > 0.0
