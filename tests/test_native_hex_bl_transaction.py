"""L0 tests for the private Native Hex inward-shell validator."""
from __future__ import annotations
from copy import deepcopy
import numpy as np
from core.evaluator.native_hex_bl_transaction import evaluate_native_hex_bl_transaction

def _case():
    points=np.array([[0.,0.,0.],[1.,0.,0.],[1.,1.,0.],[0.,1.,0.],[0.,0.,1.],[1.,0.,1.],[1.,1.,1.],[0.,1.,1.]])
    cells=[[0,1,2,3,4,5,6,7]]
    boundary=[[0,1,2,3],[4,5,6,7],[0,1,5,4],[1,2,6,5],[2,3,7,6],[3,0,4,7]]
    binding=[{"source_face":str(i),"output_face":str(i),"feature":"f","patch":"p","physical_group":"g","component":"c","provenance":"direct","direct":True} for i in range(6)]
    witness={"accepted":True,"frozen_front":{"status":"frozen"},"collision_visibility":{"status":"measured_clear"},"geodesic":{"status":"measured"}}
    authority={"source_verified":True,"field_origins_complete":True,"brep_hash":"brep","raw_sha256":"raw","feature":"f","patch":"p","physical_group":"g","component":"c","provenance":"direct"}
    profile={"min_volume":0.1,"min_corner_jacobian":0.0001,"max_wall_non_orthogonality":0.0,"max_tangential_skewness":0.0,"max_metric_distortion":1.0}
    cert={"brep_hash":"brep","raw_sha256":"raw","kind":"cad"}
    return points,cells,boundary,binding,witness,authority,profile,cert

def _call(points,cells,boundary,binding,witness,authority,profile,cert,requested=1,actual=1):
    return evaluate_native_hex_bl_transaction(points,cells,boundary,points.copy(),cells,boundary,requested,actual,"bd","bd","sd","sd",binding,cert,authority,profile,witness)

def test_bl0_exact_identity():
    p,c,b,bind,w,a,q,cert=_case()
    result=_call(p,c,b,bind,w,a,q,cert,0,0)
    assert result["accepted"] is True
    assert result["status"]=="disabled_identity"
    assert result["receipt_sealed"] is False
    assert result["publication_eligible"] is False

def test_positive_hex_stage_is_private_and_deterministic():
    args=_case()
    before=deepcopy(args[0])
    first=_call(*args)
    second=_call(*args)
    assert first["accepted"] is True
    assert first["status"]=="stage_receipt_sealed"
    assert first["runtime_route"]=="default_off"
    assert first["route_calls"]==0
    assert first["receipt_digest"]==second["receipt_digest"]
    assert first["topology"]["inverted"]==0
    assert args[0].tolist()==before.tolist()

def test_negative_jacobian_duplicate_and_binding_fail_closed():
    p,c,b,bind,w,a,q,cert=_case()
    inverted=np.array([[0,3,2,1,4,7,6,5]],dtype=np.int64)
    result=evaluate_native_hex_bl_transaction(p,c,b,p,inverted,b,1,1,"bd","bd2","sd","sd2",bind,cert,a,q,w)
    assert result["reason"]=="hex_quality_gate_failed"
    duplicate=c+c
    result=evaluate_native_hex_bl_transaction(p,c,b,p,duplicate,np.concatenate([b,b]),1,1,"bd","bd2","sd","sd2",bind*2,cert,a,q,w)
    assert result["reason"]=="duplicate_cell"
    result=_call(p,c,b,None,w,a,q,cert)
    assert result["status"]=="incomplete"

def test_authority_and_witness_are_hard_gates():
    p,c,b,bind,w,a,q,cert=_case()
    bad=_call(p,c,b,bind,w,dict(a,source_verified=False),q,cert)
    assert bad["status"]=="incomplete"
    badw=_call(p,c,b,bind,None,a,q,cert)
    assert badw["reason"]=="surface_witness_gate_failed"
