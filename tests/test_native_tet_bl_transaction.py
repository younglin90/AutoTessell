"""L0 contract tests for Native Tet private-stage BL validation."""
from __future__ import annotations
from copy import deepcopy
import numpy as np
from core.evaluator.native_tet_bl_transaction import evaluate_native_tet_bl_transaction

def _case():
    points = np.array([[0.,0.,0.],[1.,0.,0.],[0.,1.,0.],[0.,0.,1.]])
    tets = np.array([[0,1,2,3]], dtype=np.int64)
    witness = {
        "accepted": True,
        "frozen_front": {"status": "frozen"},
        "collision_visibility": {"status": "measured_clear"},
        "geodesic": {"status": "measured"},
    }
    authority = {
        "authority_state": "source_verified",
        "field_origins_complete": True,
        "source": "source-sha",
        "feature": "feature-sha",
        "physical_group": "group-sha",
        "component": "component-sha",
        "provenance": "provenance-sha",
    }
    profile = {
        "min_volume": 1.0e-14,
        "min_jacobian": 1.0,
        "max_wall_non_orthogonality": 0.0,
        "max_tangential_skewness": 0.0,
        "max_metric_distortion": 1.0,
    }
    lineage = [{
        "source_face": "wall-face-0",
        "layer": 1,
        "feature": "flat",
        "patch": "wall",
        "physical_group": "fluid",
        "component": "main",
        "provenance": "direct",
    }]
    return points, tets, witness, authority, profile, lineage

def _invoke(*, points, tets, requested=1, actual=1, witness=None, authority=None, profile=None, lineage=None):
    return evaluate_native_tet_bl_transaction(
        points, tets, points.copy(), tets.copy(), requested, actual,
        "boundary-digest", "boundary-digest",
        "semantic-digest", "semantic-digest",
        lineage if lineage is not None else [],
        witness, authority, profile, [0],
    )

def test_bl0_is_exact_identity_and_not_published():
    points, tets, *_ = _case()
    result = evaluate_native_tet_bl_transaction(
        points, tets, points.copy(), tets.copy(), 0, 0,
        "b", "b", "s", "s", [], None, None, None, [0],
    )
    assert result["accepted"] is True
    assert result["status"] == "disabled_identity"
    assert result["actual_layers"] == 0
    assert result["receipt_sealed"] is False
    assert result["publication_eligible"] is False

def test_positive_stage_passes_but_route_stays_off():
    points, tets, witness, authority, profile, lineage = _case()
    before = (points.copy(), tets.copy(), deepcopy(lineage))
    result = _invoke(points=points, tets=tets, witness=witness, authority=authority, profile=profile, lineage=lineage)
    assert result["accepted"] is True
    assert result["status"] == "stage_receipt_sealed"
    assert result["actual_layers"] == 1
    assert result["receipt_sealed"] is True
    assert result["publication_eligible"] is False
    assert result["runtime_route"] == "default_off"
    assert result["route_calls"] == 0
    assert result["topology"]["inverted"] == 0
    assert points.tolist() == before[0].tolist()
    assert tets.tolist() == before[1].tolist()
    assert lineage == before[2]
    assert result["receipt_digest"] == _invoke(points=points, tets=tets, witness=witness, authority=authority, profile=profile, lineage=lineage)["receipt_digest"]

def test_negative_duplicate_and_missing_evidence_roll_back():
    points, tets, witness, authority, profile, lineage = _case()
    inverted = np.array([[0,2,1,3]], dtype=np.int64)
    result = _invoke(points=points, tets=inverted, witness=witness, authority=authority, profile=profile, lineage=lineage)
    assert result["accepted"] is False
    assert result["reason"] == "inverted_tet"
    assert result["actual_layers"] == 0
    duplicate = np.array([[0,1,2,3],[0,1,2,3]], dtype=np.int64)
    result = evaluate_native_tet_bl_transaction(
        points, tets, points.copy(), duplicate, 1, 1,
        "b", "b2", "s", "s2", lineage * 2, witness, authority, profile, [0],
    )
    assert result["reason"] == "duplicate_tet"
    no_witness = _invoke(points=points, tets=tets, witness=None, authority=authority, profile=profile, lineage=lineage)
    assert no_witness["status"] == "incomplete"
    assert no_witness["actual_layers"] == 0

def test_quality_profile_and_authority_are_hard_gates():
    points, tets, witness, authority, profile, lineage = _case()
    bad_authority = dict(authority, authority_state="inferred")
    result = _invoke(points=points, tets=tets, witness=witness, authority=bad_authority, profile=profile, lineage=lineage)
    assert result["status"] == "incomplete"
    bad_profile = dict(profile, max_metric_distortion=25.0)
    result = _invoke(points=points, tets=tets, witness=witness, authority=authority, profile=bad_profile, lineage=lineage)
    assert result["reason"] == "quality_profile_gate_failed"
