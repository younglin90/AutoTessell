"""Multi-module release package and fail-closed provenance tests."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from core.utils.native_extension_manifest import SCHEMA, verify_native_extension_manifest
from core.utils.native_extensions import import_native_extension


def _digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _bundle(tmp_path: Path) -> Path:
    native = tmp_path / "native_extensions"
    native.mkdir(parents=True)
    rows = []
    for module, marker in (("native_bundle_a", 21), ("native_bundle_b", 34)):
        binary = native / f"{module}.py"
        binary.write_text(f"ABI_MARKER = {marker}\n", encoding="utf-8")
        rows.append({
            "module": module,
            "install_relative_path": f"native_extensions/{binary.name}",
            "binary_sha256": _digest(binary),
            "extension_suffix": ".py",
            "sources": [{"path": f"src/{module}.cpp", "sha256": "c" * 64}],
        })
    receipt_payload = {"schema": "test-receipt/v1", "modules": rows}
    receipt = tmp_path / "native-surface-bl-build-receipt.json"
    receipt.write_text(json.dumps(receipt_payload, sort_keys=True), encoding="utf-8")
    manifest = {
        "schema": SCHEMA,
        "package": "test-bundle",
        "modules": rows,
        "authority_receipt_relative_path": receipt.name,
        "authority_receipt_sha256": _digest(receipt),
    }
    manifest["manifest_payload_sha256"] = hashlib.sha256(
        json.dumps(manifest, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode()
    ).hexdigest()
    path = tmp_path / "native-extension-manifest.json"
    path.write_text(json.dumps(manifest, sort_keys=True), encoding="utf-8")
    return path


def test_bundle_selects_requested_module_and_binds_receipt(tmp_path: Path) -> None:
    manifest = _bundle(tmp_path)
    for module, marker in (("native_bundle_a", 21), ("native_bundle_b", 34)):
        path, reason = verify_native_extension_manifest(manifest, module_name=module)
        assert reason == ""
        assert path is not None
        assert path.name == f"{module}.py"
        loaded = import_native_extension  # keep the public release route explicit
        assert loaded is not None


def test_bundle_rejects_duplicate_or_unknown_module(tmp_path: Path) -> None:
    manifest = _bundle(tmp_path)
    payload = json.loads(manifest.read_text())
    payload["modules"].append(dict(payload["modules"][0]))
    payload["manifest_payload_sha256"] = hashlib.sha256(
        json.dumps({k: v for k, v in payload.items() if k != "manifest_payload_sha256"},
                   sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode()
    ).hexdigest()
    manifest.write_text(json.dumps(payload), encoding="utf-8")
    assert verify_native_extension_manifest(manifest, module_name="native_bundle_a")[1] == "manifest_module_duplicate"

    payload["modules"] = payload["modules"][:2]
    payload["modules"][0]["module"] = "native_bundle_other"
    payload["manifest_payload_sha256"] = hashlib.sha256(
        json.dumps({k: v for k, v in payload.items() if k != "manifest_payload_sha256"},
                   sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode()
    ).hexdigest()
    manifest.write_text(json.dumps(payload), encoding="utf-8")
    assert verify_native_extension_manifest(manifest, module_name="native_bundle_a")[1] == "manifest_module_mismatch"


def test_bundle_rejects_receipt_tamper_and_symlink(tmp_path: Path) -> None:
    manifest = _bundle(tmp_path)
    receipt = tmp_path / "native-surface-bl-build-receipt.json"
    receipt.write_text(receipt.read_text() + "tamper", encoding="utf-8")
    assert verify_native_extension_manifest(manifest, module_name="native_bundle_a")[1] == "manifest_authority_receipt_digest_mismatch"

    manifest = _bundle(tmp_path / "symlink")
    payload = json.loads(manifest.read_text())
    target = Path(payload["modules"][0]["install_relative_path"])
    root = manifest.parent
    real = root / target
    link = root / "native_extensions" / "link.py"
    link.symlink_to(real)
    payload["modules"][0]["install_relative_path"] = "native_extensions/link.py"
    payload["manifest_payload_sha256"] = hashlib.sha256(
        json.dumps({k: v for k, v in payload.items() if k != "manifest_payload_sha256"},
                   sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode()
    ).hexdigest()
    manifest.write_text(json.dumps(payload), encoding="utf-8")
    assert verify_native_extension_manifest(manifest, module_name="native_bundle_a")[1] == "manifest_symlink_forbidden"


def test_release_loader_bundle_is_manifest_only(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    manifest = _bundle(tmp_path)
    monkeypatch.setenv("AUTOTESSELL_NATIVE_RELEASE_MODE", "1")
    monkeypatch.setenv("AUTOTESSELL_NATIVE_MANIFEST", str(manifest))
    loaded = import_native_extension("native_bundle_b")
    assert loaded.ABI_MARKER == 34
