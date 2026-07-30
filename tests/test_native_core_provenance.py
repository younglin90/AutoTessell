from __future__ import annotations

import json
from pathlib import Path

from scripts.verify_native_core_provenance import discover_bindings, load_manifest, validate


_ROOT = Path(__file__).resolve().parents[1]
_MANIFEST = _ROOT / "docs/licensing/native-core-provenance-manifest.json"


def test_manifest_covers_exact_tracked_binding_set() -> None:
    manifest = load_manifest(_MANIFEST)
    assert validate(manifest, discover_bindings(_ROOT)) == []


def test_missing_binding_is_reported() -> None:
    manifest = load_manifest(_MANIFEST)
    manifest["bindings"] = manifest["bindings"][1:]
    errors = validate(manifest, discover_bindings(_ROOT))
    assert any("cfmesh_bind.cpp: missing manifest record" in error for error in errors)


def test_extra_binding_is_reported() -> None:
    manifest = load_manifest(_MANIFEST)
    manifest["bindings"].append({**manifest["bindings"][0], "path": "auto_tessell_core/missing_bind.cpp"})
    errors = validate(manifest, discover_bindings(_ROOT))
    assert any("missing_bind.cpp: manifest record does not map" in error for error in errors)


def test_excluded_or_nonpermissive_binding_cannot_be_eligible() -> None:
    manifest = load_manifest(_MANIFEST)
    manifest["bindings"][0]["mit_core_eligible"] = True
    manifest["bindings"][3]["license_status"] = "MPL-2.0 dependency"
    errors = validate(manifest, discover_bindings(_ROOT))
    assert any("excluded adapter must not" in error for error in errors)
    assert any("nonpermissive or unresolved license" in error for error in errors)


def test_manifest_is_plain_json() -> None:
    assert json.loads(_MANIFEST.read_text(encoding="utf-8"))["schema_version"] == 1
