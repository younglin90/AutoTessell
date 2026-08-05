from __future__ import annotations

import sys
from pathlib import Path

import numpy as np

BUILD = Path("auto_tessell_core/build").resolve()
if str(BUILD) not in sys.path:
    sys.path.insert(0, str(BUILD))

from native_surface_bl_strip_writer import write_authoritative_surface_bl_strip  # noqa: E402


def _authority() -> dict[str, str]:
    return {
        "source_kind": "synthetic_surface_fixture",
        "source_sha256": "sha-source",
        "boundary_mapping_sha256": "sha-boundary",
        "physical_group_sha256": "sha-groups",
        "provenance": "sealed-test-ledger",
    }


def _provenance() -> list[dict[str, str | int]]:
    return [
        {
            "source_wall_edge": 11,
            "source_face": 0,
            "patch": "wall",
            "feature": "smooth",
            "physical_group": "fluid_wall",
            "component": "main",
            "provenance": "fixture-ledger",
        }
    ]


def _inputs():
    points = np.array(
        [
            [0.0, 0.0, 0.0],
            [1.0, 0.0, 0.0],
            [0.0, 1.0, 0.0],
            [0.0, 0.0, 0.8],
            [1.0, 0.0, 0.8],
        ],
        dtype=float,
    )
    source_triangles = np.array([[0, 1, 2]], dtype=np.int64)
    edges = np.array([[11, 0, 1, 0]], dtype=np.int64)
    layer_ids = np.array([[[3, 4]]], dtype=np.int64)
    normals = np.array([[0.0, 0.0, 1.0]], dtype=float)
    return points, source_triangles, edges, layer_ids, normals


def _call(layers: int = 1, provenance=None):
    points, triangles, edges, layer_ids, normals = _inputs()
    return write_authoritative_surface_bl_strip(
        points,
        triangles,
        edges,
        layer_ids if layers else np.empty((0, 1, 2), dtype=np.int64),
        normals,
        _authority(),
        _provenance() if provenance is None else provenance,
        layers,
    )


def test_bl0_is_identity_and_has_no_sidecar_faces():
    result = _call(0)
    assert result["accepted"] is True
    assert result["status"] == "surface_bl_actual_strip_bl0_identity"
    assert result["generated_faces"] == []
    assert result["publication_eligible"] is False


def test_positive_strip_is_quality_gated_deterministic_and_provenance_bound():
    first = _call(1)
    second = _call(1)
    assert first == second
    assert first["accepted"] is True
    assert first["status"] == "surface_bl_actual_strip_artifact_sealed"
    assert first["topology_invalid"] == 0
    assert first["topology_inverted"] == 0
    assert first["topology_duplicate"] == 0
    assert first["topology_non_manifold"] == 0
    assert len(first["generated_faces"]) == 3
    assert len(first["provenance"]) == 1
    assert first["provenance"][0]["final_face_ids"] == (1, 2)
    decision = first["diagonal_decisions"][0]
    assert decision["skewness"] <= 0.50
    assert decision["metric_aspect_ratio"] <= 10.0
    assert decision["non_orthogonality"] <= 75.0


def test_missing_authority_or_lineage_refuses_without_faces():
    points, triangles, edges, layer_ids, normals = _inputs()
    refused = write_authoritative_surface_bl_strip(
        points,
        triangles,
        edges,
        layer_ids,
        normals,
        {"source_kind": "stl"},
        _provenance(),
        1,
    )
    assert refused["accepted"] is False
    assert refused["reason"] == "authority_unsealed"
    assert refused["generated_faces"] == []

    missing = _call(1, provenance=[{"source_wall_edge": 11}])
    assert missing["accepted"] is False
    assert missing["reason"] == "direct_id_or_provenance_missing"
    assert missing["generated_faces"] == []
