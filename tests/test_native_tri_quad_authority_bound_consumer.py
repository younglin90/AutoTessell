from __future__ import annotations
from pathlib import Path
import numpy as np

from core.evaluator.native_tri_quad_authority_bound_consumer import (
    evaluate_native_tri_quad_authority_bound,
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
        "schema": "native-tri-quad-source-ledger/v1", "immutable": True,
        "source_sha256": "a" * 64,
        "source_faces": [
            {"source_face_id": "face-0", "patch_id": "wall",
             "feature_id": "flat", "physical_group": "fluid",
             "component_id": "main"},
            {"source_face_id": "face-1", "patch_id": "wall",
             "feature_id": "flat", "physical_group": "fluid",
             "component_id": "main"},
            {"source_face_id": "face-2", "patch_id": "wall",
             "feature_id": "flat", "physical_group": "fluid",
             "component_id": "main"},
        ],
    }


def _producer(layers):
    return {
        "lineage_complete": True, "actual_layers": layers,
        "total_thickness": 0.1, "thickness_monotone": True,
        "growth_ratio_error": 0.0,
    }


def _binding():
    return [
        {
            "source_edge": "edge-tri", "wall_edge": "wall-tri",
            "output_kind": "triangle", "output_face": 0,
            "source_face": "face-0", "strip_face": "strip-tri",
            "feature": "flat", "patch": "wall",
            "physical_group": "fluid", "component": "main",
            "provenance": "direct", "layer": 1,
            "wall_front_orthogonality_degrees": 0.0,
        },
        {
            "source_edge": "edge-quad", "wall_edge": "wall-quad",
            "output_kind": "quad", "output_face": 0,
            "source_face_a": "face-1", "source_face_b": "face-2",
            "strip_face": "strip-quad", "feature": "flat",
            "patch": "wall", "physical_group": "fluid",
            "component": "main", "provenance": "direct", "layer": 1,
            "wall_front_orthogonality_degrees": 0.0,
        },
    ]


def _meshes():
    points = np.array([
        [0., 0., 0.], [1., 0., 0.], [0., 1., 0.],
        [3., 0., 0.], [4., 0., 0.], [4., 1., 0.], [3., 1., 0.],
    ])
    triangles = np.array([[0, 1, 2]], dtype=np.int64)
    quads = np.array([[3, 4, 5, 6]], dtype=np.int64)
    candidate = points.copy()
    candidate[:, 2] = 0.1
    return points, triangles, quads, candidate, triangles.copy(), quads.copy()


def _call(monkeypatch, layers, **kwargs):
    monkeypatch.setenv("AUTOTESSELL_EXT_BUILD_DIR", str(BUILD))
    bp, bt, bq, cp, ct, cq = _meshes()
    if layers == 0:
        cp, ct, cq = bp.copy(), bt.copy(), bq.copy()
    if "candidate" in kwargs:
        cp, ct, cq = kwargs["candidate"]
    return evaluate_native_tri_quad_authority_bound(
        _authority(), _optimizer(layers), _ledger(),
        _producer(layers) if layers else {}, kwargs.get("binding", _binding() if layers else []),
        bp, bt, bq, cp, ct, cq, layers, layers,
        "a" * 64 if layers == 0 else "c" * 64,
        "a" * 64 if layers == 0 else "b" * 64,
        kwargs.get("quad_relabel", False),
        kwargs.get("triangle_handoff", False),
        kwargs.get("pair_plan_reordered", False),
    )


def test_tri_quad_bl0_and_positive_layers_are_deterministic(monkeypatch):
    for layers in (0, 1, 3, 8):
        first = _call(monkeypatch, layers)
        second = _call(monkeypatch, layers)
        assert first == second
        assert first["accepted"] is True
        assert first["actual_layers"] == layers
        assert first["runtime_route"] == "default_off"
        assert first["publication_eligible"] is False
        assert first["topology"]["duplicate"] == 0
        assert first["topology"]["non_manifold"] == 0
        assert first["quality"]["minimum_scaled_jacobian"] > 0
        assert first["quality"]["max_wall_front_orthogonality_degrees"] == 0


def test_tri_quad_rejects_relabel_clone_handoff_and_reordered_plan(monkeypatch):
    bp, bt, bq, _, _, _ = _meshes()
    result = _call(monkeypatch, 1, candidate=(bp.copy(), bt.copy(), bq.copy()))
    assert result["reason"] == "tri_quad_clone_rejected"
    assert _call(monkeypatch, 1, quad_relabel=True)["reason"] == "quad_relabel_rejected"
    assert _call(monkeypatch, 1, triangle_handoff=True)["reason"] == "triangle_handoff_rejected"
    assert _call(monkeypatch, 1, pair_plan_reordered=True)["reason"] == "pair_plan_reordered"


def test_tri_quad_provenance_and_quality_roll_back(monkeypatch):
    rows = _binding()
    rows[1]["source_face_b"] = rows[0]["source_face"]
    assert _call(monkeypatch, 1, binding=rows)["reason"] == "quad_source_consumption_invalid"

    bp, bt, bq, cp, ct, cq = _meshes()
    bad = cp.copy()
    bad[1] = bad[0]
    result = evaluate_native_tri_quad_authority_bound(
        _authority(), _optimizer(1), _ledger(), _producer(1), _binding(),
        bp, bt, bq, bad, ct, cq, 1, 1, "c" * 64, "b" * 64,
    )
    assert result["reason"] == "mixed_surface_topology_failed"
    result = _call(monkeypatch, 0)
    assert result["accepted"] is True
    result = evaluate_native_tri_quad_authority_bound(
        _authority(), _optimizer(0), _ledger(), {}, [],
        bp, bt, bq, bp, bt, bq, 0, 0, "a" * 64, "b" * 64,
    )
    assert result["reason"] == "bl0_mixed_identity_mismatch"
