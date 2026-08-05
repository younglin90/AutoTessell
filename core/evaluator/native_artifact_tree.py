"""Native staged artifact-tree fingerprint bridge.

The release path intentionally has no Python filesystem fallback. If the first-party
C++ kernel is unavailable, authority construction refuses closed.
"""

from __future__ import annotations

import importlib
import sys
from pathlib import Path
from typing import Any, Mapping


def _load_kernel() -> Any:
    try:
        return importlib.import_module("native_artifact_fingerprint")
    except ImportError:
        build = Path(__file__).resolve().parents[2] / "auto_tessell_core" / "build"
        if build.is_dir() and str(build) not in sys.path:
            sys.path.insert(0, str(build))
        try:
            return importlib.import_module("native_artifact_fingerprint")
        except ImportError as error:
            raise RuntimeError("native_artifact_fingerprint_unavailable") from error


def fingerprint_staged_artifact_tree(root: str | Path) -> Mapping[str, Any]:
    path = Path(root)
    if not path.is_dir():
        raise ValueError("artifact_root_not_directory")
    return _load_kernel().fingerprint_tree(str(path))


def validate_staged_artifact_tree(
    root: str | Path,
    *,
    expected_sha256: str,
    expected_entry_count: int,
) -> Mapping[str, Any]:
    result = fingerprint_staged_artifact_tree(root)
    if result.get("tree_sha256") != expected_sha256:
        raise ValueError("artifact_tree_digest_mismatch")
    if result.get("entry_count") != expected_entry_count:
        raise ValueError("artifact_tree_entry_count_mismatch")
    return result


__all__ = ["fingerprint_staged_artifact_tree", "validate_staged_artifact_tree"]
