"""Actual staged source/output bindings for the native Gate4 release route."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

from core.evaluator.native_artifact_tree import fingerprint_staged_artifact_tree
from core.evaluator.native_gate4_admission import admit_staged_native_run
from core.evaluator.native_run_manifest_v2 import (
    build_native_run_manifest_v2,
    canonical_manifest_sha256,
)


D = "a" * 64


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _write_json(path: Path, value: object) -> str:
    path.write_text(
        json.dumps(value, ensure_ascii=True, sort_keys=True, separators=(",", ":")),
        encoding="utf-8",
    )
    return _sha256(path)


def _base_manifest(raw_sha: str, authority_sha: str, ledger_sha: str,
                   tree_sha: str, entry_count: int) -> dict:
    source = {
        "kind": "stl", "raw_sha256": raw_sha,
        "canonical_geometry_sha256": D, "parser_version": "stl-parser/1",
        "units": "m", "orientation": "RH",
        "authority_certificate_sha256": authority_sha,
        "raw_path": "source/original.stl",
        "authority_certificate_path": "authority/source-certificate.json",
    }
    semantics = {
        "mapping_table_sha256": D, "features_sha256": D,
        "patches_sha256": D, "physical_groups_sha256": D,
        "components_sha256": D, "provenance_sha256": D,
        "coverage_complete": True, "bijection": True,
        "ledger_sha256": ledger_sha, "ledger_path": "authority/semantic-ledger.json",
    }
    output = {
        "readback_format": "polyMesh", "readback_version": "1",
        "geometry_sha256": D, "topology_sha256": D,
        "boundary_sha256": D, "artifact_tree_sha256": tree_sha,
        "artifact_tree_entry_count": entry_count,
        "source_output_mapping_sha256": D,
        "artifact_tree_path": "output", "mesh_root_path": "output/constant/polyMesh",
    }
    return build_native_run_manifest_v2(
        engine="native-tet", product="volume", source=source,
        cad_authority={"authority_ready": False}, output=output,
        semantics=semantics,
        boundary_layer={
            "requested_layers": 0, "actual_layers": 0, "mode": "disabled_identity",
            "source_geometry_sha256": D, "output_geometry_sha256": D,
            "identity_sha256": D, "lineage_sha256": D,
        },
        quality={
            "witness_schema": "native-quality-witness/v2", "witness_digest": D,
            "p95": 0.2, "p99": 0.3, "max": 0.4, "worst_uid": "cell:0",
            "worst_mapping_coverage": True, "cpp_module_build_sha256": D,
        },
        transaction={
            "baseline_manifest_sha256": D, "candidate_manifest_sha256": D,
            "pre_audit_tree_sha256": D, "post_audit_tree_sha256": D,
            "same_filesystem": True, "fsync_complete": True, "rollback_ready": True,
            "atomic_publish_receipt": {"accepted": True, "receipt_sha256": D},
        },
        replay={
            "config_sha256": D, "seed_policy_sha256": D,
            "native_build_sha256": D, "manifest_digests": [D, D, D],
        },
    )


def _stage(tmp_path: Path) -> tuple[Path, dict]:
    root = tmp_path / "stage"
    source = root / "source"
    authority = root / "authority"
    mesh = root / "output" / "constant" / "polyMesh"
    source.mkdir(parents=True)
    authority.mkdir(parents=True)
    mesh.mkdir(parents=True)
    (source / "original.stl").write_bytes(b"solid authoritative cube\nendsolid cube\n")
    for name, value in {
        "points": "0 0 0\n", "faces": "0 1 2\n", "owner": "0\n",
        "neighbour": "-1\n", "boundary": "wall\n",
    }.items():
        (mesh / name).write_text(value, encoding="utf-8")
    raw_sha = _sha256(source / "original.stl")
    certificate = {
        "schema": "autotessell/source-authority/v1", "kind": "stl",
        "authoritative": True, "source_sha256": raw_sha,
    }
    authority_sha = _write_json(authority / "source-certificate.json", certificate)
    semantic_values = {
        "mapping_table_sha256": D, "features_sha256": D, "patches_sha256": D,
        "physical_groups_sha256": D, "components_sha256": D,
        "provenance_sha256": D, "coverage_complete": True, "bijection": True,
    }
    ledger_sha = _write_json(
        authority / "semantic-ledger.json", {"semantics": semantic_values}
    )
    fingerprint = fingerprint_staged_artifact_tree(root / "output")
    manifest = _base_manifest(
        raw_sha, authority_sha, ledger_sha,
        fingerprint["tree_sha256"], fingerprint["entry_count"],
    )
    (root / "native_run_manifest_v2.json").write_text(
        json.dumps(manifest, ensure_ascii=True, sort_keys=True, separators=(",", ":")),
        encoding="utf-8",
    )
    return root, manifest


def _rewrite_manifest(root: Path, manifest: dict) -> None:
    manifest = dict(manifest)
    manifest.pop("manifest_sha256", None)
    manifest["manifest_sha256"] = canonical_manifest_sha256(manifest)
    (root / "native_run_manifest_v2.json").write_text(
        json.dumps(manifest, ensure_ascii=True, sort_keys=True, separators=(",", ":")),
        encoding="utf-8",
    )


def test_actual_staged_source_authority_semantics_and_cpp_tree_are_admitted(tmp_path):
    root, _ = _stage(tmp_path)
    result = admit_staged_native_run(root)
    assert result["accepted"] is True
    assert result["reasons"] == []
    assert result["artifact_tree"]["entry_count"] == 7


def test_source_mutation_is_refused_even_when_manifest_is_unchanged(tmp_path):
    root, _ = _stage(tmp_path)
    (root / "source" / "original.stl").write_bytes(b"mutated source\n")
    result = admit_staged_native_run(root)
    assert result["accepted"] is False
    assert "source_raw_digest_mismatch" in result["reasons"]


def test_semantic_ledger_mutation_is_refused(tmp_path):
    root, manifest = _stage(tmp_path)
    (root / "authority" / "semantic-ledger.json").write_text(
        json.dumps({"semantics": {"coverage_complete": False}}), encoding="utf-8"
    )
    result = admit_staged_native_run(root)
    assert result["accepted"] is False
    assert "semantic_ledger_digest_mismatch" in result["reasons"]


def test_cad_candidate_without_authoritative_xde_certificate_is_refused(tmp_path):
    root, manifest = _stage(tmp_path)
    manifest["source"]["kind"] = "cad"
    manifest["cad_authority"] = {
        "authority_ready": False, "occt_sdk_version": "7.8",
        "occt_build_id": "build", "occt_abi": "abi",
        "xde_document_sha256": D, "label_mapping_sha256": D,
        "shape_subshape_sha256": D, "name_layer_group_sha256": D,
    }
    _rewrite_manifest(root, manifest)
    result = admit_staged_native_run(root)
    assert result["accepted"] is False
    assert "cad_authority_not_ready" in result["reasons"]
    assert "source_authority_kind_mismatch" in result["reasons"]


def test_cpp_artifact_tree_mutation_is_refused(tmp_path):
    root, _ = _stage(tmp_path)
    (root / "output" / "unexpected.txt").write_text("unsealed\n", encoding="utf-8")
    result = admit_staged_native_run(root)
    assert result["accepted"] is False
    assert "output_artifact_tree_digest_mismatch" in result["reasons"]
