from __future__ import annotations
from pathlib import Path
import numpy as np

from core.evaluator.native_poly_authority_bound_consumer import (
    validate_native_poly_authority_bound,
)

BUILD = Path("auto_tessell_core/build").resolve()

def _mesh():
    points = np.array([
        [0.,0.,0.],[1.,0.,0.],[1.,1.,0.],[0.,1.,0.],
        [0.,0.,1.],[1.,0.,1.],[1.,1.,1.],[0.,1.,1.],
    ])
    faces = [[0,3,2,1],[4,5,6,7],[0,1,5,4],[1,2,6,5],[2,3,7,6],[3,0,4,7]]
    return points, faces

def _binding():
    return [{
        "source_edge": f"edge-{i}", "source_face": f"face-{i}",
        "wall_edge": f"wall-{i}", "output_face": i,
        "feature": "flat", "patch": "wall", "physical_group": "fluid",
        "component": "main", "provenance": "direct",
    } for i in range(6)]

def _authority():
    return {
        "accepted": True, "receipt_sealed": True, "receipt_digest": "auth",
        "runtime_route": "default_off", "direct_lineage": True,
        "source_sha256": "a" * 64,
    }

def _optimizer(layers):
    return {
        "accepted": True, "receipt_sealed": True, "receipt_digest": "opt",
        "runtime_route": "default_off", "actual_layers": layers,
    }

def _ledger():
    return {
        "schema": "native-poly-source-ledger/v1", "immutable": True,
        "source_sha256": "a" * 64,
        "source_faces": [{
            "source_face_id": i, "ordered_vertex_ids": [0,1,2],
            "canonical_vertex_ids": [0,1,2], "patch_id": "wall",
            "feature_id": "flat", "physical_group": "fluid",
            "component_id": "main",
        } for i in range(6)],
    }

def _producer(layers):
    return {
        "lineage_complete": True, "source_sha256": "a" * 64,
        "candidate_source_sha256": "b" * 64,
        "producer_mapping_sha256": "c" * 64,
        "wall_edge_layer_sha256": "d" * 64,
        "source_face_preservation_sha256": "e" * 64,
        "outer_front_sha256": "f" * 64,
        "actual_layers": layers, "total_thickness": 0.1,
        "thickness_monotone": True, "growth_ratio_error": 0.0,
    }

def _partition():
    return {"cell_ids": {"core": [0], "boundary_layer": [0], "transition": []}}

def _call(monkeypatch, layers, *, authority=None, faces=None, candidate_digest=None):
    monkeypatch.setenv("AUTOTESSELL_EXT_BUILD_DIR", str(BUILD))
    points, base_faces = _mesh()
    return validate_native_poly_authority_bound(
        authority or _authority(), _optimizer(layers), _ledger(),
        _producer(layers) if layers else {}, _partition() if layers else {},
        _binding() if layers else [], points, faces or base_faces,
        [0] * 6, [-1] * 6, layers, layers,
        ("a" * 64) if layers == 0 else "baseline",
        candidate_digest or (("a" * 64) if layers == 0 else "b" * 64),
    )

def test_poly_bl0_and_positive_layers_are_deterministic(monkeypatch):
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

def test_poly_receipt_route_and_lineage_mutations_roll_back(monkeypatch):
    bad = _authority()
    bad["runtime_route"] = "production"
    result = _call(monkeypatch, 1, authority=bad)
    assert result["accepted"] is False and result["actual_layers"] == 0
    rows = _binding()
    rows[1]["output_face"] = rows[0]["output_face"]
    monkeypatch.setenv("AUTOTESSELL_EXT_BUILD_DIR", str(BUILD))
    points, faces = _mesh()
    result = validate_native_poly_authority_bound(
        _authority(), _optimizer(1), _ledger(), _producer(1), _partition(),
        rows, points, faces, [0] * 6, [-1] * 6, 1, 1, "baseline", "b" * 64,
    )
    assert result["reason"] == "boundary_output_binding_invalid"

def test_poly_duplicate_face_and_bl0_digest_mismatch_are_rejected(monkeypatch):
    _, faces = _mesh()
    bad_faces = list(faces) + [faces[0]]
    result = _call(monkeypatch, 1, faces=bad_faces)
    assert result["accepted"] is False
    assert result["actual_layers"] == 0
    result = _call(monkeypatch, 0, candidate_digest="different")
    assert result["reason"] == "bl0_artifact_identity_mismatch"
