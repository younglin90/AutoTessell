"""Gate4 admission for an actual staged native-engine release candidate.

The lower-level manifest validator checks the shape of a release receipt.  This
module performs the missing filesystem binding: every authority digest must
point at a real staged file, the source bytes must hash to the manifest, the
semantic ledger must agree with its declared fields, and the output tree must
be fingerprinted by the first-party C++ bridge.  It intentionally does not
infer features, patches, physical groups, or source/output correspondence.
"""
from __future__ import annotations

import hashlib
import importlib
import json
import sys
from pathlib import Path
from typing import Any, Mapping

from .native_run_manifest_v2 import validate_native_run_manifest_v2

SCHEMA = "autotessell/native-gate4-admission/v1"
DEFAULT_MANIFEST_NAME = "native_run_manifest_v2.json"
_HEX = frozenset("0123456789abcdef")
_SEMANTIC_KEYS = (
    "mapping_table_sha256",
    "features_sha256",
    "patches_sha256",
    "physical_groups_sha256",
    "components_sha256",
    "provenance_sha256",
    "coverage_complete",
    "bijection",
)
_CAD_KEYS = (
    "authority_ready",
    "occt_sdk_version",
    "occt_build_id",
    "occt_abi",
    "xde_document_sha256",
    "label_mapping_sha256",
    "shape_subshape_sha256",
    "name_layer_group_sha256",
)


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _digest(value: Any) -> bool:
    return isinstance(value, str) and len(value) == 64 and not (set(value) - _HEX)


def _safe_staged_path(root: Path, value: Any, reasons: list[str], label: str,
                      *, directory: bool = False) -> Path | None:
    if not isinstance(value, str) or not value:
        reasons.append(f"{label}_path_missing")
        return None
    relative = Path(value)
    if relative.is_absolute() or ".." in relative.parts:
        reasons.append(f"{label}_path_outside_stage")
        return None
    current = root
    for part in relative.parts:
        current = current / part
        if current.is_symlink():
            reasons.append(f"{label}_symlink_forbidden")
            return None
    candidate = current
    try:
        resolved_root = root.resolve(strict=True)
        resolved_candidate = candidate.resolve(strict=True)
        resolved_candidate.relative_to(resolved_root)
    except (OSError, RuntimeError, ValueError):
        reasons.append(f"{label}_path_outside_stage")
        return None
    if directory:
        if not candidate.is_dir():
            reasons.append(f"{label}_directory_missing")
    elif not candidate.is_file():
        reasons.append(f"{label}_file_missing")
    return candidate


def _load_json(path: Path, reasons: list[str], label: str) -> Mapping[str, Any] | None:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError):
        reasons.append(f"{label}_json_invalid")
        return None
    if not isinstance(value, Mapping):
        reasons.append(f"{label}_json_object_required")
        return None
    return value


def _verify_file_reference(root: Path, section: Mapping[str, Any], path_key: str,
                           digest_key: str, reasons: list[str], label: str,
                           *, directory: bool = False) -> tuple[Path | None, str | None]:
    expected = section.get(digest_key)
    if not _digest(expected):
        reasons.append(f"{label}_digest_invalid")
    path = _safe_staged_path(root, section.get(path_key), reasons, label,
                             directory=directory)
    if path is None or directory or not path.is_file():
        return path, None
    actual = _sha256_file(path)
    if actual != expected:
        reasons.append(f"{label}_digest_mismatch")
    return path, actual


def _load_artifact_fingerprint():
    try:
        return importlib.import_module("native_artifact_fingerprint")
    except ImportError:
        build = Path(__file__).resolve().parents[2] / "auto_tessell_core" / "build"
        if build.is_dir() and str(build) not in sys.path:
            sys.path.insert(0, str(build))
        try:
            return importlib.import_module("native_artifact_fingerprint")
        except ImportError as error:
            raise RuntimeError("artifact_tree_kernel_unavailable") from error


def _verify_artifact_tree(root: Path, output: Mapping[str, Any],
                          reasons: list[str]) -> Mapping[str, Any] | None:
    expected = output.get("artifact_tree_sha256")
    if not _digest(expected):
        reasons.append("output_artifact_tree_digest_invalid")
    entry_count = output.get("artifact_tree_entry_count")
    if isinstance(entry_count, bool) or not isinstance(entry_count, int) or entry_count < 1:
        reasons.append("output_artifact_tree_entry_count_invalid")
    tree = _safe_staged_path(
        root, output.get("artifact_tree_path"), reasons, "output_artifact_tree",
        directory=True,
    )
    if tree is None or not tree.is_dir() or not _digest(expected):
        return None
    try:
        fingerprint = _load_artifact_fingerprint().fingerprint_tree(str(tree))
    except (RuntimeError, OSError, ValueError, ImportError):
        reasons.append("output_artifact_tree_kernel_unavailable")
        return None
    if fingerprint.get("tree_sha256") != expected:
        reasons.append("output_artifact_tree_digest_mismatch")
    if fingerprint.get("entry_count") != entry_count:
        reasons.append("output_artifact_tree_entry_count_mismatch")
    return fingerprint


def _check_authority_certificate(root: Path, source: Mapping[str, Any],
                                 cad: Any, reasons: list[str]) -> Mapping[str, Any] | None:
    path, _ = _verify_file_reference(
        root, source, "authority_certificate_path",
        "authority_certificate_sha256", reasons, "source_authority_certificate",
    )
    if path is None:
        return None
    certificate = _load_json(path, reasons, "source_authority_certificate")
    if certificate is None:
        return None
    if certificate.get("authoritative") is not True:
        reasons.append("source_authority_not_authoritative")
    certificate_kind = certificate.get("kind", certificate.get("source_kind"))
    if certificate_kind is not None and certificate_kind != source.get("kind"):
        reasons.append("source_authority_kind_mismatch")
    certificate_source_digest = certificate.get(
        "source_sha256", certificate.get("raw_sha256")
    )
    if certificate_source_digest != source.get("raw_sha256"):
        reasons.append("source_authority_raw_digest_mismatch")
    if source.get("kind") == "cad":
        if not isinstance(cad, Mapping):
            reasons.append("cad_authority_section")
        certificate_cad = certificate.get("cad_authority", certificate)
        if not isinstance(certificate_cad, Mapping):
            reasons.append("cad_authority_certificate_section")
        else:
            for key in _CAD_KEYS:
                if certificate_cad.get(key) != cad.get(key):
                    reasons.append(f"cad_authority_certificate_{key}_mismatch")
    return certificate


def _check_semantic_ledger(root: Path, semantics: Mapping[str, Any],
                           reasons: list[str]) -> Mapping[str, Any] | None:
    path, _ = _verify_file_reference(
        root, semantics, "ledger_path", "ledger_sha256", reasons,
        "semantic_ledger",
    )
    if path is None:
        return None
    ledger = _load_json(path, reasons, "semantic_ledger")
    if ledger is None:
        return None
    payload = ledger.get("semantics", ledger)
    if not isinstance(payload, Mapping):
        reasons.append("semantic_ledger_section")
        return ledger
    for key in _SEMANTIC_KEYS:
        if payload.get(key) != semantics.get(key):
            reasons.append(f"semantic_ledger_{key}_mismatch")
    return ledger


def admit_staged_native_run(
    staged_root: str | Path,
    *,
    baseline: Mapping[str, Any] | None = None,
    manifest_name: str = DEFAULT_MANIFEST_NAME,
) -> dict[str, Any]:
    """Admit one staged candidate only when all Gate4 bindings are measured."""
    root = Path(staged_root)
    reasons: list[str] = []
    if root.is_symlink() or not root.is_dir():
        return {"schema": SCHEMA, "accepted": False,
                "reasons": ["stage_directory_invalid"]}
    manifest_path = _safe_staged_path(root, manifest_name, reasons, "manifest")
    if manifest_path is None:
        return {"schema": SCHEMA, "accepted": False, "reasons": sorted(set(reasons))}
    manifest = _load_json(manifest_path, reasons, "manifest")
    if manifest is None:
        return {"schema": SCHEMA, "accepted": False, "reasons": sorted(set(reasons))}
    validation = validate_native_run_manifest_v2(manifest, baseline=baseline)
    reasons.extend(validation["reasons"])
    source = manifest.get("source")
    output = manifest.get("output")
    semantics = manifest.get("semantics")
    if not isinstance(source, Mapping):
        reasons.append("source_section")
    else:
        raw_path, raw_actual = _verify_file_reference(
            root, source, "raw_path", "raw_sha256", reasons, "source_raw",
        )
        if raw_path is None:
            raw_actual = None
        _check_authority_certificate(
            root, source, manifest.get("cad_authority"), reasons,
        )
    if not isinstance(semantics, Mapping):
        reasons.append("semantics_section")
    else:
        _check_semantic_ledger(root, semantics, reasons)
    artifact = None
    if not isinstance(output, Mapping):
        reasons.append("output_section")
    else:
        mesh_root = _safe_staged_path(
            root, output.get("mesh_root_path"), reasons, "output_mesh_root",
            directory=True,
        )
        if mesh_root is None:
            pass
        artifact = _verify_artifact_tree(root, output, reasons)
    return {
        "schema": SCHEMA,
        "accepted": not reasons,
        "reasons": sorted(set(reasons)),
        "manifest_sha256": validation.get("manifest_sha256"),
        "source_sha256": raw_actual if isinstance(source, Mapping) else None,
        "artifact_tree": dict(artifact) if isinstance(artifact, Mapping) else None,
        "manifest_path": str(manifest_path.relative_to(root)),
    }


__all__ = ["SCHEMA", "DEFAULT_MANIFEST_NAME", "admit_staged_native_run"]
