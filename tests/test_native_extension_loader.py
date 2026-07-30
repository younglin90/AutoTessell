"""Native extension search-order contracts."""

from __future__ import annotations

import os
import subprocess
import sys
import textwrap
from pathlib import Path

import pytest

import core.utils.native_extensions as subject


def _run_loader_script(script: str) -> list[str]:
    repo_root = Path(__file__).resolve().parents[1]
    env = os.environ.copy()
    env["PYTHONPATH"] = os.pathsep.join([str(repo_root), env.get("PYTHONPATH", "")]).rstrip(
        os.pathsep
    )
    completed = subprocess.run(
        [sys.executable, "-c", textwrap.dedent(script)],
        cwd=repo_root,
        env=env,
        check=True,
        capture_output=True,
        text=True,
    )
    return completed.stdout.splitlines()


def test_explicit_build_directory_has_highest_import_priority(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
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


def test_explicit_candidate_replaces_stale_module_name_cache(tmp_path: Path) -> None:
    default_build = tmp_path / "repo-build"
    explicit_build = tmp_path / "explicit-build"
    default_build.mkdir()
    explicit_build.mkdir()
    module_name = "native_loader_abi_fixture"
    default_module = default_build / f"{module_name}.py"
    explicit_module = explicit_build / f"{module_name}.py"
    default_module.write_text("ABI_MARKER = 1\n", encoding="utf-8")
    explicit_module.write_text("ABI_MARKER = 2\n", encoding="utf-8")

    lines = _run_loader_script(f"""
        import importlib
        import os
        import sys
        from core.utils.native_extensions import import_native_extension

        sys.path.insert(0, {str(default_build)!r})
        stale = importlib.import_module({module_name!r})
        assert stale.ABI_MARKER == 1
        os.environ["AUTOTESSELL_EXT_BUILD_DIR"] = {str(explicit_build)!r}
        loaded = import_native_extension({module_name!r})
        print(loaded.ABI_MARKER)
        print(loaded.__file__)
        print(sys.path[0])
        print(sys.modules[{module_name!r}].ABI_MARKER)
        """)

    assert lines == ["2", str(explicit_module), str(explicit_build), "1"]


def test_broken_explicit_candidate_never_falls_through_to_stale_cache(
    tmp_path: Path,
) -> None:
    default_build = tmp_path / "repo-build"
    explicit_build = tmp_path / "broken-explicit-build"
    default_build.mkdir()
    explicit_build.mkdir()
    module_name = "native_loader_broken_fixture"
    (default_build / f"{module_name}.py").write_text("ABI_MARKER = 1\n", encoding="utf-8")
    (explicit_build / f"{module_name}.py").write_text(
        "raise RuntimeError('explicit ABI import failed')\n",
        encoding="utf-8",
    )

    lines = _run_loader_script(f"""
        import importlib
        import os
        import sys
        from core.utils.native_extensions import import_native_extension

        sys.path.insert(0, {str(default_build)!r})
        stale = importlib.import_module({module_name!r})
        os.environ["AUTOTESSELL_EXT_BUILD_DIR"] = {str(explicit_build)!r}
        try:
            import_native_extension({module_name!r})
        except RuntimeError as exc:
            print(exc)
        else:
            raise AssertionError("broken explicit ABI silently used stale module")
        print(sys.modules[{module_name!r}].ABI_MARKER)
        """)

    assert lines == ["explicit ABI import failed", "1"]


def test_optional_loader_maps_broken_explicit_candidate_to_none(tmp_path: Path) -> None:
    explicit_build = tmp_path / "broken-explicit-build"
    explicit_build.mkdir()
    module_name = "native_loader_optional_fixture"
    (explicit_build / f"{module_name}.py").write_text(
        "raise RuntimeError('optional explicit ABI import failed')\n",
        encoding="utf-8",
    )

    lines = _run_loader_script(f"""
        import os
        from core.utils.native_extensions import load_native_extension

        os.environ["AUTOTESSELL_EXT_BUILD_DIR"] = {str(explicit_build)!r}
        print(load_native_extension({module_name!r}) is None)
        """)

    assert lines == ["True"]


def test_missing_explicit_candidate_retains_cached_fallback(tmp_path: Path) -> None:
    default_build = tmp_path / "repo-build"
    explicit_build = tmp_path / "empty-explicit-build"
    default_build.mkdir()
    explicit_build.mkdir()
    module_name = "native_loader_missing_fixture"
    default_module = default_build / f"{module_name}.py"
    default_module.write_text("ABI_MARKER = 1\n", encoding="utf-8")

    lines = _run_loader_script(f"""
        import importlib
        import os
        import sys
        from core.utils.native_extensions import import_native_extension

        sys.path.insert(0, {str(default_build)!r})
        stale = importlib.import_module({module_name!r})
        os.environ["AUTOTESSELL_EXT_BUILD_DIR"] = {str(explicit_build)!r}
        loaded = import_native_extension({module_name!r})
        print(loaded.ABI_MARKER)
        print(loaded.__file__)
        print(sys.path[0])
        """)

    assert lines == ["1", str(default_module), str(explicit_build)]
