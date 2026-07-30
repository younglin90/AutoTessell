"""Native extension search-order contracts."""
from __future__ import annotations

import sys
from pathlib import Path

import core.utils.native_extensions as subject


def test_explicit_build_directory_has_highest_import_priority(
    tmp_path: Path,
    monkeypatch,
) -> None:
    explicit = tmp_path / "explicit-native-build"
    explicit.mkdir()
    monkeypatch.setenv("AUTOTESSELL_EXT_BUILD_DIR", str(explicit))
    original_path = list(sys.path)
    try:
        subject._add_native_extension_paths()
        assert sys.path[0] == str(explicit)
    finally:
        sys.path[:] = original_path
