"""Fail-closed manifest and digest contracts."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

from core.utils.native_extension_manifest import SCHEMA, verify_native_extension_manifest


def _write_manifest(root: Path, *, relative: str = "native_extensions/fixture.py") -> Path:
    binary = root / relative
    binary.parent.mkdir(parents=True, exist_ok=True)
    binary.write_text("ABI_MARKER = 7\n", encoding="utf-8")
    payload = {
        "schema": SCHEMA,
        "module": "native_manifest_fixture",
        "python_soabi": "source",
        "extension_suffix": ".py",
        "install_relative_path": relative,
        "binary_sha256": hashlib.sha256(binary.read_bytes()).hexdigest(),
        "sources": [],
        "source_identity": "test",
        "build": {"cxx_standard": 23},
        "authority_receipt_sha256": "a" * 64,
    }
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    payload["manifest_payload_sha256"] = hashlib.sha256(encoded.encode()).hexdigest()
    manifest = root / "native-extension-manifest.json"
    manifest.write_text(json.dumps(payload, sort_keys=True), encoding="utf-8")
    return manifest


def test_verified_manifest_resolves_install_relative_binary(tmp_path: Path) -> None:
    manifest = _write_manifest(tmp_path)
    path, reason = verify_native_extension_manifest(
        manifest, module_name="native_manifest_fixture"
    )
    assert reason == ""
    assert path == (tmp_path / "native_extensions/fixture.py").resolve()


def test_binary_tamper_is_rejected(tmp_path: Path) -> None:
    manifest = _write_manifest(tmp_path)
    (tmp_path / "native_extensions/fixture.py").write_text("ABI_MARKER = 8\n", encoding="utf-8")
    path, reason = verify_native_extension_manifest(manifest, module_name="native_manifest_fixture")
    assert path is None
    assert reason == "manifest_binary_digest_mismatch"


def test_manifest_path_traversal_is_rejected(tmp_path: Path) -> None:
    manifest = _write_manifest(tmp_path, relative="../escape.py")
    path, reason = verify_native_extension_manifest(manifest, module_name="native_manifest_fixture")
    assert path is None
    assert reason == "manifest_path_traversal"
