from __future__ import annotations
import os
from unittest.mock import patch
import numpy as np
from core.preprocessor.native_quad.strict_pair_transaction_l0 import materialize_strict_quad_pair_transaction_l0

_ENV = "AUTO_TESSELL_STRICT_QUAD_FIXED_PAIR_PRODUCT_L0"
def _square():
    return (np.array(((0.,0.,0.),(1.,0.,0.),(1.,1.,0.),(0.,1.,0.)),dtype=np.float64), np.array(((0,1,2),(0,2,3)),dtype=np.int64), np.array(((0,1),(1,2),(2,3),(0,3)),dtype=np.int64))

def test_default_off_derives_no_strict_quad_product() -> None:
    v,t,f=_square(); r=materialize_strict_quad_pair_transaction_l0(v,t,np.array(((0,1),),dtype=np.int64),f,source_patch_ids=("wall","wall"))
    assert not r.accepted and not r.transaction_applied and r.product_result is not None
    assert r.status == "reject_strict_quad_fixed_pair_product_disabled"

def test_enabled_actual_all_pair_transaction_outputs_only_quads_with_preservation_certificate() -> None:
    v,t,f=_square(); before=(v.copy(),t.copy())
    with patch.dict(os.environ,{_ENV:"1"}):
        r=materialize_strict_quad_pair_transaction_l0(v,t,np.array(((0,1),),dtype=np.int64),f,source_patch_ids=("wall","wall"))
    assert r.accepted and r.transaction_applied and not r.independent_product_ready
    assert r.product_result and r.product_result.product
    p=r.product_result.product
    assert p.triangles.shape == (0,3) and p.quads.shape == (1,4) and p.quad_patch_ids == ("wall",)
    assert not p.vertices.flags.writeable and not p.quads.flags.writeable
    np.testing.assert_array_equal(v,before[0]); np.testing.assert_array_equal(t,before[1])

def test_incomplete_or_feature_pair_plan_fails_closed_without_quad_dominant() -> None:
    v,t,f=_square()
    incomplete=materialize_strict_quad_pair_transaction_l0(v,t,np.empty((0,2),dtype=np.int64),f,source_patch_ids=("wall","wall"))
    with patch.dict(os.environ,{_ENV:"1"}):
        feature=materialize_strict_quad_pair_transaction_l0(v,t,np.array(((0,1),),dtype=np.int64),np.array(((0,2),),dtype=np.int64),source_patch_ids=("wall","wall"))
    assert incomplete.product_result is None and incomplete.status == "reject_strict_quad_pair_plan"
    assert feature.product_result and feature.product_result.product is None
    assert feature.status == "reject_strict_quad_fixed_pair_preflight"
