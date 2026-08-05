"""Opt-in, read-back release evidence contract for every native engine."""
from __future__ import annotations
import hashlib
import json
import math
from typing import Any, Mapping

SCHEMA = "autotessell/native-run-manifest/v2"
VERSION = 2
_HEX = frozenset("0123456789abcdef")


def _bytes(value: Any) -> bytes:
    return json.dumps(value, allow_nan=False, ensure_ascii=True,
                      separators=(",", ":"), sort_keys=True).encode()


def canonical_manifest_sha256(value: Any) -> str:
    return hashlib.sha256(_bytes(value)).hexdigest()


def _finite(value: Any) -> bool:
    if isinstance(value, float):
        return math.isfinite(value)
    if isinstance(value, Mapping):
        return all(_finite(v) for v in value.values())
    if isinstance(value, (list, tuple)):
        return all(_finite(v) for v in value)
    return True


def _get(obj: Mapping[str, Any], path: str) -> Any:
    value: Any = obj
    for part in path.split("."):
        if not isinstance(value, Mapping) or part not in value or value[part] is None:
            raise ValueError("{}_missing".format(path))
        value = value[part]
    if not _finite(value):
        raise ValueError("{}_nonfinite".format(path))
    return value


def _require(obj: Mapping[str, Any], paths: tuple[str, ...]) -> list[str]:
    reasons = []
    for path in paths:
        try:
            _get(obj, path)
        except ValueError as exc:
            reasons.append(str(exc))
    return reasons


def _digest(obj: Mapping[str, Any], key: str, prefix: str, reasons: list[str]) -> None:
    try:
        value = _get(obj, key)
        if not isinstance(value, str) or len(value) != 64 or set(value) - _HEX:
            reasons.append("{}.{}_invalid_digest".format(prefix, key))
    except ValueError as exc:
        reasons.append(str(exc))


def _true(obj: Mapping[str, Any], key: str, reason: str, reasons: list[str]) -> None:
    try:
        if _get(obj, key) is not True:
            reasons.append(reason)
    except ValueError as exc:
        reasons.append(str(exc))


def build_native_run_manifest_v2(
    *, engine: str, product: str, source: Mapping[str, Any],
    cad_authority: Mapping[str, Any], output: Mapping[str, Any],
    semantics: Mapping[str, Any], boundary_layer: Mapping[str, Any],
    quality: Mapping[str, Any], transaction: Mapping[str, Any],
    replay: Mapping[str, Any],
) -> dict[str, Any]:
    if not isinstance(engine, str) or not engine:
        raise ValueError("engine_missing")
    if not isinstance(product, str) or not product:
        raise ValueError("product_missing")
    result = {
        "schema": SCHEMA, "version": VERSION, "engine": engine,
        "product": product, "source": dict(source),
        "cad_authority": dict(cad_authority), "output": dict(output),
        "semantics": dict(semantics), "boundary_layer": dict(boundary_layer),
        "quality": dict(quality), "transaction": dict(transaction),
        "replay": dict(replay),
    }
    result["manifest_sha256"] = canonical_manifest_sha256(result)
    return result


def validate_native_run_manifest_v2(
    manifest: Any, *, baseline: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    if not isinstance(manifest, Mapping):
        return {"accepted": False, "reasons": ["manifest_type"]}
    reasons: list[str] = []
    if manifest.get("schema") != SCHEMA:
        reasons.append("schema")
    if manifest.get("version") != VERSION:
        reasons.append("version")
    reasons += _require(manifest, (
        "engine", "product", "source", "output", "semantics",
        "boundary_layer", "quality", "transaction", "replay",
    ))
    source, output = manifest.get("source"), manifest.get("output")
    sem, bl = manifest.get("semantics"), manifest.get("boundary_layer")
    quality = manifest.get("quality")
    tx, replay = manifest.get("transaction"), manifest.get("replay")
    for name, section in (("source", source), ("output", output),
                          ("semantics", sem), ("boundary_layer", bl),
                          ("quality", quality), ("transaction", tx),
                          ("replay", replay)):
        if not isinstance(section, Mapping):
            reasons.append("{}_section".format(name))
    if not isinstance(source, Mapping) or not isinstance(output, Mapping):
        return {"accepted": False, "reasons": sorted(set(reasons))}
    reasons += _require(source, (
        "kind", "raw_sha256", "canonical_geometry_sha256", "parser_version",
        "units", "orientation", "authority_certificate_sha256",
    ))
    for key in ("raw_sha256", "canonical_geometry_sha256",
                "authority_certificate_sha256"):
        _digest(source, key, "source", reasons)
    reasons += _require(output, (
        "readback_format", "readback_version", "geometry_sha256",
        "topology_sha256", "boundary_sha256", "artifact_tree_sha256",
        "source_output_mapping_sha256",
    ))
    for key in ("geometry_sha256", "topology_sha256", "boundary_sha256",
                "artifact_tree_sha256", "source_output_mapping_sha256"):
        _digest(output, key, "output", reasons)
    if source.get("kind") not in {"stl", "cad"}:
        reasons.append("source_kind")
    cad = manifest.get("cad_authority")
    if source.get("kind") == "cad":
        if not isinstance(cad, Mapping):
            reasons.append("cad_authority_section")
        else:
            reasons += _require(cad, (
                "authority_ready", "occt_sdk_version", "occt_build_id",
                "occt_abi", "xde_document_sha256", "label_mapping_sha256",
                "shape_subshape_sha256", "name_layer_group_sha256",
            ))
            _true(cad, "authority_ready", "cad_authority_not_ready", reasons)
            for key in ("xde_document_sha256", "label_mapping_sha256",
                        "shape_subshape_sha256", "name_layer_group_sha256"):
                _digest(cad, key, "cad_authority", reasons)
    if isinstance(sem, Mapping):
        reasons += _require(sem, (
            "mapping_table_sha256", "features_sha256", "patches_sha256",
            "physical_groups_sha256", "components_sha256", "provenance_sha256",
            "coverage_complete", "bijection",
        ))
        for key in ("mapping_table_sha256", "features_sha256", "patches_sha256",
                    "physical_groups_sha256", "components_sha256",
                    "provenance_sha256"):
            _digest(sem, key, "semantics", reasons)
        _true(sem, "coverage_complete", "semantics_coverage_incomplete", reasons)
        _true(sem, "bijection", "semantics_bijection_false", reasons)
    if isinstance(bl, Mapping):
        reasons += _require(bl, ("requested_layers", "actual_layers", "mode"))
        try:
            requested, actual = _get(bl, "requested_layers"), _get(bl, "actual_layers")
            if not isinstance(requested, int) or isinstance(requested, bool) or requested < 0:
                reasons.append("boundary_layer_requested_invalid")
            if not isinstance(actual, int) or isinstance(actual, bool) or actual < 0:
                reasons.append("boundary_layer_actual_invalid")
            if requested != actual:
                reasons.append("boundary_layer_count_mismatch")
            if requested == 0 and actual == 0:
                if bl.get("mode") != "disabled_identity":
                    reasons.append("bl0_mode")
                reasons += _require(bl, ("source_geometry_sha256",
                    "output_geometry_sha256", "identity_sha256", "lineage_sha256"))
            elif isinstance(requested, int) and requested > 0:
                reasons += _require(bl, ("wall_edge_layer_sha256",
                    "source_face_preservation_sha256", "outer_front_sha256",
                    "positive_thickness", "positive_area", "lineage_complete"))
                for key in ("wall_edge_layer_sha256",
                            "source_face_preservation_sha256", "outer_front_sha256"):
                    _digest(bl, key, "boundary_layer", reasons)
                for key in ("positive_thickness", "positive_area", "lineage_complete"):
                    _true(bl, key, "boundary_layer_{}".format(key), reasons)
        except ValueError as exc:
            reasons.append(str(exc))
    if isinstance(quality, Mapping):
        reasons += _require(quality, ("witness_schema", "witness_digest",
            "p95", "p99", "max", "worst_uid", "worst_mapping_coverage",
            "cpp_module_build_sha256"))
        _digest(quality, "witness_digest", "quality", reasons)
        _digest(quality, "cpp_module_build_sha256", "quality", reasons)
        _true(quality, "worst_mapping_coverage",
              "quality_worst_mapping_coverage", reasons)
        for key in ("p95", "p99", "max"):
            try:
                value = _get(quality, key)
                if isinstance(value, bool) or not isinstance(value, (int, float)) or value < 0:
                    reasons.append("quality_{}_invalid".format(key))
            except ValueError as exc:
                reasons.append(str(exc))
    if isinstance(tx, Mapping):
        reasons += _require(tx, ("baseline_manifest_sha256",
            "candidate_manifest_sha256", "pre_audit_tree_sha256",
            "post_audit_tree_sha256", "same_filesystem", "fsync_complete",
            "rollback_ready", "atomic_publish_receipt"))
        for key in ("baseline_manifest_sha256", "candidate_manifest_sha256",
                    "pre_audit_tree_sha256", "post_audit_tree_sha256"):
            _digest(tx, key, "transaction", reasons)
        for key in ("same_filesystem", "fsync_complete", "rollback_ready"):
            _true(tx, key, "transaction_{}".format(key), reasons)
        receipt = tx.get("atomic_publish_receipt")
        if not isinstance(receipt, Mapping) or receipt.get("accepted") is not True:
            reasons.append("transaction_atomic_publish_receipt")
    if isinstance(replay, Mapping):
        reasons += _require(replay, ("config_sha256", "seed_policy_sha256",
                                      "native_build_sha256", "manifest_digests"))
        for key in ("config_sha256", "seed_policy_sha256", "native_build_sha256"):
            _digest(replay, key, "replay", reasons)
        digests = replay.get("manifest_digests")
        if not isinstance(digests, list) or len(digests) < 3:
            reasons.append("replay_manifest_digests")
        elif any(not isinstance(x, str) or len(x) != 64 or set(x) - _HEX
                 for x in digests):
            reasons.append("replay_manifest_digest_format")
        elif len(set(digests)) != 1:
            reasons.append("replay_manifest_not_deterministic")
    if baseline is not None and isinstance(bl, Mapping):
        try:
            if _get(bl, "requested_layers") == 0 and baseline.get("output") != output:
                reasons.append("bl0_baseline_output_identity")
        except ValueError as exc:
            reasons.append(str(exc))
    computed = canonical_manifest_sha256({
        key: value for key, value in manifest.items() if key != "manifest_sha256"
    })
    if manifest.get("manifest_sha256") is None:
        reasons.append("manifest_sha256_missing")
    elif manifest.get("manifest_sha256") != computed:
        reasons.append("manifest_sha256_mismatch")
    return {"accepted": not reasons, "reasons": sorted(set(reasons)),
            "manifest_sha256": computed}


__all__ = ["SCHEMA", "VERSION", "build_native_run_manifest_v2",
           "canonical_manifest_sha256", "validate_native_run_manifest_v2"]
