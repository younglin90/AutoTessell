"""Release mode uses only a verified manifest."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from core.utils.native_extensions import import_native_extension
from core.utils.native_extension_manifest import SCHEMA


def _manifest(root: Path) -> Path:
    binary = root / "native_extensions" / "fixture.py"
    binary.parent.mkdir(parents=True)
    binary.write_text("ABI_MARKER = 11\n", encoding="utf-8")
    payload = {
        "schema": SCHEMA,
        "module": "native_release_fixture",
        "python_soabi": "source",
        "extension_suffix": ".py",
        "install_relative_path": "native_extensions/fixture.py",
        "binary_sha256": hashlib.sha256(binary.read_bytes()).hexdigest(),
        "sources": [],
        "source_identity": "test",
        "build": {"cxx_standard": 23},
        "authority_receipt_sha256": "b" * 64,
    }
    payload["manifest_payload_sha256"] = hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode()
    ).hexdigest()
    path = root / "native-extension-manifest.json"
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


def test_release_loader_uses_manifest_candidate(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    manifest = _manifest(tmp_path)
    monkeypatch.setenv("AUTOTESSELL_NATIVE_RELEASE_MODE", "1")
    monkeypatch.setenv("AUTOTESSELL_NATIVE_MANIFEST", str(manifest))
    loaded = import_native_extension("native_release_fixture")
    assert loaded.ABI_MARKER == 11


def test_release_loader_fails_closed_without_manifest(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AUTOTESSELL_NATIVE_RELEASE_MODE", "1")
    monkeypatch.delenv("AUTOTESSELL_NATIVE_MANIFEST", raising=False)
    with pytest.raises(ImportError, match="manifest_not_configured"):
        import_native_extension("native_release_fixture_missing")
