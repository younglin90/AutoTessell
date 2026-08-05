from copy import deepcopy

import pytest

from core.evaluator.native_run_manifest_v2 import (
    build_native_run_manifest_v2,
    canonical_manifest_sha256,
    validate_native_run_manifest_v2,
)


D = "a" * 64
E = "b" * 64


def _parts(bl=0, kind="stl"):
    source = {
        "kind": kind, "raw_sha256": D, "canonical_geometry_sha256": D,
        "parser_version": "stl-parser/1", "units": "m",
        "orientation": "RH", "authority_certificate_sha256": D,
    }
    cad = {"authority_ready": False}
    if kind == "cad":
        cad = {
            "authority_ready": True, "occt_sdk_version": "7.8",
            "occt_build_id": "build", "occt_abi": "abi",
            "xde_document_sha256": D, "label_mapping_sha256": D,
            "shape_subshape_sha256": D, "name_layer_group_sha256": D,
        }
    output = {
        "readback_format": "polyMesh", "readback_version": "1",
        "geometry_sha256": D, "topology_sha256": D,
        "boundary_sha256": D, "artifact_tree_sha256": D,
        "source_output_mapping_sha256": D,
    }
    semantics = {
        "mapping_table_sha256": D, "features_sha256": D,
        "patches_sha256": D, "physical_groups_sha256": D,
        "components_sha256": D, "provenance_sha256": D,
        "coverage_complete": True, "bijection": True,
    }
    if bl == 0:
        boundary = {
            "requested_layers": 0, "actual_layers": 0,
            "mode": "disabled_identity", "source_geometry_sha256": D,
            "output_geometry_sha256": D, "identity_sha256": D,
            "lineage_sha256": D,
        }
    else:
        boundary = {
            "requested_layers": bl, "actual_layers": bl, "mode": "wall_edge",
            "wall_edge_layer_sha256": D, "source_face_preservation_sha256": D,
            "outer_front_sha256": D, "positive_thickness": True,
            "positive_area": True, "lineage_complete": True,
        }
    quality = {
        "witness_schema": "native-quality-witness/v2", "witness_digest": D,
        "p95": 0.2, "p99": 0.3, "max": 0.4, "worst_uid": "cell:0",
        "worst_mapping_coverage": True, "cpp_module_build_sha256": D,
    }
    tx = {
        "baseline_manifest_sha256": D, "candidate_manifest_sha256": D,
        "pre_audit_tree_sha256": D, "post_audit_tree_sha256": D,
        "same_filesystem": True, "fsync_complete": True, "rollback_ready": True,
        "atomic_publish_receipt": {"accepted": True, "receipt_sha256": D},
    }
    replay = {
        "config_sha256": D, "seed_policy_sha256": D,
        "native_build_sha256": D, "manifest_digests": [E, E, E],
    }
    return source, cad, output, semantics, boundary, quality, tx, replay


def _manifest(bl=0, kind="stl"):
    values = _parts(bl, kind)
    return build_native_run_manifest_v2(
        engine="native-tet", product="volume", source=values[0],
        cad_authority=values[1], output=values[2], semantics=values[3],
        boundary_layer=values[4], quality=values[5], transaction=values[6],
        replay=values[7],
    )


def test_complete_bl0_manifest_is_accepted_and_reproducible():
    manifest = _manifest(0)
    result = validate_native_run_manifest_v2(manifest, baseline=manifest)
    assert result["accepted"] is True
    assert result["reasons"] == []
    assert result["manifest_sha256"] == manifest["manifest_sha256"]
    reordered = dict(manifest); reordered.pop("manifest_sha256")
    assert canonical_manifest_sha256(reordered) == manifest["manifest_sha256"]


def test_complete_positive_boundary_layer_is_accepted():
    assert validate_native_run_manifest_v2(_manifest(2))["accepted"] is True


def test_missing_quality_witness_refuses_instead_of_defaulting_to_zero():
    manifest = _manifest(0)
    del manifest["quality"]["witness_digest"]
    manifest["manifest_sha256"] = canonical_manifest_sha256(
        {key: value for key, value in manifest.items() if key != "manifest_sha256"}
    )
    result = validate_native_run_manifest_v2(manifest)
    assert result["accepted"] is False
    assert "witness_digest_missing" in result["reasons"]


def test_incomplete_semantic_mapping_and_publish_receipt_refuse():
    manifest = _manifest(0)
    manifest["semantics"]["coverage_complete"] = False
    manifest["transaction"]["atomic_publish_receipt"]["accepted"] = False
    result = validate_native_run_manifest_v2(manifest)
    assert result["accepted"] is False
    assert "semantics_coverage_incomplete" in result["reasons"]
    assert "transaction_atomic_publish_receipt" in result["reasons"]


def test_cad_without_occt_xde_authority_refuses():
    manifest = _manifest(0, "cad")
    del manifest["cad_authority"]["xde_document_sha256"]
    result = validate_native_run_manifest_v2(manifest)
    assert result["accepted"] is False
    assert "xde_document_sha256_missing" in result["reasons"]


def test_non_deterministic_replay_refuses():
    manifest = _manifest(1)
    manifest["replay"]["manifest_digests"][2] = "c" * 64
    result = validate_native_run_manifest_v2(manifest)
    assert result["accepted"] is False
    assert "replay_manifest_not_deterministic" in result["reasons"]
