"""Validate app-version consistency across key project files."""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

import tomllib


def _extract(pattern: str, text: str, label: str) -> str:
    match = re.search(pattern, text)
    if not match:
        raise ValueError(f"Could not parse version from {label}")
    return match.group(1)


def main() -> int:
    root = Path(__file__).resolve().parents[1]

    project_version = tomllib.loads((root / "pyproject.toml").read_text())["project"]["version"]
    versions = {
        "pyproject.toml": project_version,
        "core/version.py": _extract(
            r'APP_VERSION\s*=\s*"([^"]+)"',
            (root / "core/version.py").read_text(),
            "core/version.py",
        ),
        "backend/version.py": _extract(
            r'APP_VERSION\s*=\s*"([^"]+)"',
            (root / "backend/version.py").read_text(),
            "backend/version.py",
        ),
        "godot/project.godot": _extract(
            r'config/version="([^"]+)"',
            (root / "godot/project.godot").read_text(),
            "godot/project.godot",
        ),
        "scripts/installer.iss": _extract(
            r'#define MyAppVersion "([^"]+)"',
            (root / "scripts/installer.iss").read_text(),
            "scripts/installer.iss",
        ),
        "frontend/package.json": json.loads((root / "frontend/package.json").read_text())["version"],
    }

    print(f"app_version = {project_version}")
    for path, value in versions.items():
        print(f"{path}: {value}")

    mismatches = {path: value for path, value in versions.items() if value != project_version}
    if mismatches:
        for path, value in mismatches.items():
            print(f"mismatch: {path} = {value} (expected {project_version})")
        return 1

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
