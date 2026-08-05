"""L0 authoritative B-Rep bridge and private optimizer ingress tests."""

from __future__ import annotations

from pathlib import Path

import numpy as np

from core.evaluator.native_surface_bl_front_authority_bridge import bridge_authoritative_surface_wall_edge
from core.evaluator.native_surface_bl_front_optimizer import optimize_surface_wall_edge_front


BUILD = Path("/tmp/autotessell_surface_bl_front_shared_build")


def _case():
    points = np.array([[0, 0, 0], [1, 0, 0], [1, 1, 0]], dtype=np.float64)
    edges = np.array([[101, 0, 1, 0], [102, 1, 2, 0]], dtype=np.int64)
    normals = np.array([[0, 0, 1]], dtype=np.float64)
    evidence = {
        "accepted": True,
        "version": "v2",
        "source_kind": "step",
        "raw_sha256": "raw-step-sha",
        "brep_hash": "brep-sha",
        "source_digest": "source-digest",
        "seam_digest": "seam-digest",
        "orientation_digest": "orientation-digest",
        "face_ordinal_digest": "ordinal-digest",
        "provenance_digest": "provenance-digest",
    }
    direction = [{"face": 0, "source_face": 0, "orientation": "forward", "seam": "none", "normal": "n0", "direction": "d0"}]
    mapping = [
        {
            "source_edge": int(row[0]),
            "source_face": int(row[3]),
            "wall_edge": f"wall-{int(row[0])}",
            "output_face": f"out-{int(row[0])}",
            "patch": "wall",
            "feature": "smooth",
            "physical_group": "fluid-wall",
            "component": "body-0",
            "provenance": "direct-v2",
            "mapping_source": "explicit_user",
            "direct": True,
        }
        for row in edges
    ]
    digests = {"source_digest": "source-digest", "seam_digest": "seam-digest", "orientation_digest": "orientation-digest", "face_ordinal_digest": "ordinal-digest", "mapping_digest": "mapping-digest"}
    return points, edges, normals, evidence, direction, mapping, digests


def test_bl0_and_bl1_authoritative_receipts_are_deterministic(monkeypatch):
    monkeypatch.setenv("AUTOTESSELL_EXT_BUILD_DIR", str(BUILD))
    args = _case()
    for layers in (0, 1, 3):
        first = bridge_authoritative_surface_wall_edge(*args[:3], layers, *args[3:])
        second = bridge_authoritative_surface_wall_edge(*args[:3], layers, *args[3:])
        assert first == second
        assert first["accepted"] is True
        assert first["actual_layers"] == layers
        assert first["runtime_route"] == "default_off"
        assert first["publication_eligible"] is False
        assert first["route_calls"] == 0
        assert first["optimizer_ingress"]["source_certificate"]["authority"] == "brep-front-evidence-v2-explicit-mapping"


def test_bridge_receipt_can_feed_041_optimizer_without_route(monkeypatch):
    monkeypatch.setenv("AUTOTESSELL_EXT_BUILD_DIR", str(BUILD))
    points, edges, normals, evidence, direction, mapping, digests = _case()
    bridge = bridge_authoritative_surface_wall_edge(points, edges, normals, 1, evidence, direction, mapping, digests)
    ingress = bridge["optimizer_ingress"]
    result = optimize_surface_wall_edge_front(
        ingress["points"], ingress["edges"], ingress["face_normals"], ["wall"], ["smooth"], ["fluid-wall"], 1, 0.01, 1.2, ingress["source_certificate"], ingress["edge_provenance"]
    )
    assert result["accepted"] is True
    assert result["actual_layers"] == 1
    assert result["runtime_route"] == "default_off"
    assert result["publication_eligible"] is False
    assert all(item["wall_edge"] for item in result["provenance"])


def test_missing_mapping_digest_owner_and_xde_only_group_fail_closed(monkeypatch):
    monkeypatch.setenv("AUTOTESSELL_EXT_BUILD_DIR", str(BUILD))
    points, edges, normals, evidence, direction, mapping, digests = _case()
    for bad_mapping, expected in (
        (mapping[:-1], "authority_mapping_coverage_incomplete"),
        ([dict(mapping[0], source_edge=999), mapping[1]], "mapping_owner_mismatch"),
        ([dict(mapping[0], mapping_source="xde_name"), mapping[1]], "physical_group_mapping_not_explicit"),
    ):
        result = bridge_authoritative_surface_wall_edge(points, edges, normals, 1, evidence, direction, bad_mapping, digests)
        assert result["accepted"] is False
        assert result["reason"] == expected
        assert result["actual_layers"] == 0
    result = bridge_authoritative_surface_wall_edge(points, edges, normals, 1, evidence, direction, mapping, dict(digests, mapping_digest="mutated"))
    assert result["accepted"] is True
    assert result["receipt_digest"].endswith("|mutated|1")
