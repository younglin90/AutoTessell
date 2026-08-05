from __future__ import annotations
from pathlib import Path
import numpy as np

from core.evaluator.native_tri_authority_bound_consumer import (
    evaluate_native_tri_authority_bound,
)

BUILD = Path("auto_tessell_core/build").resolve()

def _authority():
    return {
        "accepted": True, "receipt_sealed": True, "receipt_digest": "authority",
        "runtime_route": "default_off", "direct_lineage": True,
        "source_sha256": "a" * 64,
    }

def _optimizer(layers):
    return {
        "accepted": True, "receipt_sealed": True, "receipt_digest": "optimizer",
        "runtime_route": "default_off", "actual_layers": layers,
    }

def _ledger():
    return {
        "schema": "native-tri-source-ledger/v1", "immutable": True,
        "source_sha256": "a" * 64,
        "source_faces": [{
            "source_face_id": 0, "patch_id": "wall", "feature_id": "flat",
            "physical_group": "fluid", "component_id": "main",
        }],
    }

def _producer(layers):
    return {
        "lineage_complete": True, "actual_layers": layers,
        "total_thickness": 0.1, "thickness_monotone": True,
        "growth_ratio_error": 0.0,
    }

def _binding():
    return [{
        "source_edge": f"edge-{i}", "source_face": "face-0",
        "wall_edge": f"wall-{i}", "strip_face": f"strip-{i}",
        "output_face": i, "feature": "flat", "patch": "wall",
        "physical_group": "fluid", "component": "main",
        "provenance": "direct", "layer": 1,
    } for i in range(3)]

def _meshes():
    base_points = np.array([[0.,0.,0.],[1.,0.,0.],[0.,1.,0.]])
    base_triangles = np.array([[0,1,2]], dtype=np.int64)
    candidate_points = np.array([[0.,0.,0.],[1.,0.,0.],[0.,1.,0.],[.4,.4,0.]])
    candidate_triangles = np.array([[0,1,3],[1,2,3],[2,0,3]], dtype=np.int64)
    return base_points, base_triangles, candidate_points, candidate_triangles

def _call(monkeypatch, layers, *, authority=None, candidate=None, quad_relabel=False, binding=None):
    monkeypatch.setenv("AUTOTESSELL_EXT_BUILD_DIR", str(BUILD))
    bp, bt, cp, ct = _meshes()
    if layers == 0:
        cp, ct = bp.copy(), bt.copy()
    elif candidate is not None:
        cp, ct = candidate
    return evaluate_native_tri_authority_bound(
        authority or _authority(), _optimizer(layers), _ledger(),
        _producer(layers) if layers else {},
        _binding() if binding is None and layers else (binding or []),
        bp, bt, cp, ct, layers, layers,
        "a" * 64 if layers == 0 else "b" * 64,
        "a" * 64 if layers == 0 else "c" * 64,
        quad_relabel,
    )

def test_tri_bl0_and_positive_layers_are_deterministic(monkeypatch):
    for layers in (0, 1, 3, 8):
        first = _call(monkeypatch, layers)
        second = _call(monkeypatch, layers)
        assert first == second
        assert first["accepted"] is True
        assert first["actual_layers"] == layers
        assert first["runtime_route"] == "default_off"
        assert first["publication_eligible"] is False
        assert first["topology"]["duplicate"] == 0
        assert first["quality"]["minimum_scaled_jacobian"] > 0

def test_tri_route_clone_and_relabel_fail_closed(monkeypatch):
    bp, bt, _, _ = _meshes()
    result = _call(monkeypatch, 1, candidate=(bp.copy(), bt.copy()))
    assert result["reason"] == "tri_clone_rejected"
    result = _call(monkeypatch, 1, quad_relabel=True)
    assert result["reason"] == "quad_relabel_rejected"
    bad = _authority()
    bad["runtime_route"] = "production"
    result = _call(monkeypatch, 1, authority=bad)
    assert result["actual_layers"] == 0

def test_tri_lineage_and_quality_fail_closed(monkeypatch):
    rows = _binding()
    rows[1]["output_face"] = rows[0]["output_face"]
    result = _call(monkeypatch, 1, binding=rows)
    assert result["reason"] == "output_face_binding_invalid"
    bp, bt, cp, ct = _meshes()
    bad = cp.copy()
    bad[3] = [0.0, 0.0, 0.0]
    result = _call(monkeypatch, 1, candidate=(bad, ct))
    assert result["actual_layers"] == 0 and result["atomic_rollback"] is True
