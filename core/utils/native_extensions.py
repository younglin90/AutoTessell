"""Optional native extension loaders.

The native kernels are release/build-time optional.  Callers should treat a
missing module as normal and keep their Python fallback path intact.
"""

from __future__ import annotations

import hashlib
import importlib
import os
import sys
from importlib.machinery import EXTENSION_SUFFIXES
from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path
from typing import Any

from core.utils.native_extension_manifest import (
    release_manifest_path,
    verify_native_extension_manifest,
)

_NATIVE_EXTENSIONS: dict[str, Any | None] = {}
_NATIVE_ATTEMPTED: set[str] = set()


def _configured_build_directory() -> Path | None:
    env_dir = os.environ.get("AUTOTESSELL_EXT_BUILD_DIR", "").strip()
    return Path(env_dir) if env_dir else None


def _add_native_extension_paths() -> None:
    candidate_dirs: list[Path] = []
    explicit_dir = _configured_build_directory()
    if explicit_dir is not None:
        candidate_dirs.append(explicit_dir)
    repo_root = Path(__file__).resolve().parents[2]
    build_root = repo_root / "auto_tessell_core" / "build"
    candidate_dirs.append(build_root)
    # The optional surface BL product is staged below its own package output.
    # This developer-mode path is never consulted by release manifest mode.
    candidate_dirs.append(build_root / "surface_bl_package" / "native_extensions")

    # Insert defaults first and the explicit override last so repeated
    # ``insert(0, ...)`` leaves AUTOTESSELL_EXT_BUILD_DIR at highest priority.
    for candidate in reversed(candidate_dirs):
        if candidate.is_dir():
            candidate_s = str(candidate)
            while candidate_s in sys.path:
                sys.path.remove(candidate_s)
            sys.path.insert(0, candidate_s)


def _native_extension_candidate(directory: Path, module_name: str) -> Path | None:
    for suffix in (*EXTENSION_SUFFIXES, ".py"):
        candidate = directory / f"{module_name}{suffix}"
        if candidate.is_file():
            return candidate
    return None


def _module_is_from_directory(module: Any, directory: Path) -> bool:
    module_file = getattr(module, "__file__", None)
    if not module_file:
        return False
    try:
        return Path(module_file).resolve().parent == directory.resolve()
    except OSError:
        return False


def _load_explicit_native_extension(module_name: str, candidate: Path) -> Any:
    digest = hashlib.sha256(str(candidate.resolve()).encode()).hexdigest()[:16]
    alias = f"_autotessell_native_{digest}.{module_name}"
    spec = spec_from_file_location(alias, candidate)
    if spec is None or spec.loader is None:
        raise ImportError(f"cannot load explicit native extension candidate: {candidate}")
    module = module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def import_native_extension(module_name: str) -> Any:
    """Import one first-party native module with explicit-build precedence.

    Release mode is deliberately manifest-only. Developer/test mode retains
    the historical explicit build-directory behavior.

    A candidate present under ``AUTOTESSELL_EXT_BUILD_DIR`` wins even when an
    older module with the same top-level name is cached in ``sys.modules``.
    When the explicit directory does not contain the requested module, normal
    repository/PYTHONPATH fallback behavior remains available.
    """
    if os.environ.get("AUTOTESSELL_NATIVE_RELEASE_MODE", "").strip().lower() in {
        "1", "true", "yes"
    }:
        manifest = release_manifest_path()
        if manifest is None:
            raise ImportError("native_extension_manifest_refused:manifest_not_configured")
        candidate, reason = verify_native_extension_manifest(
            manifest, module_name=module_name
        )
        if candidate is None:
            raise ImportError(f"native_extension_manifest_refused:{reason}")
        return _load_explicit_native_extension(module_name, candidate)

    _add_native_extension_paths()
    importlib.invalidate_caches()

    explicit_dir = _configured_build_directory()
    explicit_candidate = (
        _native_extension_candidate(explicit_dir, module_name)
        if explicit_dir is not None and explicit_dir.is_dir()
        else None
    )
    if explicit_candidate is not None:
        assert explicit_dir is not None
        cached = sys.modules.get(module_name)
        if cached is not None and _module_is_from_directory(cached, explicit_dir):
            return cached
        if cached is not None:
            return _load_explicit_native_extension(module_name, explicit_candidate)

    return importlib.import_module(module_name)


def load_native_extension(module_name: str) -> Any | None:
    """Return an optional pybind11 module if available."""
    if module_name in _NATIVE_ATTEMPTED:
        return _NATIVE_EXTENSIONS.get(module_name)
    _NATIVE_ATTEMPTED.add(module_name)
    try:
        _NATIVE_EXTENSIONS[module_name] = import_native_extension(module_name)
    except Exception:  # pragma: no cover - optional extension
        _NATIVE_EXTENSIONS[module_name] = None
    return _NATIVE_EXTENSIONS[module_name]


def load_native_metrics() -> Any | None:
    """Return the optional ``native_metrics`` pybind11 module if available."""
    return load_native_extension("native_metrics")


def load_native_bl() -> Any | None:
    """Return the optional ``native_bl`` boundary-layer kernel module."""
    return load_native_extension("native_bl")


def load_native_polymesh() -> Any | None:
    """Return the optional ``native_polymesh`` pybind11 module if available."""
    return load_native_extension("native_polymesh")


def load_native_poly_quality_relocation() -> Any | None:
    """Return the optional C++23 Native Poly quality relocation kernel."""
    return load_native_extension("native_poly_quality_relocation")


def load_native_poly_bl_local_front_qopt() -> Any | None:
    """Return the optional C++23 Native Poly local BL front optimizer."""
    return load_native_extension("native_poly_bl_local_front_qopt")


def load_native_surface_bl_quality() -> Any | None:
    """Return the optional native wall-edge surface BL quality kernel."""
    return load_native_extension("native_surface_bl_quality")


def load_native_snap() -> Any | None:
    """Return the optional ``native_snap`` pybind11 module if available."""
    return load_native_extension("native_snap")


def load_native_tet_predicates() -> Any | None:
    """Return the optional exact tetrahedral predicate/metric module."""
    return load_native_extension("native_tet_predicates")


def load_native_tet_qopt() -> Any | None:
    """Return the optional guarded tetrahedral optimizer module."""
    return load_native_extension("native_tet_qopt")


def load_native_tri_quality_repair() -> Any | None:
    """Return the optional C++23 Native Tri constrained quality repair kernel."""
    return load_native_extension("native_tri_quality_repair")
