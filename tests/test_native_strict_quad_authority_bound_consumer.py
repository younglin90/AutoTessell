from __future__ import annotations
from pathlib import Path
import numpy as np

from core.evaluator.native_strict_quad_authority_bound_consumer import (
    evaluate_native_strict_quad_authority_bound,
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
        "schema": "native-strict-quad-source-ledger/v1", "immutable": True,
        "source_sha256": "a" * 64,
        "source_faces": [
            {"source_face_id": 0, "patch_id": "wall", "feature_id": "flat",
             "physical_group": "fluid", "component_id": "main"},
            {"source_face_id": 1, "patch_id": "wall", "feature_id": "flat",
             "physical_group": "fluid", "component_id": "main"},
        ],
    }


def _producer(layers):
    return {
        "lineage_complete": True, "actual_layers": layers,
        "total_thickness": 0.1, "thickness_monotone": True,
        "growth_ratio_error": 0.0,
    }


def _binding():
    return [{
        "source_edge": "edge-0", "source_face_a": "face-0",
        "source_face_b": "face-1", "wall_edge": "wall-0",
        "strip_quad": "strip-0", "output_quad": 0,
        "feature": "flat", "patch": "wall", "physical_group": "fluid",
        "component": "main", "provenance": "direct", "layer": 1,
    }]


def _meshes():
    points = np.array([[0., 0., 0.], [1., 0., 0.],
                       [1., 1., 0.], [0., 1., 0.]])
    quads = np.array([[0, 1, 2, 3]], dtype=np.int64)
    candidate = points.copy()
    candidate[:, 2] = 0.1
    return points, quads, candidate, quads.copy()


def _call(monkeypatch, layers, **kwargs):
    monkeypatch.setenv("AUTOTESSELL_EXT_BUILD_DIR", str(BUILD))
    bp, bq, cp, cq = _meshes()
    if layers == 0:
        cp, cq = bp.copy(), bq.copy()
    if "candidate" in kwargs:
        cp, cq = kwargs["candidate"]
    binding = kwargs.get("binding", _binding() if layers else [])
    return evaluate_native_strict_quad_authority_bound(
        _authority(), _optimizer(layers), _ledger(),
        _producer(layers) if layers else {}, binding,
        bp, bq, cp, cq, layers, layers,
        "a" * 64 if layers == 0 else "c" * 64,
        "a" * 64 if layers == 0 else "b" * 64,
        kwargs.get("triangles_present", False),
        kwargs.get("pair_plan_reordered", False),
    )


def test_strict_quad_bl0_and_positive_layers_are_deterministic(monkeypatch):
    for layers in (0, 1, 3, 8):
        first = _call(monkeypatch, layers)
        second = _call(monkeypatch, layers)
        assert first == second
        assert first["accepted"] is True
        assert first["actual_layers"] == layers
        assert first["runtime_route"] == "default_off"
        assert first["publication_eligible"] is False
        assert first["topology"]["duplicate"] == 0
        assert first["quality"]["minimum_corner_scaled_jacobian"] > 0


def test_strict_quad_rejects_clone_triangle_and_reordered_pair_plan(monkeypatch):
    bp, bq, _, _ = _meshes()
    result = _call(monkeypatch, 1, candidate=(bp.copy(), bq.copy()))
    assert result["reason"] == "strict_quad_clone_rejected"
    result = _call(monkeypatch, 1, triangles_present=True)
    assert result["reason"] == "triangles_present"
    result = _call(monkeypatch, 1, pair_plan_reordered=True)
    assert result["reason"] == "pair_plan_reordered"


def test_strict_quad_lineage_and_bl0_identity_fail_closed(monkeypatch):
    rows = _binding()
    rows[0]["output_quad"] = 1
    result = _call(monkeypatch, 1, binding=rows)
    assert result["reason"] == "output_quad_binding_invalid"
    result = _call(monkeypatch, 0)
    assert result["accepted"] is True
    monkeypatch.setenv("AUTOTESSELL_EXT_BUILD_DIR", str(BUILD))
    bp, bq, cp, cq = _meshes()
    result = evaluate_native_strict_quad_authority_bound(
        _authority(), _optimizer(0), _ledger(), {}, [],
        bp, bq, cp, cq, 0, 0, "a" * 64, "b" * 64,
    )
    assert result["reason"] == "bl0_canonical_quad_identity_mismatch"
