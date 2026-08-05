"""L0 tests for Tri, Strict Quad, and TRI+QUAD private surface transaction."""
from __future__ import annotations
from copy import deepcopy
import numpy as np
from core.evaluator.native_surface_product_transaction import evaluate_surface_product_transaction

def _common():
    points=np.array([[0.,0.,0.],[1.,0.,0.],[1.,1.,0.],[0.,1.,0.]])
    witness={"accepted":True,"frozen_front":{"status":"frozen"},"collision_visibility":{"status":"measured_clear"},"geodesic":{"status":"measured"}}
    authority={"source_verified":True,"field_origins_complete":True,"raw_sha256":"raw-sha","feature":"feature","patch":"patch","physical_group":"group","component":"component","provenance":"provenance"}
    profile={"min_face_area":0.1,"max_skewness":0.9,"max_metric_distortion":2.0}
    cert={"raw_sha256":"raw-sha","source_kind":"stl"}
    return points,witness,authority,profile,cert

def _call(kind,sp,st,sq,cp,ct,cq,lineage,requested=1,actual=1,witness=None,authority=None,profile=None,cert=None):
    return evaluate_surface_product_transaction(kind,sp,st,sq,cp,ct,cq,requested,actual,cert,authority,profile,witness,lineage)

def test_bl0_identity_is_exact_and_not_published():
    points,witness,authority,profile,cert=_common()
    result=_call("tri",points,[[0,1,2]],[],points,[[0,1,2]],[],[],0,0)
    assert result["accepted"] is True
    assert result["status"]=="disabled_identity"
    assert result["receipt_sealed"] is False
    assert result["publication_eligible"] is False

def test_strict_quad_requires_true_two_to_one_pair_and_stays_private():
    points,witness,authority,profile,cert=_common()
    source_tri=[[0,1,2],[0,2,3]]
    lineage=[{"kind":"quad","source_count":2,"feature":"f","patch":"p","physical_group":"g","component":"c","provenance":"direct"}]
    before=deepcopy(points)
    result=_call("strict_quad",points,source_tri,[],points,[],[[0,1,2,3]],lineage,1,1,witness,authority,profile,cert)
    assert result["accepted"] is True
    assert result["status"]=="stage_receipt_sealed"
    assert result["runtime_route"]=="default_off"
    assert result["face_count"]==1
    assert points.tolist()==before.tolist()

def test_tri_plus_quad_is_mixed_and_noop_tri_is_refused():
    points,witness,authority,profile,cert=_common()
    lineage=[{"kind":"tri","source_count":1,"feature":"f","patch":"p","physical_group":"g","component":"c","provenance":"direct"},{"kind":"quad","source_count":2,"feature":"f","patch":"p","physical_group":"g","component":"c","provenance":"direct"}]
    result=_call("tri_plus_quad",points,[[0,1,2]],[],points,[[0,1,2]],[[0,1,2,3]],lineage,1,1,witness,authority,profile,cert)
    assert result["accepted"] is True
    noop=_call("tri",points,[[0,1,2]],[],points,[[0,1,2]],[],[{"kind":"tri","source_count":1,"feature":"f","patch":"p","physical_group":"g","component":"c","provenance":"direct"}],1,1,witness,authority,profile,cert)
    assert noop["reason"]=="tri_noop_clone"

def test_product_relabels_and_quality_authority_fail_closed():
    points,witness,authority,profile,cert=_common()
    quad_lineage=[{"kind":"quad","source_count":2,"feature":"f","patch":"p","physical_group":"g","component":"c","provenance":"direct"}]
    relabel=_call("strict_quad",points,[[0,1,2]],[],points,[[0,1,2]],[[0,1,2,3]],quad_lineage,1,1,witness,authority,profile,cert)
    assert relabel["reason"]=="strict_quad_product_shape"
    bad=_call("tri_plus_quad",points,[[0,1,2]],[],points,[[0,1,2]],[[0,1,2,3]],quad_lineage,1,1,witness,dict(authority,source_verified=False),profile,cert)
    assert bad["status"]=="incomplete"
    badq=_call("tri_plus_quad",points,[[0,1,2]],[],points,[[0,1,2]],[[0,1,2,3]],[
        {"kind":"tri","source_count":1,"feature":"f","patch":"p","physical_group":"g","component":"c","provenance":"direct"},
        {"kind":"quad","source_count":2,"feature":"f","patch":"p","physical_group":"g","component":"c","provenance":"direct"}],1,1,witness,authority,dict(profile,min_face_area=2.0),cert)
    assert badq["reason"]=="face_area_gate_failed"
