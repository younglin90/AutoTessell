#!/usr/bin/env python3
"""Validate every release identity against ``core/version.py``."""

from __future__ import annotations

import argparse
import ast
import json
import os
import re
import sys
import tomllib
from pathlib import Path

_CANONICAL_PATTERN = r'^APP_VERSION\s*=\s*["\']([^"\']+)["\']\s*$'
_PYTHON_CONSUMERS = (
    "products/web/api/version.py",
    "desktop/qt_main.py",
    "desktop/qt_app/main_window.py",
)


def _extract(pattern: str, text: str, label: str) -> str:
    match = re.search(pattern, text, flags=re.MULTILINE)
    if not match:
        raise ValueError(f"Could not parse version from {label}")
    return match.group(1)


def canonical_version(root: Path) -> str:
    """Return the sole authored application version."""
    return _extract(
        _CANONICAL_PATTERN,
        (root / "core/version.py").read_text(encoding="utf-8"),
        "core/version.py",
    )


def _static_versions(root: Path) -> dict[str, str]:
    frontend = json.loads((root / "products/web/app/package.json").read_text(encoding="utf-8"))
    frontend_lock = json.loads((root / "products/web/app/package-lock.json").read_text(encoding="utf-8"))
    electron = json.loads((root / "desktop/electron/package.json").read_text(encoding="utf-8"))
    return {
        "scripts/installer.iss": _extract(
            r'#define MyAppVersion "([^"]+)"',
            (root / "scripts/installer.iss").read_text(encoding="utf-8"),
            "scripts/installer.iss",
        ),
        "products/web/app/package.json": frontend["version"],
        "products/web/app/package-lock.json": frontend_lock["version"],
        'products/web/app/package-lock.json packages[""]': frontend_lock["packages"][""]["version"],
        "desktop/electron/package.json": electron["version"],
    }


def _dynamic_metadata_errors(root: Path) -> list[str]:
    config = tomllib.loads((root / "pyproject.toml").read_text(encoding="utf-8"))
    project = config["project"]
    errors: list[str] = []
    if "version" in project:
        errors.append("pyproject.toml: project.version must not duplicate APP_VERSION")
    if "version" not in project.get("dynamic", []):
        errors.append("pyproject.toml: project.dynamic must contain version")

    providers = config.get("tool", {}).get("dynamic-metadata", [])
    expected = {
        "provider": "scikit_build_core.metadata.regex",
        "field": "version",
        "input": "core/version.py",
    }
    matches = [
        provider
        for provider in providers
        if all(provider.get(key) == value for key, value in expected.items())
    ]
    if len(matches) != 1:
        errors.append("pyproject.toml: expected one regex version provider reading core/version.py")
    includes = config.get("tool", {}).get("scikit-build", {}).get("sdist", {}).get("include", [])
    if "core/version.py" not in includes:
        errors.append("pyproject.toml: sdist must explicitly include core/version.py")
    return errors


def _python_consumer_errors(root: Path) -> list[str]:
    errors: list[str] = []
    for relative in _PYTHON_CONSUMERS:
        tree = ast.parse((root / relative).read_text(encoding="utf-8"), filename=relative)
        imports = [
            node
            for node in ast.walk(tree)
            if isinstance(node, ast.ImportFrom)
            and node.module == "core.version"
            and any(alias.name == "APP_VERSION" for alias in node.names)
        ]
        assignments = [
            node
            for node in ast.walk(tree)
            if (
                isinstance(node, ast.Assign)
                and any(
                    isinstance(target, ast.Name) and target.id == "APP_VERSION"
                    for target in node.targets
                )
            )
            or (
                isinstance(node, ast.AnnAssign)
                and isinstance(node.target, ast.Name)
                and node.target.id == "APP_VERSION"
            )
        ]
        if not imports:
            errors.append(f"{relative}: must import APP_VERSION from core.version")
        if assignments:
            errors.append(f"{relative}: local APP_VERSION fallback is forbidden")

    electron_main = (root / "desktop/electron/main.js").read_text(encoding="utf-8")
    if 'const APP_VERSION = require("./package.json").version;' not in electron_main:
        errors.append("desktop/electron/main.js: version must come from package.json")
    return errors


def validate(root: Path, *, tag: str | None = None) -> tuple[str, dict[str, str], list[str]]:
    """Return canonical version, observed static versions, and validation errors."""
    version = canonical_version(root)
    versions = _static_versions(root)
    errors = _dynamic_metadata_errors(root)
    errors.extend(_python_consumer_errors(root))
    for path, value in versions.items():
        if value != version:
            errors.append(f"{path} = {value} (expected {version})")
    if tag is not None and tag != f"v{version}":
        errors.append(f"release tag = {tag} (expected v{version})")
    return version, versions, errors


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--tag", help="Release tag to compare, for example v1.2.0")
    args = parser.parse_args()
    tag = args.tag
    if tag is None and os.environ.get("GITHUB_REF_TYPE") == "tag":
        tag = os.environ.get("GITHUB_REF_NAME")

    try:
        version, versions, errors = validate(args.root.resolve(), tag=tag)
    except (KeyError, OSError, SyntaxError, ValueError, json.JSONDecodeError) as exc:
        print(f"version check error: {exc}", file=sys.stderr)
        return 1

    print(f"app_version = {version}")
    print("core/version.py: canonical")
    print("pyproject.toml: dynamic from core/version.py")
    for path, value in versions.items():
        print(f"{path}: {value}")
    if tag is not None:
        print(f"release tag: {tag}")
    for error in errors:
        print(f"mismatch: {error}", file=sys.stderr)
    return 1 if errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
