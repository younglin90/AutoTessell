from __future__ import annotations
import os
from unittest.mock import patch
import numpy as np
from core.preprocessor.native_tri.strict_planar_flip_product_l0 import materialize_strict_planar_flip_product_l0

_ENV = "AUTO_TESSELL_TRI_STRICT_PLANAR_FLIP_PRODUCT_L0"

def _patch() -> tuple[np.ndarray, np.ndarray]:
    return np.array(((0.,0.,0.),(1.,0.,0.),(2.,1.,0.),(0.,1.,0.))), np.array(((0,1,2),(1,3,2)), dtype=np.int64)

def test_default_off_never_runs_a_product_candidate() -> None:
    vertices, faces = _patch()
    result = materialize_strict_planar_flip_product_l0(vertices, faces, (1,2), source_patch_ids=("wall", "wall"))
    assert not result.accepted and result.product is None
    assert result.status == "reject_strict_planar_flip_disabled"

def test_enabled_actual_flip_preserves_source_boundary_topology_patch_and_region_provenance() -> None:
    vertices, faces = _patch(); before_v, before_f = vertices.copy(), faces.copy()
    with patch.dict(os.environ, {_ENV:"1"}):
        result = materialize_strict_planar_flip_product_l0(vertices, faces, (1,2), source_patch_ids=("wall", "wall"))
    assert result.accepted and result.product is not None
    assert result.status == "pass_strict_planar_flip_candidate"
    assert result.source_boundary_preserved and result.source_features_preserved
    assert result.topology_preserved and result.provenance_preserved
    assert result.independent_product_ready is False
    assert result.product.face_region_provenance == ((0,1),(0,1))
    assert not result.product.vertices.flags.writeable and not result.product.faces.flags.writeable
    np.testing.assert_array_equal(vertices, before_v); np.testing.assert_array_equal(faces, before_f)

def test_feature_edge_or_patch_mismatch_fails_closed() -> None:
    vertices, faces = _patch()
    with patch.dict(os.environ, {_ENV:"1"}):
        feature = materialize_strict_planar_flip_product_l0(vertices, faces, (1,2), source_patch_ids=("wall", "wall"), source_feature_edges=((1,2),))
        patches = materialize_strict_planar_flip_product_l0(vertices, faces, (1,2), source_patch_ids=("wall", "inlet"))
    assert feature.status == "reject_strict_planar_flip_feature" and feature.product is None
    assert patches.status == "reject_strict_planar_flip_preflight" and patches.product is None
