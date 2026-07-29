"""Optional native extension loaders.

The native kernels are release/build-time optional.  Callers should treat a
missing module as normal and keep their Python fallback path intact.
"""
from __future__ import annotations

import importlib
import os
import sys
from pathlib import Path
from typing import Any

_NATIVE_EXTENSIONS: dict[str, Any | None] = {}
_NATIVE_ATTEMPTED: set[str] = set()


def _add_native_extension_paths() -> None:
    candidate_dirs: list[Path] = []
    env_dir = os.environ.get("AUTOTESSELL_EXT_BUILD_DIR", "").strip()
    if env_dir:
        candidate_dirs.append(Path(env_dir))
    repo_root = Path(__file__).resolve().parents[2]
    candidate_dirs.append(repo_root / "auto_tessell_core" / "build")

    for candidate in candidate_dirs:
        if candidate.is_dir():
            candidate_s = str(candidate)
            if candidate_s not in sys.path:
                sys.path.insert(0, candidate_s)


def load_native_extension(module_name: str) -> Any | None:
    """Return an optional pybind11 module if available."""
    if module_name in _NATIVE_ATTEMPTED:
        return _NATIVE_EXTENSIONS.get(module_name)
    _NATIVE_ATTEMPTED.add(module_name)
    _add_native_extension_paths()
    try:
        _NATIVE_EXTENSIONS[module_name] = importlib.import_module(module_name)
    except Exception:  # pragma: no cover - optional extension
        _NATIVE_EXTENSIONS[module_name] = None
    return _NATIVE_EXTENSIONS[module_name]


def load_native_metrics() -> Any | None:
    """Return the optional ``native_metrics`` pybind11 module if available."""
    return load_native_extension("native_metrics")


def load_native_polymesh() -> Any | None:
    """Return the optional ``native_polymesh`` pybind11 module if available."""
    return load_native_extension("native_polymesh")


def load_native_snap() -> Any | None:
    """Return the optional ``native_snap`` pybind11 module if available."""
    return load_native_extension("native_snap")
