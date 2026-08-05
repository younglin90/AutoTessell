from __future__ import annotations
from hashlib import sha256
from pathlib import Path

import numpy as np

from core.evaluator.native_l2_evidence_audit import audit_native_l2_evidence

BUILD = Path("auto_tessell_core/build").resolve()
SOURCE = b"authoritative-source-bytes"
OUTPUT = b"persisted-native-output-bytes"


def _authority(source_digest: str):
    return {
        "accepted": True,
        "receipt_sealed": True,
        "receipt_digest": "authority",
        "runtime_route": "default_off",
        "direct_lineage": True,
        "source_sha256": source_digest,
    }


def _ledger(count: int = 1):
    return {
        "schema": "native-l2-authoritative-ledger/v1",
        "immutable": True,
        "source_sha256": sha256(SOURCE).hexdigest(),
        "source_faces": [
            {
                "source_face_id": f"face-{i}",
                "source_edge": f"edge-{i}",
                "feature_id": "flat",
                "patch_id": "wall",
                "physical_group": "fluid",
                "component_id": "main",
                "orientation": "forward",
            }
            for i in range(count)
        ],
    }


def _manifest(engine: str, layers: int, output: bytes = OUTPUT):
    source_digest = sha256(SOURCE).hexdigest()
    output_digest = sha256(output).hexdigest()
    return {
        "schema": "native-l2-evidence-manifest/v1",
        "engine": engine,
        "output_sha256": output_digest,
        "build_sha256": "b" * 64,
        "config_sha256": "c" * 64,
        "repeat_source_sha256": [source_digest] * 3,
        "repeat_output_sha256": [output_digest] * 3,
        "bl0_exact_identity": layers == 0,
        "total_thickness": 0.1,
        "thickness_monotone": True,
        "growth_ratio_error": 0.0,
    }


def _surface():
    points = np.array([
        [0., 0., 0.], [1., 0., 0.], [0., 1., 0.],
        [3., 0., 0.], [4., 0., 0.], [4., 1., 0.], [3., 1., 0.],
    ])
    triangles = np.array([[0, 1, 2]], dtype=np.int64)
    quads = np.array([[3, 4, 5, 6]], dtype=np.int64)
    return points, triangles, quads


def _volume(engine: str):
    if engine == "native_hex":
        points = np.array([
            [0., 0., 0.], [1., 0., 0.], [1., 1., 0.], [0., 1., 0.],
            [0., 0., 1.], [1., 0., 1.], [1., 1., 1.], [0., 1., 1.],
        ])
        return points, np.empty((0, 3), dtype=np.int64), np.empty((0, 4), dtype=np.int64), [[0, 1, 2, 3, 4, 5, 6, 7]]
    points = np.array([[0., 0., 0.], [1., 0., 0.],
                       [0., 1., 0.], [0., 0., 1.]])
    return points, np.empty((0, 3), dtype=np.int64), np.empty((0, 4), dtype=np.int64), [[0, 1, 2, 3]]


def _binding(kind: str = "triangle", *, mixed: bool = False):
    rows = [{
        "source_edge": "edge-0", "wall_edge": "wall-0",
        "bl_strip": "strip-0", "output_boundary_face": "out-0",
        "volume_boundary_face": "vol-0", "source_face": "face-0",
        "feature": "flat", "patch": "wall", "physical_group": "fluid",
        "component": "main", "provenance": "direct",
        "wall_front_orthogonality_degrees": 0.0,
    }]
    if mixed:
        rows.append({
            "source_edge": "edge-1", "wall_edge": "wall-1",
            "bl_strip": "strip-1", "output_boundary_face": "out-1",
            "volume_boundary_face": "vol-1", "source_face_a": "face-1",
            "source_face_b": "face-2", "feature": "flat", "patch": "wall",
            "physical_group": "fluid", "component": "main",
            "provenance": "direct", "wall_front_orthogonality_degrees": 0.0,
        })
    return rows


def _call(monkeypatch, engine: str, layers: int, *, manifest=None,
          source=SOURCE, output=OUTPUT, binding=None, candidate="e" * 64,
          points=None, triangles=None, quads=None, cells=None,
          ledger=None, actual=None):
    monkeypatch.setenv("AUTOTESSELL_EXT_BUILD_DIR", str(BUILD))
    source_digest = sha256(source).hexdigest()
    if points is None:
        if engine in {"native_tet", "native_hex", "native_poly"}:
            points, triangles, quads, cells = _volume(engine)
        else:
            points, triangles, quads = _surface()
            cells = []
    if manifest is None:
        manifest = _manifest(engine, layers, output)
    if ledger is None:
        ledger = _ledger(3 if engine == "tri_quad" and layers else 1)
    if actual is None:
        actual = layers
    positive = layers > 0
    return audit_native_l2_evidence(
        engine, source, output, _authority(source_digest), ledger, manifest,
        binding if binding is not None else (_binding(mixed=engine == "tri_quad") if positive else []),
        points, triangles, quads, cells, layers, actual,
        "d" * 64 if positive else "a" * 64,
        candidate if positive else "a" * 64,
    )


def test_l2_audit_accepts_all_six_engine_labels_and_is_deterministic(monkeypatch):
    for engine in ("native_tet", "native_hex", "native_poly",
                   "native_tri", "strict_quad", "tri_quad"):
        first = _call(monkeypatch, engine, 0)
        second = _call(monkeypatch, engine, 0)
        assert first == second
        assert first["accepted"] is True
        assert first["runtime_route"] == "default_off"
        assert first["publication_eligible"] is False
        assert first["repeatable_three_runs"] is True


def test_l2_audit_accepts_positive_surface_bl_and_mixed_provenance(monkeypatch):
    result = _call(monkeypatch, "native_tri", 1)
    assert result["accepted"] is True
    assert result["actual_layers"] == 1
    assert result["topology"]["duplicate"] == 0
    assert result["topology"]["non_manifold"] == 0
    assert result["quality"]["minimum_scaled_jacobian"] > 0
    assert result["quality"]["max_wall_front_orthogonality_degrees"] == 0

    result = _call(monkeypatch, "tri_quad", 1)
    assert result["accepted"] is True
    assert result["topology"]["self_intersection"] == 0


def test_l2_audit_rejects_tamper_layer_binding_and_quality(monkeypatch):
    manifest = _manifest("native_tri", 0)
    result = _call(monkeypatch, "native_tri", 0, output=b"tampered", manifest=manifest)
    assert result["reason"] == "manifest_digest_or_schema_mismatch"

    manifest = _manifest("native_tri", 0)
    manifest["repeat_output_sha256"][2] = "0" * 64
    result = _call(monkeypatch, "native_tri", 0, manifest=manifest)
    assert result["reason"] == "output_repeatability_mismatch"

    result = _call(monkeypatch, "native_tri", 1, actual=0)
    assert result["reason"] == "positive_bl_contract_failed"

    rows = _binding()
    rows[0]["source_face"] = "missing"
    result = _call(monkeypatch, "native_tri", 1, binding=rows)
    assert result["reason"] == "source_binding_invalid"

    points, triangles, quads = _surface()
    bad = points.copy()
    bad[1] = bad[0]
    result = _call(monkeypatch, "native_tri", 1, points=bad,
                   triangles=triangles, quads=quads, cells=[])
    assert result["reason"] == "surface_topology_failed"
