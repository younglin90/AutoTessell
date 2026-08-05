"""Immutable pre-boundary-layer baseline manifest v1."""

from __future__ import annotations

import json
import math
import os
from pathlib import Path
from typing import Any, Mapping

from .native_artifact_tree import fingerprint_staged_artifact_tree
from .native_authority_transaction_gate import canonical_sha256


SCHEMA = "autotessell/immutable-baseline-manifest/v1"
_HEX64 = set("0123456789abcdef")
_MESH_FIELDS = (
    "geometry",
    "topology",
    "boundary_binding",
    "feature_patch_group_multimap",
    "component",
    "provenance",
)
_MESH_DIGEST_FIELDS = _MESH_FIELDS + ("artifact_tree",)


def _digest(value: Any) -> str:
    return canonical_sha256(value)


def _contains_nonfinite(value: Any) -> bool:
    if isinstance(value, float):
        return not math.isfinite(value)
    if isinstance(value, Mapping):
        return any(_contains_nonfinite(item) for item in value.values())
    if isinstance(value, (list, tuple)):
        return any(_contains_nonfinite(item) for item in value)
    return False


def _required(mapping: Mapping[str, Any], key: str, label: str) -> Any:
    if key not in mapping or mapping[key] is None:
        raise ValueError(f"{label}_missing")
    value = mapping[key]
    if _contains_nonfinite(value):
        raise ValueError(f"{label}_nonfinite")
    return value


def build_baseline_manifest_v1(
    *,
    engine: str,
    product_kind: str,
    source: Mapping[str, Any],
    mesh: Mapping[str, Any],
    route_context: Mapping[str, Any],
    artifact_root: str | Path,
) -> dict[str, Any]:
    """Build a path-independent BL=0 manifest from a measured stage tree."""
    source_kind = source.get("kind")
    if source_kind not in {"stl", "cad"}:
        raise ValueError("source.kind must be stl or cad")
    if product_kind not in {"volume", "surface"}:
        raise ValueError("product_kind must be volume or surface")
    if not engine or not isinstance(engine, str):
        raise ValueError("engine_missing")
    if source_kind == "cad" and source.get("authority_ready") is not True:
        raise ValueError("cad_source_authority_not_ready")

    source_record = {
        "kind": source_kind,
        "bytes_sha256": _digest(_required(source, "bytes", "source.bytes")),
        "canonical_geometry_sha256": _digest(
            _required(source, "canonical_geometry", "source.canonical_geometry")
        ),
        "authority_certificate_sha256": _digest(
            _required(source, "authority_certificate", "source.authority_certificate")
        ),
        "parser_version_sha256": _digest(
            _required(source, "parser_version", "source.parser_version")
        ),
        "unit_orientation_profile_sha256": _digest(
            _required(source, "unit_orientation_profile", "source.unit_orientation_profile")
        ),
    }
    artifact = fingerprint_staged_artifact_tree(artifact_root)
    mesh_record = {
        f"{field}_sha256": _digest(_required(mesh, field, f"mesh.{field}"))
        for field in _MESH_FIELDS
    }
    mesh_record["artifact_tree_sha256"] = _required(
        artifact, "tree_sha256", "artifact.tree_sha256"
    )
    mesh_record["artifact_tree_entry_count"] = _required(
        artifact, "entry_count", "artifact.entry_count"
    )
    route_record = {
        "route_contract_sha256": _digest(
            _required(route_context, "route_contract", "route_context.route_contract")
        ),
        "native_build_manifest_sha256": _digest(
            _required(
                route_context,
                "native_build_manifest",
                "route_context.native_build_manifest",
            )
        ),
    }
    manifest: dict[str, Any] = {
        "schema": SCHEMA,
        "engine": engine,
        "product_kind": product_kind,
        "bl": {"requested_layers": 0, "actual_layers": 0},
        "source": source_record,
        "mesh": mesh_record,
        "route_context": route_record,
    }
    manifest["manifest_sha256"] = _digest(manifest)
    return manifest


def validate_baseline_manifest_v1(value: Any) -> tuple[bool, tuple[str, ...]]:
    if not isinstance(value, dict) or value.get("schema") != SCHEMA:
        return False, ("schema",)
    if value.get("bl") != {"requested_layers": 0, "actual_layers": 0}:
        return False, ("baseline_layer_state",)
    source = value.get("source")
    source_fields = (
        "bytes_sha256",
        "canonical_geometry_sha256",
        "authority_certificate_sha256",
        "parser_version_sha256",
        "unit_orientation_profile_sha256",
    )
    if not isinstance(source, dict) or source.get("kind") not in {"stl", "cad"}:
        return False, ("source",)
    if any(
        not isinstance(source.get(field), str)
        or len(source[field]) != 64
        or set(source[field]) - _HEX64
        for field in source_fields
    ):
        return False, ("source_digest",)
    mesh = value.get("mesh")
    if not isinstance(mesh, dict) or any(
        not isinstance(mesh.get(f"{field}_sha256"), str)
        or len(mesh[f"{field}_sha256"]) != 64
        or set(mesh[f"{field}_sha256"]) - _HEX64
        for field in _MESH_DIGEST_FIELDS
    ):
        return False, ("mesh_digest",)
    if (
        not isinstance(mesh.get("artifact_tree_entry_count"), int)
        or isinstance(mesh["artifact_tree_entry_count"], bool)
        or mesh["artifact_tree_entry_count"] < 0
    ):
        return False, ("artifact_tree_entry_count",)
    route = value.get("route_context")
    if not isinstance(route, dict) or any(
        not isinstance(route.get(field), str)
        or len(route[field]) != 64
        or set(route[field]) - _HEX64
        for field in ("route_contract_sha256", "native_build_manifest_sha256")
    ):
        return False, ("route_context_digest",)
    expected = dict(value)
    expected.pop("manifest_sha256", None)
    if value.get("manifest_sha256") != _digest(expected):
        return False, ("manifest_digest",)
    return True, ()


def seal_immutable_baseline_manifest(path: str | Path, manifest: Mapping[str, Any]) -> None:
    valid, reasons = validate_baseline_manifest_v1(dict(manifest))
    if not valid:
        raise ValueError(f"invalid_baseline_manifest:{','.join(reasons)}")
    payload = json.dumps(manifest, ensure_ascii=True, sort_keys=True, separators=(",", ":")).encode("utf-8")
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    descriptor = os.open(target, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o644)
    try:
        os.write(descriptor, payload)
    finally:
        os.close(descriptor)


def compare_bl0_candidate_to_baseline(candidate: Mapping[str, Any], baseline: Mapping[str, Any]) -> dict[str, Any]:
    valid, reasons = validate_baseline_manifest_v1(dict(baseline))
    if not valid:
        return {"accepted": False, "reasons": [f"baseline:{reason}" for reason in reasons]}
    candidate_valid, candidate_reasons = validate_baseline_manifest_v1(dict(candidate))
    if not candidate_valid:
        return {"accepted": False, "reasons": [f"candidate:{reason}" for reason in candidate_reasons]}
    reasons_list: list[str] = []
    if candidate["source"] != baseline["source"]:
        reasons_list.append("source_authority_mismatch")
    if candidate["mesh"] != baseline["mesh"]:
        reasons_list.append("mesh_identity_mismatch")
    if candidate["route_context"] != baseline["route_context"]:
        reasons_list.append("route_context_mismatch")
    return {"accepted": not reasons_list, "reasons": reasons_list}


__all__ = [
    "SCHEMA",
    "build_baseline_manifest_v1",
    "compare_bl0_candidate_to_baseline",
    "seal_immutable_baseline_manifest",
    "validate_baseline_manifest_v1",
]
