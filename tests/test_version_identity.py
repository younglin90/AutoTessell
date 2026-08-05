"""Focused contract tests for the single-source release identity."""

from __future__ import annotations

import shutil
from pathlib import Path

import pytest

from scripts.check_version import validate

ROOT = Path(__file__).resolve().parents[1]
REQUIRED_FILES = (
    "core/version.py",
    "pyproject.toml",
    "products/web/api/version.py",
    "desktop/qt_main.py",
    "desktop/qt_app/main_window.py",
    "desktop/electron/main.js",
    "desktop/electron/package.json",
    "products/web/app/package.json",
    "products/web/app/package-lock.json",
    "scripts/installer.iss",
)


def _fixture_tree(tmp_path: Path) -> Path:
    for relative in REQUIRED_FILES:
        destination = tmp_path / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(ROOT / relative, destination)
    return tmp_path


def test_repository_release_identities_match_canonical() -> None:
    version, versions, errors = validate(ROOT, tag="v1.2.0")
    assert version == "1.2.0"
    assert set(versions.values()) == {version}
    assert errors == []


@pytest.mark.parametrize(
    ("relative", "old", "replacement", "label"),
    [
        (
            "scripts/installer.iss",
            'MyAppVersion "1.2.0"',
            'MyAppVersion "9.9.9"',
            "scripts/installer.iss",
        ),
        (
            "products/web/app/package.json",
            '"version": "1.2.0"',
            '"version": "9.9.9"',
            "products/web/app/package.json",
        ),
        (
            "products/web/app/package-lock.json",
            '"version": "1.2.0"',
            '"version": "9.9.9"',
            "products/web/app/package-lock.json",
        ),
        (
            "desktop/electron/package.json",
            '"version": "1.2.0"',
            '"version": "9.9.9"',
            "desktop/electron/package.json",
        ),
    ],
)
def test_static_consumer_mutation_is_rejected(
    tmp_path: Path,
    relative: str,
    old: str,
    replacement: str,
    label: str,
) -> None:
    root = _fixture_tree(tmp_path)
    target = root / relative
    target.write_text(
        target.read_text(encoding="utf-8").replace(old, replacement, 1),
        encoding="utf-8",
    )

    _, _, errors = validate(root)

    assert any(label in error for error in errors)


def test_local_python_version_fallback_is_rejected(tmp_path: Path) -> None:
    root = _fixture_tree(tmp_path)
    backend_version = root / "products/web/api/version.py"
    backend_version.write_text(
        backend_version.read_text(encoding="utf-8") + '\nAPP_VERSION = "9.9.9"\n',
        encoding="utf-8",
    )

    _, _, errors = validate(root)

    assert "products/web/api/version.py: local APP_VERSION fallback is forbidden" in errors


def test_packaging_must_read_the_canonical_file(tmp_path: Path) -> None:
    root = _fixture_tree(tmp_path)
    pyproject = root / "pyproject.toml"
    pyproject.write_text(
        pyproject.read_text(encoding="utf-8").replace(
            'input = "core/version.py"', 'input = "products/web/api/version.py"', 1
        ),
        encoding="utf-8",
    )

    _, _, errors = validate(root)

    assert any("regex version provider" in error for error in errors)


def test_release_tag_mismatch_is_rejected() -> None:
    _, _, errors = validate(ROOT, tag="v1.0.0")

    assert "release tag = v1.0.0 (expected v1.2.0)" in errors
