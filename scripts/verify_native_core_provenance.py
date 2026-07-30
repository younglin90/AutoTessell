#!/usr/bin/env python3
"""Fail-closed provenance boundary check for tracked native binding files.

The final non-empty stdout line is the numeric count of unrecorded or invalid
binding records.  Diagnostic messages go to stderr so this command can serve as
an autoresearch metric without hiding malformed manifest state.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path
from typing import Any


_REQUIRED_FIELDS = {
    "path": str,
    "module": str,
    "classification": str,
    "implementation_provenance": str,
    "algorithm_source": str,
    "direct_dependencies": list,
    "license_status": str,
    "mit_core_eligible": bool,
    "tests": list,
}
_CLASSIFICATIONS = {"native_core", "excluded_adapter"}
_NONPERMISSIVE_MARKERS = ("gpl", "agpl", "mpl-", "license review required")


def discover_bindings(repo: Path) -> set[str]:
    completed = subprocess.run(
        ["git", "-C", str(repo), "ls-files", "auto_tessell_core/*_bind.cpp"],
        check=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    if completed.returncode != 0:
        raise RuntimeError(completed.stderr.strip() or "git ls-files failed")
    return {line.strip() for line in completed.stdout.splitlines() if line.strip()}


def load_manifest(path: Path) -> dict[str, Any]:
    loaded = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(loaded, dict) or loaded.get("schema_version") != 1:
        raise ValueError("manifest must be an object with schema_version=1")
    if not isinstance(loaded.get("bindings"), list):
        raise ValueError("manifest bindings must be a list")
    return loaded


def validate(manifest: dict[str, Any], discovered: set[str]) -> list[str]:
    errors: list[str] = []
    records = manifest["bindings"]
    paths: list[str] = []
    for index, record in enumerate(records):
        prefix = f"bindings[{index}]"
        if not isinstance(record, dict):
            errors.append(f"{prefix}: record must be an object")
            continue
        for field, expected_type in _REQUIRED_FIELDS.items():
            value = record.get(field)
            if not isinstance(value, expected_type) or (
                expected_type is str and not value.strip()
            ):
                errors.append(f"{prefix}: invalid {field}")
        if not isinstance(record.get("path"), str):
            continue
        path = record["path"]
        paths.append(path)
        classification = record.get("classification")
        eligible = record.get("mit_core_eligible")
        license_status = str(record.get("license_status", "")).lower()
        if classification not in _CLASSIFICATIONS:
            errors.append(f"{path}: unknown classification {classification!r}")
        if classification == "excluded_adapter" and eligible is not False:
            errors.append(f"{path}: excluded adapter must not be MIT-core eligible")
        if eligible is True and any(marker in license_status for marker in _NONPERMISSIVE_MARKERS):
            errors.append(f"{path}: nonpermissive or unresolved license cannot be MIT-core eligible")
        for list_field in ("direct_dependencies", "tests"):
            value = record.get(list_field)
            if not isinstance(value, list) or not value or not all(
                isinstance(item, str) and item.strip() for item in value
            ):
                errors.append(f"{path}: {list_field} must be a nonempty string list")

    path_set = set(paths)
    duplicates = {path for path in path_set if paths.count(path) > 1}
    for path in sorted(duplicates):
        errors.append(f"{path}: duplicate manifest record")
    for path in sorted(discovered - path_set):
        errors.append(f"{path}: missing manifest record")
    for path in sorted(path_set - discovered):
        errors.append(f"{path}: manifest record does not map to tracked binding")
    return errors


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", type=Path, default=Path.cwd())
    parser.add_argument("--manifest", type=Path)
    args = parser.parse_args()
    repo = args.repo.resolve()
    manifest_path = args.manifest or repo / "docs/licensing/native-core-provenance-manifest.json"
    try:
        errors = validate(load_manifest(manifest_path), discover_bindings(repo))
    except (OSError, ValueError, RuntimeError, json.JSONDecodeError) as error:
        print(f"provenance verifier error: {error}", file=sys.stderr)
        print(1)
        return 1
    for error in errors:
        print(f"provenance verifier error: {error}", file=sys.stderr)
    print(len(errors))
    return 0 if not errors else 1


if __name__ == "__main__":
    raise SystemExit(main())
