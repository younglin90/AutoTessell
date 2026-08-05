"""Verified install-relative first-party native extension manifests."""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
from typing import Any


SCHEMA = "autotessell/native-extension-manifest/v1"


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _payload_digest(value: dict[str, Any]) -> str:
    payload = dict(value)
    payload.pop("manifest_payload_sha256", None)
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def _relative_candidate(root: Path, relative: object) -> tuple[Path | None, str]:
    if not isinstance(relative, str) or not relative or os.path.isabs(relative):
        return None, "manifest_path_not_relative"
    raw = Path(relative)
    if any(part == ".." for part in raw.parts):
        return None, "manifest_path_traversal"
    unresolved = root / raw
    current = root
    for part in raw.parts:
        current = current / part
        if current.is_symlink():
            return None, "manifest_symlink_forbidden"
    candidate = unresolved.resolve()
    try:
        candidate.relative_to(root)
    except ValueError:
        return None, "manifest_path_traversal"
    return candidate, ""


def _select_entry(manifest: dict[str, Any], module_name: str) -> tuple[dict[str, Any] | None, str]:
    modules = manifest.get("modules")
    if modules is not None:
        if not isinstance(modules, list) or not modules:
            return None, "manifest_modules_invalid"
        seen: set[str] = set()
        selected: dict[str, Any] | None = None
        for entry in modules:
            if not isinstance(entry, dict) or not isinstance(entry.get("module"), str):
                return None, "manifest_module_entry_invalid"
            name = entry["module"]
            if name in seen:
                return None, "manifest_module_duplicate"
            seen.add(name)
            if name == module_name:
                selected = entry
        if selected is None:
            return None, "manifest_module_mismatch"
        return selected, ""
    if manifest.get("module") != module_name:
        return None, "manifest_module_mismatch"
    return manifest, ""


def _verify_receipt(
    *, root: Path, manifest: dict[str, Any], entry: dict[str, Any], candidate: Path
) -> str:
    receipt_relative = entry.get(
        "authority_receipt_relative_path", manifest.get("authority_receipt_relative_path")
    )
    expected_receipt = entry.get(
        "authority_receipt_sha256", manifest.get("authority_receipt_sha256")
    )
    if not isinstance(expected_receipt, str) or len(expected_receipt) != 64:
        return "manifest_authority_digest_missing"
    if receipt_relative is None:
        # Legacy single-module manifests only carried an external authority
        # digest. Keep that format valid; bundle producers use the bound receipt.
        return ""
    receipt, reason = _relative_candidate(root, receipt_relative)
    if receipt is None:
        return reason
    if not receipt.is_file():
        return "manifest_authority_receipt_missing"
    if _sha256(receipt) != expected_receipt.lower():
        return "manifest_authority_receipt_digest_mismatch"
    try:
        payload = json.loads(receipt.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return "manifest_authority_receipt_unreadable"
    if not isinstance(payload, dict):
        return "manifest_authority_receipt_invalid"
    rows = payload.get("modules")
    if rows is None:
        rows = [payload]
    if not isinstance(rows, list):
        return "manifest_authority_receipt_invalid"
    matches = [row for row in rows if isinstance(row, dict) and row.get("module") == entry.get("module")]
    if len(matches) != 1:
        return "manifest_authority_receipt_module_mismatch"
    row = matches[0]
    if row.get("binary_sha256") != entry.get("binary_sha256"):
        return "manifest_authority_receipt_binary_mismatch"
    if _sha256(candidate) != row.get("binary_sha256"):
        return "manifest_authority_receipt_binary_mismatch"
    sources = entry.get("sources")
    receipt_sources = row.get("sources")
    if sources is not None and receipt_sources is not None and sources != receipt_sources:
        return "manifest_authority_receipt_source_mismatch"
    return ""


def verify_native_extension_manifest(
    manifest_path: Path,
    *,
    module_name: str,
) -> tuple[Path | None, str]:
    """Return a verified binary path or a stable fail-closed reason.

    v1 accepts the original single-module shape and an additive ``modules``
    bundle shape. Bundle entries are independently selected and verified, so a
    producer cannot accidentally satisfy a request for its readback verifier.
    """

    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None, "manifest_unreadable"
    if not isinstance(manifest, dict) or manifest.get("schema") != SCHEMA:
        return None, "manifest_schema_invalid"
    if manifest.get("manifest_payload_sha256") != _payload_digest(manifest):
        return None, "manifest_payload_digest_mismatch"
    entry, reason = _select_entry(manifest, module_name)
    if entry is None:
        return None, reason
    root = manifest_path.parent.resolve()
    candidate, reason = _relative_candidate(root, entry.get("install_relative_path"))
    if candidate is None:
        return None, reason
    if not candidate.is_file():
        return None, "manifest_binary_missing"
    expected = entry.get("binary_sha256")
    if not isinstance(expected, str) or len(expected) != 64:
        return None, "manifest_binary_digest_missing"
    if _sha256(candidate) != expected.lower():
        return None, "manifest_binary_digest_mismatch"
    suffix = entry.get("extension_suffix")
    if not isinstance(suffix, str) or not suffix or not candidate.name.endswith(suffix):
        return None, "manifest_extension_identity_mismatch"
    authority_reason = _verify_receipt(
        root=root, manifest=manifest, entry=entry, candidate=candidate
    )
    if authority_reason:
        return None, authority_reason
    return candidate, ""


def release_manifest_path() -> Path | None:
    explicit = os.environ.get("AUTOTESSELL_NATIVE_MANIFEST", "").strip()
    if explicit:
        return Path(explicit)
    return None


__all__ = ["SCHEMA", "release_manifest_path", "verify_native_extension_manifest"]
