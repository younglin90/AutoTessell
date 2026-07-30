#!/usr/bin/env python3
"""Fail-closed check for declared distribution dependency inventory.

This checker inventories only direct declarations in repository metadata.  It
does not resolve packages, fetch metadata, or infer licenses from package names.
The final non-empty stdout line is the numeric count of coverage or evidence
errors so the command can serve as a stable release-gate metric.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import tomllib
from pathlib import Path
from typing import Any


_REQUIRED_RECORD_FIELDS = {
    "id": str,
    "kind": str,
    "declared_at": str,
    "distribution_condition": str,
    "license_assertion": dict,
    "core_boundary": str,
}
_PROFILE_IDS = {"python-wheel-core", "cmake-native-direct"}
_PYTHON_DECLARED_AT = "pyproject.toml:[project].dependencies"
_UNRESOLVED_STATUSES = {
    "UNVERIFIED_NO_LOCAL_ARTIFACT",
    "LOCAL_EVIDENCE_RECORDED_NOT_RESOLVED",
}
_EXTERNAL_BOUNDARY = "external_adapter_excluded"
_CMAKE_DECLARATIONS = {
    "cmake:pybind11": "find_package(pybind11 CONFIG REQUIRED)",
    "cmake:Eigen3": "find_package(Eigen3 3.3 REQUIRED NO_MODULE)",
    "source:cinolib": "target_include_directories(cinolib_hex PRIVATE \"${CINOLIB_DIR}/include\")",
    "source:robusthex": "if(BUILD_ROBUSTHEX AND EXISTS \"${ROBUSTHEX_DIR}/src/meshio.cpp\")",
    "source:fTetWild": "if(BUILD_FTETWILD AND EXISTS \"${FTETWILD_SRC_DIR}/CMakeLists.txt\")",
    "source:cfMesh": "if(BUILD_CFMESH AND EXISTS \"${CFMESH_SRC_DIR}/CMakeLists.txt\")",
}
_CMAKE_EXTERNAL_IDS = {
    "source:cinolib",
    "source:robusthex",
    "source:fTetWild",
    "source:cfMesh",
}


def load_manifest(path: Path) -> dict[str, Any]:
    loaded = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(loaded, dict) or loaded.get("schema_version") != 1:
        raise ValueError("manifest must be an object with schema_version=1")
    if not isinstance(loaded.get("profiles"), list):
        raise ValueError("manifest profiles must be a list")
    return loaded


def _python_direct_dependencies(repo: Path) -> dict[str, str]:
    with (repo / "pyproject.toml").open("rb") as file:
        project = tomllib.load(file).get("project", {})
    requirements = project.get("dependencies")
    if not isinstance(requirements, list) or not all(isinstance(item, str) for item in requirements):
        raise ValueError("pyproject [project].dependencies must be a string list")
    declared: dict[str, str] = {}
    for requirement in requirements:
        match = re.match(r"^([A-Za-z0-9_.-]+)", requirement)
        if match is None:
            raise ValueError(f"unparseable direct requirement {requirement!r}")
        dependency_id = f"pypi:{match.group(1).lower()}"
        if dependency_id in declared:
            raise ValueError(f"duplicate direct requirement {dependency_id}")
        declared[dependency_id] = requirement
    return declared


def _cmake_direct_dependencies(repo: Path) -> dict[str, tuple[str, str]]:
    cmake = (repo / "auto_tessell_core/CMakeLists.txt").read_text(encoding="utf-8")
    locations: dict[str, tuple[str, str]] = {}
    missing: dict[str, str] = {}
    for dependency_id, declaration in _CMAKE_DECLARATIONS.items():
        matches = [
            line_number
            for line_number, line in enumerate(cmake.splitlines(), start=1)
            if line.strip() == declaration
        ]
        if len(matches) != 1:
            missing[dependency_id] = declaration
            continue
        locations[dependency_id] = (
            declaration,
            f"auto_tessell_core/CMakeLists.txt:{matches[0]}",
        )
    if missing:
        descriptions = ", ".join(sorted(missing))
        raise ValueError(f"CMake direct dependency declaration changed or missing: {descriptions}")
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


def validate(manifest: dict[str, Any], repo: Path) -> list[str]:
    errors: list[str] = []
    try:
        profiles = _profile_by_id(manifest)
        expected_profiles = _PROFILE_IDS
        extra_profiles = set(profiles) - expected_profiles
        missing_profiles = expected_profiles - set(profiles)
        for profile_id in sorted(extra_profiles):
            errors.append(f"profile {profile_id}: unexpected")
        for profile_id in sorted(missing_profiles):
            errors.append(f"profile {profile_id}: missing")
        if missing_profiles:
            return errors
        python_expected = _python_direct_dependencies(repo)
        cmake_expected = _cmake_direct_dependencies(repo)
    except (OSError, ValueError, tomllib.TOMLDecodeError) as error:
        return [str(error)]

    expected_by_profile = {
        "python-wheel-core": python_expected,
        "cmake-native-direct": cmake_expected,
    }
    for profile_id, expected in expected_by_profile.items():
        profile = profiles[profile_id]
        records = profile.get("dependencies")
        if not isinstance(records, list):
            errors.append(f"profile {profile_id}: dependencies must be a list")
            continue
        seen: set[str] = set()
        for index, record in enumerate(records):
            prefix = f"profile {profile_id} dependencies[{index}]"
            if not isinstance(record, dict):
                errors.append(f"{prefix}: record must be an object")
                continue
            for field, expected_type in _REQUIRED_RECORD_FIELDS.items():
                value = record.get(field)
                if not isinstance(value, expected_type) or (
                    expected_type is str and not value.strip()
                ):
                    errors.append(f"{prefix}: invalid {field}")
            dependency_id = record.get("id")
            if not isinstance(dependency_id, str):
                continue
            if dependency_id in seen:
                errors.append(f"{dependency_id}: duplicate manifest record")
            seen.add(dependency_id)
            if dependency_id not in expected:
                errors.append(f"{dependency_id}: not a declared direct dependency")
                continue
            if record.get("kind") != ("python_direct" if profile_id == "python-wheel-core" else "cmake_direct"):
                errors.append(f"{dependency_id}: wrong dependency kind")
            if profile_id == "python-wheel-core":
                if record.get("requirement") != expected[dependency_id]:
                    errors.append(f"{dependency_id}: requirement does not match pyproject")
                if record.get("declared_at") != _PYTHON_DECLARED_AT:
                    errors.append(f"{dependency_id}: wrong Python declaration source")
                if record.get("distribution_condition") != "always":
                    errors.append(f"{dependency_id}: Python base dependency must be always included")
            else:
                declaration, declared_at = expected[dependency_id]
                if record.get("declaration") != declaration:
                    errors.append(f"{dependency_id}: declaration does not match CMake")
                if record.get("declared_at") != declared_at:
                    errors.append(f"{dependency_id}: declaration location does not match CMake")
                if dependency_id in _CMAKE_EXTERNAL_IDS and record.get("core_boundary") != _EXTERNAL_BOUNDARY:
                    errors.append(f"{dependency_id}: external source must be excluded from native core")
            assertion = record.get("license_assertion")
            if not isinstance(assertion, dict):
                continue
            status = assertion.get("status")
            spdx_expression = assertion.get("spdx_expression")
            evidence = assertion.get("local_evidence")
            if status not in _UNRESOLVED_STATUSES:
                errors.append(f"{dependency_id}: license status must remain unresolved")
            if spdx_expression is not None:
                errors.append(f"{dependency_id}: SPDX assertion requires a separate resolution card")
            if not isinstance(evidence, list) or not all(isinstance(item, str) and item for item in evidence):
                errors.append(f"{dependency_id}: local_evidence must be a string list")
                continue
            if status == "UNVERIFIED_NO_LOCAL_ARTIFACT" and evidence:
                errors.append(f"{dependency_id}: unverified record must not claim local evidence")
            if status == "LOCAL_EVIDENCE_RECORDED_NOT_RESOLVED" and not evidence:
                errors.append(f"{dependency_id}: local evidence status requires evidence path")
            for evidence_path in evidence:
                candidate = repo / evidence_path
                if not candidate.is_file():
                    errors.append(f"{dependency_id}: local evidence missing: {evidence_path}")
        for dependency_id in sorted(set(expected) - seen):
            errors.append(f"{dependency_id}: missing manifest record")
    return errors


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", type=Path, default=Path.cwd())
    parser.add_argument("--manifest", type=Path)
    args = parser.parse_args()
    repo = args.repo.resolve()
    manifest_path = args.manifest or repo / "docs/licensing/distribution-dependency-inventory.json"
    try:
        errors = validate(load_manifest(manifest_path), repo)
    except (OSError, ValueError, json.JSONDecodeError) as error:
        errors = [f"inventory verifier error: {error}"]
    for error in errors:
        print(f"inventory verifier error: {error}", file=sys.stderr)
    print(len(errors))
    return 0 if not errors else 1


if __name__ == "__main__":
    raise SystemExit(main())
