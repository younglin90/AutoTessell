"""L0 contract tests for B-Rep ownership and collision contact classes."""

from __future__ import annotations

import copy
import sys
from pathlib import Path

sys.path.insert(0, "/tmp/autotessell_surface_bl_front_shared_build")
from native_brep_front_evidence import classify_brep_contact, validate_brep_front_evidence  # noqa: E402


def _evidence() -> dict:
    return {
        "schema": "BRepFrontEvidence/v1",
        "source_digest": "a" * 64,
        "triangles": [
            {"triangle_id": 0, "brep_face_id": 10, "canonical_vertices": [0, 1, 2], "raw_vertices": [0, 1, 2], "orientation_reversed": False},
            {"triangle_id": 1, "brep_face_id": 11, "canonical_vertices": [1, 3, 2], "raw_vertices": [1, 3, 2], "orientation_reversed": False},
        ],
        "edges": [
            {"brep_edge_id": 100, "owner_face_id": 10, "canonical_endpoints": [0, 1], "incident_faces": [10, 11], "incident_triangles": [0, 1]},
            {"brep_edge_id": 101, "owner_face_id": 10, "canonical_endpoints": [1, 2], "incident_faces": [10], "incident_triangles": [0]},
        ],
    }


def test_valid_brep_contract_and_contact_policy() -> None:
    evidence = _evidence()
    result = validate_brep_front_evidence(evidence)
    assert result == {
        "accepted": True,
        "status": "brep_evidence_ready",
        "schema": "BRepFrontEvidence/v1",
        "source_digest": "a" * 64,
        "triangle_count": 2,
        "edge_count": 2,
        "canonical_vertex_count": 4,
        "contact_policy": "owner_face_or_verified_seam_only",
        "uncertain_is_refusal": True,
    }
    assert classify_brep_contact(evidence, 100, 0, "base_touch")["permitted"] is True
    assert classify_brep_contact(evidence, 100, 1, "seam_touch")["permitted"] is True
    assert classify_brep_contact(evidence, 100, 1, "base_touch")["permitted"] is False
    assert classify_brep_contact(evidence, 100, 1, "crossing")["permitted"] is False
    assert classify_brep_contact(evidence, 100, 1, "uncertain")["decision"] == "forbidden_or_uncertain_refusal"


def test_brep_contract_mutations_fail_closed() -> None:
    mutations = (
        lambda value: value.update({"schema": "wrong"}),
        lambda value: value.update({"source_digest": "stale"}),
        lambda value: value["triangles"].append(copy.deepcopy(value["triangles"][0])),
        lambda value: value["edges"][0].update({"owner_face_id": 99}),
        lambda value: value["edges"][0].update({"canonical_endpoints": [0, 0]}),
        lambda value: value["edges"][0].update({"incident_triangles": [99]}),
    )
    for mutate in mutations:
        value = _evidence()
        mutate(value)
        assert validate_brep_front_evidence(value)["accepted"] is False
