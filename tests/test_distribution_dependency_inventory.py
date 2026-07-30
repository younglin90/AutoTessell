from __future__ import annotations

import copy
import json
import tomllib
from pathlib import Path

import pytest

from scripts import collect_python_wheel_license_evidence as collector
from scripts import verify_distribution_dependency_inventory as verifier
from scripts.verify_distribution_dependency_inventory import load_manifest, validate
from scripts.verify_native_distribution_artifacts import REQUIRED_SOURCE

_ROOT = Path(__file__).resolve().parents[1]
_MANIFEST = _ROOT / "docs/licensing/distribution-dependency-inventory.json"
_EVIDENCE = _ROOT / "docs/licensing/evidence/python-wheel-core-cp312-manylinux-x86_64.json"


def _dependency(manifest: dict, profile_id: str, dependency_id: str) -> dict:
    profile = next(item for item in manifest["profiles"] if item["id"] == profile_id)
    return next(item for item in profile["dependencies"] if item["id"] == dependency_id)


def test_manifest_covers_exact_declared_direct_dependencies() -> None:
    assert validate(load_manifest(_MANIFEST), _ROOT) == []


def test_python_wheel_profile_is_fully_resolved() -> None:
    assert (
        validate(
            load_manifest(_MANIFEST),
            _ROOT,
            profile_id="python-wheel-core",
            require_resolved=True,
        )
        == []
    )


def test_global_resolution_stays_fail_closed() -> None:
    errors = validate(load_manifest(_MANIFEST), _ROOT, require_resolved=True)
    assert len(errors) == 8
    assert all(error.startswith("unresolved: ") for error in errors)
    assert any("cmake-native-direct:source:cfMesh" in error for error in errors)
    assert any("first-party-native-wheel:cmake:Boost.headers" in error for error in errors)


def test_missing_python_dependency_is_reported() -> None:
    manifest = load_manifest(_MANIFEST)
    profile = next(item for item in manifest["profiles"] if item["id"] == "python-wheel-core")
    profile["dependencies"] = [
        item for item in profile["dependencies"] if item["id"] != "pypi:click"
    ]
    errors = validate(manifest, _ROOT)
    assert "pypi:click: missing manifest record" in errors


def test_pep639_expression_must_match_exact_artifact() -> None:
    manifest = load_manifest(_MANIFEST)
    assertion = _dependency(manifest, "python-wheel-core", "pypi:click")["license_assertion"]
    assertion["spdx_expression"] = "MIT"
    errors = validate(manifest, _ROOT)
    assert "pypi:click: PEP 639 expression does not match artifact" in errors


def test_legacy_metadata_cannot_be_promoted_to_guessed_spdx() -> None:
    manifest = load_manifest(_MANIFEST)
    assertion = _dependency(manifest, "python-wheel-core", "pypi:rich")["license_assertion"]
    assertion["spdx_expression"] = "MIT"
    errors = validate(manifest, _ROOT)
    assert "pypi:rich: legacy artifact must not infer SPDX" in errors


def test_missing_local_evidence_is_reported() -> None:
    manifest = load_manifest(_MANIFEST)
    assertion = _dependency(manifest, "cmake-native-direct", "source:fTetWild")["license_assertion"]
    assertion["local_evidence"] = ["third_party/fTetWild/MISSING-LICENSE"]
    errors = validate(manifest, _ROOT)
    assert "source:fTetWild: local evidence missing: third_party/fTetWild/MISSING-LICENSE" in errors


def test_external_cmake_source_cannot_cross_native_core_boundary() -> None:
    manifest = load_manifest(_MANIFEST)
    record = _dependency(manifest, "cmake-native-direct", "source:cinolib")
    record["core_boundary"] = "not_core_implementation"
    errors = validate(manifest, _ROOT)
    assert "source:cinolib: external source must be excluded from native core" in errors


def test_cmake_declaration_location_is_checked() -> None:
    manifest = load_manifest(_MANIFEST)
    record = _dependency(manifest, "cmake-native-direct", "cmake:pybind11")
    record["declared_at"] = "auto_tessell_core/CMakeLists.txt:1"
    errors = validate(manifest, _ROOT)
    assert "cmake:pybind11: declared_at does not match CMake" in errors


def test_evidence_license_metadata_mutation_is_rejected(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    evidence = json.loads(_EVIDENCE.read_text(encoding="utf-8"))
    click = next(item for item in evidence["packages"] if item["id"] == "pypi:click")
    click["metadata"]["license_expression"] = "MIT"
    evidence_path = tmp_path / "evidence.json"
    evidence_path.write_text(json.dumps(evidence), encoding="utf-8")
    monkeypatch.setattr(verifier, "_EVIDENCE_PATH", evidence_path)

    manifest = load_manifest(_MANIFEST)
    errors = validate(manifest, _ROOT, profile_id="python-wheel-core")

    assert "pypi:click: PEP 639 expression does not match artifact" in errors


def test_official_artifact_hash_mutation_is_rejected(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    evidence = json.loads(_EVIDENCE.read_text(encoding="utf-8"))
    click = next(item for item in evidence["packages"] if item["id"] == "pypi:click")
    seed = {
        "target": evidence["target"],
        "packages": [copy.deepcopy(click)],
    }
    original_sha = click["artifact"]["sha256"]
    seed["packages"][0]["artifact"]["sha256"] = "0" * 64
    release_json = json.dumps(
        {
            "info": {"version": click["version"]},
            "urls": [
                {
                    "filename": click["artifact"]["filename"],
                    "url": click["artifact"]["url"],
                    "digests": {"sha256": original_sha},
                }
            ],
        }
    ).encode()
    monkeypatch.setattr(
        collector,
        "_download",
        lambda url: release_json if url == click["pypi_json_url"] else b"",
    )

    with pytest.raises(ValueError, match="artifact is not uniquely declared"):
        collector.collect_document(seed)


def test_manifest_and_evidence_are_plain_json() -> None:
    assert json.loads(_MANIFEST.read_text(encoding="utf-8"))["schema_version"] == 1
    assert json.loads(_EVIDENCE.read_text(encoding="utf-8"))["schema_version"] == 1


def test_sdist_contract_carries_reproducible_license_evidence() -> None:
    required = {
        "docs/licensing/evidence/python-wheel-core-cp312-manylinux-x86_64.json",
        "scripts/collect_python_wheel_license_evidence.py",
        "scripts/verify_distribution_dependency_inventory.py",
    }
    assert required.issubset(REQUIRED_SOURCE)
    with (_ROOT / "pyproject.toml").open("rb") as stream:
        config = tomllib.load(stream)
    assert required.issubset(config["tool"]["scikit-build"]["sdist"]["include"])
