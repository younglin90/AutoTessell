from __future__ import annotations

import hashlib

from core.generator.native_hex.cad_authority_ingress import (
    validate_native_hex_cad_authority,
)


def _sidecar(source: bytes = b"step-source") -> dict:
    return {
        "schema": "NativeHexCadAuthoritySidecar/v1",
        "source_sha256": hashlib.sha256(source).hexdigest(),
        "canonical_snapshot_sha256": "snapshot-sha",
        "reader_id": "ocp-step-reader/v1",
        "author": "fixture-author",
        "tool": "cad-authority-tool/v1",
        "provenance": "authored-sidecar",
        "orientation_digest": "orientation-sha",
        "seam_digest": "seam-sha",
        "face_count": 2,
        "faces": [
            {
                "face_id": 0,
                "feature": "planar",
                "patch": "wall",
                "physical_group": "fluid_wall",
                "component": "main",
            },
            {
                "face_id": 1,
                "feature": "planar",
                "patch": "outer",
                "physical_group": "fluid_outer",
                "component": "main",
            },
        ],
        "wall_selection": [
            {
                "face_id": 0,
                "directed_curve_ids": ["edge-0"],
                "feature": "planar",
                "patch": "wall",
                "physical_group": "fluid_wall",
                "component": "main",
            }
        ],
        "physical_group_map": {"fluid_wall": 1, "fluid_outer": 2},
        "component_map": {"main": "component-main"},
    }


def test_native_hex_cad_authority_seals_deterministically():
    source = b"step-source"
    first = validate_native_hex_cad_authority(source, "snapshot-sha", _sidecar(source), 2)
    second = validate_native_hex_cad_authority(source, "snapshot-sha", _sidecar(source), 2)
    assert first == second
    assert first["accepted"] is True
    assert first["eligible_for_hex_bl"] is True
    assert first["selected_wall_face_count"] == 1
    assert first["selected_curve_count"] == 1
    assert first["actual_layers"] == 0
    assert first["runtime_route"] == "private_default_off"
    assert first["route_calls"] == 0


def test_digest_or_group_or_wall_selection_missing_refuses_before_mesher():
    source = b"step-source"
    mismatch = _sidecar(source)
    mismatch["canonical_snapshot_sha256"] = "stale"
    refused = validate_native_hex_cad_authority(source, "snapshot-sha", mismatch, 2)
    assert refused["accepted"] is False
    assert refused["reason"] == "source_or_snapshot_digest_mismatch"
    assert refused["candidate_discarded"] is True
    assert refused["route_calls"] == 0

    missing_group = _sidecar(source)
    missing_group.pop("physical_group_map")
    refused = validate_native_hex_cad_authority(source, "snapshot-sha", missing_group, 2)
    assert refused["accepted"] is False
    assert refused["reason"] == "cad_physical_group_map_missing"

    missing_selection = _sidecar(source)
    missing_selection["wall_selection"] = []
    refused = validate_native_hex_cad_authority(source, "snapshot-sha", missing_selection, 2)
    assert refused["accepted"] is False
    assert refused["reason"] == "cad_wall_selection_missing"


def test_duplicate_face_ownership_and_incomplete_face_coverage_refuse():
    source = b"step-source"
    duplicate = _sidecar(source)
    duplicate["wall_selection"].append(dict(duplicate["wall_selection"][0], directed_curve_ids=["edge-1"]))
    refused = validate_native_hex_cad_authority(source, "snapshot-sha", duplicate, 2)
    assert refused["accepted"] is False
    assert refused["reason"] == "cad_wall_face_ownership_ambiguous"

    incomplete = _sidecar(source)
    incomplete["faces"][1]["component"] = ""
    refused = validate_native_hex_cad_authority(source, "snapshot-sha", incomplete, 2)
    assert refused["accepted"] is False
    assert refused["reason"] == "cad_face_label_incomplete"
