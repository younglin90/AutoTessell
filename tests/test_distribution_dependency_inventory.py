from __future__ import annotations

import json
from pathlib import Path

from scripts.verify_distribution_dependency_inventory import load_manifest, validate


_ROOT = Path(__file__).resolve().parents[1]
_MANIFEST = _ROOT / "docs/licensing/distribution-dependency-inventory.json"


def test_manifest_covers_exact_declared_direct_dependencies() -> None:
    assert validate(load_manifest(_MANIFEST), _ROOT) == []


def test_missing_python_dependency_is_reported() -> None:
    manifest = load_manifest(_MANIFEST)
    manifest["profiles"][0]["dependencies"] = manifest["profiles"][0]["dependencies"][1:]
    errors = validate(manifest, _ROOT)
    assert "pypi:click: missing manifest record" in errors


def test_guessed_spdx_assertion_is_rejected() -> None:
    manifest = load_manifest(_MANIFEST)
    manifest["profiles"][0]["dependencies"][0]["license_assertion"]["spdx_expression"] = "MIT"
    errors = validate(manifest, _ROOT)
    assert "pypi:click: SPDX assertion requires a separate resolution card" in errors


def test_missing_local_evidence_is_reported() -> None:
    manifest = load_manifest(_MANIFEST)
    manifest["profiles"][1]["dependencies"][4]["license_assertion"]["local_evidence"] = [
        "third_party/fTetWild/MISSING-LICENSE"
    ]
    errors = validate(manifest, _ROOT)
    assert "source:fTetWild: local evidence missing: third_party/fTetWild/MISSING-LICENSE" in errors


def test_external_cmake_source_cannot_cross_native_core_boundary() -> None:
    manifest = load_manifest(_MANIFEST)
    manifest["profiles"][1]["dependencies"][2]["core_boundary"] = "not_core_implementation"
    errors = validate(manifest, _ROOT)
    assert "source:cinolib: external source must be excluded from native core" in errors


def test_cmake_declaration_location_is_checked() -> None:
    manifest = load_manifest(_MANIFEST)
    manifest["profiles"][1]["dependencies"][0]["declared_at"] = "auto_tessell_core/CMakeLists.txt:1"
    errors = validate(manifest, _ROOT)
    assert "cmake:pybind11: declaration location does not match CMake" in errors


def test_manifest_is_plain_json() -> None:
    assert json.loads(_MANIFEST.read_text(encoding="utf-8"))["schema_version"] == 1
