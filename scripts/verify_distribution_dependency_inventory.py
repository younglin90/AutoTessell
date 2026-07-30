#!/usr/bin/env python3
"""Fail-closed verification for release dependency evidence and boundaries."""

from __future__ import annotations

import argparse
import json
import re
import sys
import tomllib
from pathlib import Path
from typing import Any

_PROFILE_IDS = {
    "python-wheel-core",
    "cmake-native-direct",
    "first-party-native-wheel",
}
_EVIDENCE_PATH = Path("docs/licensing/evidence/python-wheel-core-cp312-manylinux-x86_64.json")
_RESOLVED_STATUSES = {
    "VERIFIED_PEP639_ARTIFACT",
    "VERIFIED_LEGACY_ARTIFACT_METADATA",
    "LOCAL_PROVENANCE_RECORDED",
}
_UNRESOLVED_STATUSES = {
    "UNVERIFIED_NO_LOCAL_ARTIFACT",
    "LOCAL_EVIDENCE_RECORDED_NOT_RESOLVED",
    "UPSTREAM_LICENSE_DECLARED_NOT_YET_RELEASE_AUDITED",
}
_EXTERNAL_BOUNDARY = "external_adapter_excluded"
_CMAKE_DECLARATIONS = {
    "cmake:pybind11": "find_package(pybind11 3.0 CONFIG REQUIRED)",
    "cmake:Eigen3": "find_package(Eigen3 3.3 REQUIRED NO_MODULE)",
    "cmake:Boost.headers": "find_package(Boost REQUIRED)",
    "source:cinolib": 'target_include_directories(cinolib_hex PRIVATE "${CINOLIB_DIR}/include")',
    "source:robusthex": 'if(BUILD_ROBUSTHEX AND EXISTS "${ROBUSTHEX_DIR}/src/meshio.cpp")',
    "source:fTetWild": 'if(BUILD_FTETWILD AND EXISTS "${FTETWILD_SRC_DIR}/CMakeLists.txt")',
    "source:cfMesh": 'if(BUILD_CFMESH AND EXISTS "${CFMESH_SRC_DIR}/CMakeLists.txt")',
}
_CMAKE_EXTERNAL_IDS = {
    "source:cinolib",
    "source:robusthex",
    "source:fTetWild",
    "source:cfMesh",
}
_FIRST_PARTY_MODULES = {
    "native_metrics",
    "native_bl",
    "native_polymesh",
    "native_snap",
    "native_surface_padding",
    "native_hex_quality",
    "native_tet_predicates",
    "native_tet_qopt",
}
_FORBIDDEN_MODULES = {"cinolib_hex", "robusthex", "ftetwild", "cfmesh_native"}


def load_manifest(path: Path) -> dict[str, Any]:
    loaded = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(loaded, dict) or loaded.get("schema_version") != 1:
        raise ValueError("manifest must be an object with schema_version=1")
    if not isinstance(loaded.get("profiles"), list):
        raise ValueError("manifest profiles must be a list")
    return loaded


def _dependency_id(requirement: str) -> str:
    match = re.match(r"^([A-Za-z0-9_.-]+)", requirement)
    if match is None:
        raise ValueError(f"unparseable direct requirement {requirement!r}")
    return f"pypi:{match.group(1).lower()}"


def _python_direct_dependencies(repo: Path) -> dict[str, dict[str, str]]:
    with (repo / "pyproject.toml").open("rb") as file:
        config = tomllib.load(file)
    groups = (
        (
            config["build-system"]["requires"],
            "python_build_direct",
            "pyproject.toml:[build-system].requires",
            "isolated PEP 517 build",
        ),
        (
            config["project"]["dependencies"],
            "python_direct",
            "pyproject.toml:[project].dependencies",
            "always",
        ),
    )
    declared: dict[str, dict[str, str]] = {}
    for requirements, kind, declared_at, condition in groups:
        if not isinstance(requirements, list) or not all(
            isinstance(item, str) for item in requirements
        ):
            raise ValueError(f"{declared_at} must be a string list")
        for requirement in requirements:
            dependency_id = _dependency_id(requirement)
            if dependency_id in declared:
                raise ValueError(f"duplicate direct requirement {dependency_id}")
            declared[dependency_id] = {
                "requirement": requirement,
                "kind": kind,
                "declared_at": declared_at,
                "distribution_condition": condition,
            }
    return declared


def _cmake_direct_dependencies(repo: Path) -> dict[str, dict[str, str]]:
    cmake = (repo / "auto_tessell_core/CMakeLists.txt").read_text(encoding="utf-8")
    locations: dict[str, dict[str, str]] = {}
    missing: list[str] = []
    for dependency_id, declaration in _CMAKE_DECLARATIONS.items():
        matches = [
            line_number
            for line_number, line in enumerate(cmake.splitlines(), start=1)
            if line.strip() == declaration
        ]
        if len(matches) != 1:
            missing.append(dependency_id)
            continue
        locations[dependency_id] = {
            "declaration": declaration,
            "declared_at": f"auto_tessell_core/CMakeLists.txt:{matches[0]}",
        }
    if missing:
        raise ValueError(
            "CMake direct dependency declaration changed or missing: " + ", ".join(sorted(missing))
        )
    return locations


def _profile_by_id(manifest: dict[str, Any]) -> dict[str, dict[str, Any]]:
    profiles: dict[str, dict[str, Any]] = {}
    for index, profile in enumerate(manifest["profiles"]):
        if not isinstance(profile, dict) or not isinstance(profile.get("id"), str):
            raise ValueError(f"profiles[{index}] must be an object with id")
        profile_id = profile["id"]
        if profile_id in profiles:
            raise ValueError(f"duplicate profile {profile_id}")
        profiles[profile_id] = profile
    return profiles


def _evidence_by_id(repo: Path) -> tuple[dict[str, dict[str, Any]], list[str]]:
    errors: list[str] = []
    path = repo / _EVIDENCE_PATH
    try:
        evidence = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        return {}, [f"python wheel evidence unreadable: {exc}"]
    if evidence.get("schema_version") != 1 or evidence.get("profile") != "python-wheel-core":
        errors.append("python wheel evidence has invalid schema/profile")
    packages = evidence.get("packages")
    if not isinstance(packages, list):
        return {}, errors + ["python wheel evidence packages must be a list"]
    by_id: dict[str, dict[str, Any]] = {}
    for index, package in enumerate(packages):
        if not isinstance(package, dict) or not isinstance(package.get("id"), str):
            errors.append(f"python wheel evidence packages[{index}] has invalid id")
            continue
        dependency_id = package["id"]
        if dependency_id in by_id:
            errors.append(f"python wheel evidence duplicate {dependency_id}")
        by_id[dependency_id] = package
        artifact = package.get("artifact", {})
        metadata = package.get("metadata", {})
        sha256 = artifact.get("sha256")
        if not isinstance(sha256, str) or re.fullmatch(r"[0-9a-f]{64}", sha256) is None:
            errors.append(f"{dependency_id}: invalid artifact SHA-256")
        if metadata.get("version") != package.get("version"):
            errors.append(f"{dependency_id}: evidence METADATA version mismatch")
        metadata_sha = metadata.get("sha256")
        if not isinstance(metadata_sha, str) or re.fullmatch(r"[0-9a-f]{64}", metadata_sha) is None:
            errors.append(f"{dependency_id}: invalid METADATA SHA-256")
        for license_file in metadata.get("license_files", []):
            license_sha = license_file.get("sha256")
            if (
                not isinstance(license_sha, str)
                or re.fullmatch(r"[0-9a-f]{64}", license_sha) is None
            ):
                errors.append(f"{dependency_id}: invalid license-file SHA-256")
    return by_id, errors


def _validate_assertion(
    record: dict[str, Any],
    repo: Path,
    evidence: dict[str, dict[str, Any]],
) -> list[str]:
    dependency_id = record.get("id", "<missing-id>")
    assertion = record.get("license_assertion")
    if not isinstance(assertion, dict):
        return [f"{dependency_id}: invalid license_assertion"]
    status = assertion.get("status")
    if status not in _RESOLVED_STATUSES | _UNRESOLVED_STATUSES:
        return [f"{dependency_id}: unknown license status {status!r}"]
    errors: list[str] = []
    paths = assertion.get("local_evidence")
    if not isinstance(paths, list) or not all(isinstance(item, str) and item for item in paths):
        return [f"{dependency_id}: local_evidence must be a string list"]
    for evidence_path in paths:
        if not (repo / evidence_path).is_file():
            errors.append(f"{dependency_id}: local evidence missing: {evidence_path}")
    if status == "UNVERIFIED_NO_LOCAL_ARTIFACT" and paths:
        errors.append(f"{dependency_id}: unverified record must not claim local evidence")
    if status in _RESOLVED_STATUSES and not paths:
        errors.append(f"{dependency_id}: resolved status requires local evidence")

    if status in {"VERIFIED_PEP639_ARTIFACT", "VERIFIED_LEGACY_ARTIFACT_METADATA"}:
        evidence_id = assertion.get("artifact_evidence_id", dependency_id)
        package = evidence.get(evidence_id)
        if package is None:
            errors.append(f"{dependency_id}: exact artifact evidence missing")
            return errors
        metadata = package["metadata"]
        expression = assertion.get("spdx_expression")
        if status == "VERIFIED_PEP639_ARTIFACT":
            if not expression or expression != metadata.get("license_expression"):
                errors.append(f"{dependency_id}: PEP 639 expression does not match artifact")
        else:
            if expression is not None or metadata.get("license_expression") is not None:
                errors.append(f"{dependency_id}: legacy artifact must not infer SPDX")
            has_legacy_evidence = bool(
                metadata.get("license_field_length")
                or metadata.get("license_classifiers")
                or metadata.get("license_files")
            )
            if not has_legacy_evidence:
                errors.append(f"{dependency_id}: legacy artifact metadata evidence is empty")
    return errors


def _validate_python_profile(
    profile: dict[str, Any], repo: Path, evidence: dict[str, dict[str, Any]]
) -> list[str]:
    errors: list[str] = []
    expected = _python_direct_dependencies(repo)
    records = profile.get("dependencies")
    if not isinstance(records, list):
        return ["profile python-wheel-core: dependencies must be a list"]
    seen: set[str] = set()
    for record in records:
        dependency_id = record.get("id")
        if not isinstance(dependency_id, str):
            errors.append("profile python-wheel-core: dependency has invalid id")
            continue
        if dependency_id in seen:
            errors.append(f"{dependency_id}: duplicate manifest record")
        seen.add(dependency_id)
        declaration = expected.get(dependency_id)
        if declaration is None:
            errors.append(f"{dependency_id}: not a declared Python direct dependency")
            continue
        for field, value in declaration.items():
            if record.get(field) != value:
                errors.append(f"{dependency_id}: {field} does not match pyproject")
        package = evidence.get(dependency_id)
        if package is None:
            errors.append(f"{dependency_id}: exact artifact evidence missing")
        elif package.get("requirement") != declaration["requirement"]:
            errors.append(f"{dependency_id}: evidence requirement does not match pyproject")
        errors.extend(_validate_assertion(record, repo, evidence))
    for dependency_id in sorted(set(expected) - seen):
        errors.append(f"{dependency_id}: missing manifest record")
    for dependency_id in sorted(set(evidence) - set(expected)):
        errors.append(f"{dependency_id}: evidence is not a declared Python direct dependency")
    return errors


def _validate_cmake_profile(
    profile: dict[str, Any], repo: Path, evidence: dict[str, dict[str, Any]]
) -> list[str]:
    errors: list[str] = []
    expected = _cmake_direct_dependencies(repo)
    records = profile.get("dependencies")
    if not isinstance(records, list):
        return ["profile cmake-native-direct: dependencies must be a list"]
    seen: set[str] = set()
    for record in records:
        dependency_id = record.get("id")
        if not isinstance(dependency_id, str):
            errors.append("profile cmake-native-direct: dependency has invalid id")
            continue
        if dependency_id in seen:
            errors.append(f"{dependency_id}: duplicate manifest record")
        seen.add(dependency_id)
        declaration = expected.get(dependency_id)
        if declaration is None:
            errors.append(f"{dependency_id}: not a declared CMake direct dependency")
            continue
        if record.get("kind") != "cmake_direct":
            errors.append(f"{dependency_id}: wrong dependency kind")
        for field, value in declaration.items():
            if record.get(field) != value:
                errors.append(f"{dependency_id}: {field} does not match CMake")
        if (
            dependency_id in _CMAKE_EXTERNAL_IDS
            and record.get("core_boundary") != _EXTERNAL_BOUNDARY
        ):
            errors.append(f"{dependency_id}: external source must be excluded from native core")
        errors.extend(_validate_assertion(record, repo, evidence))
    for dependency_id in sorted(set(expected) - seen):
        errors.append(f"{dependency_id}: missing manifest record")
    return errors


def _validate_first_party_profile(
    profile: dict[str, Any], repo: Path, evidence: dict[str, dict[str, Any]]
) -> list[str]:
    errors: list[str] = []
    if set(profile.get("native_modules", [])) != _FIRST_PARTY_MODULES:
        errors.append("profile first-party-native-wheel: native module set mismatch")
    if set(profile.get("forbidden_native_modules", [])) != _FORBIDDEN_MODULES:
        errors.append("profile first-party-native-wheel: forbidden module set mismatch")
    records = profile.get("dependencies")
    if not isinstance(records, list):
        return errors + ["profile first-party-native-wheel: dependencies must be a list"]
    expected_ids = {"cmake:pybind11", "cmake:Boost.headers", "source:shewchuk-predicates"}
    seen = {record.get("id") for record in records}
    if seen != expected_ids:
        errors.append("profile first-party-native-wheel: dependency set mismatch")
    for record in records:
        errors.extend(_validate_assertion(record, repo, evidence))
    return errors


def _unresolved_errors(profile_id: str, profile: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    for record in profile.get("dependencies", []):
        assertion = record.get("license_assertion", {})
        status = assertion.get("status")
        if status in _UNRESOLVED_STATUSES:
            errors.append(f"unresolved: {profile_id}:{record.get('id')} ({status})")
    return errors


def validate(
    manifest: dict[str, Any],
    repo: Path,
    *,
    profile_id: str | None = None,
    require_resolved: bool = False,
) -> list[str]:
    try:
        profiles = _profile_by_id(manifest)
        extra_profiles = set(profiles) - _PROFILE_IDS
        missing_profiles = _PROFILE_IDS - set(profiles)
        errors = [f"profile {item}: unexpected" for item in sorted(extra_profiles)]
        errors.extend(f"profile {item}: missing" for item in sorted(missing_profiles))
        if profile_id is not None and profile_id not in profiles:
            errors.append(f"profile {profile_id}: missing")
            return errors
        evidence, evidence_errors = _evidence_by_id(repo)
        errors.extend(evidence_errors)
        selected = [profile_id] if profile_id is not None else sorted(_PROFILE_IDS & set(profiles))
        validators = {
            "python-wheel-core": _validate_python_profile,
            "cmake-native-direct": _validate_cmake_profile,
            "first-party-native-wheel": _validate_first_party_profile,
        }
        for selected_id in selected:
            profile = profiles[selected_id]
            errors.extend(validators[selected_id](profile, repo, evidence))
            if require_resolved:
                errors.extend(_unresolved_errors(selected_id, profile))
        return errors
    except (KeyError, OSError, ValueError, TypeError, tomllib.TOMLDecodeError) as exc:
        return [str(exc)]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", type=Path, default=Path.cwd())
    parser.add_argument("--manifest", type=Path)
    parser.add_argument("--profile", choices=sorted(_PROFILE_IDS))
    parser.add_argument("--require-resolved", action="store_true")
    args = parser.parse_args()
    repo = args.repo.resolve()
    manifest_path = args.manifest or repo / "docs/licensing/distribution-dependency-inventory.json"
    try:
        manifest = load_manifest(manifest_path)
        errors = validate(
            manifest,
            repo,
            profile_id=args.profile,
            require_resolved=args.require_resolved,
        )
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        errors = [f"inventory verifier error: {exc}"]
    for error in errors:
        print(f"inventory verifier error: {error}", file=sys.stderr)
    print(len(errors))
    return 0 if not errors else 1


if __name__ == "__main__":
    raise SystemExit(main())
