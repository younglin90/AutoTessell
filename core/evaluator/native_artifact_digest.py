"""Fail-closed adapter for the C++ native artifact digest kernel."""

from __future__ import annotations

from pathlib import Path
from typing import Iterable

try:
    import native_artifact_fingerprint as _native
except ImportError:
    _native = None

_IMPLEMENTATION = "native_artifact_fingerprint"
_ALGORITHM = "SHA-256"


def _digest(value: object) -> bool:
    return (
        isinstance(value, str)
        and len(value) == 64
        and value == value.lower()
        and all(character in "0123456789abcdef" for character in value)
    )


def native_tree_fingerprint(root: Path) -> dict[str, object]:
    """Return one native tree witness, or a structured fail-closed result."""
    if _native is None:
        return {
            "valid": False,
            "status": "native_kernel_unavailable",
            "algorithm": _ALGORITHM,
            "implementation": _IMPLEMENTATION,
        }
    path = Path(root)
    if not path.is_dir():
        return {
            "valid": False,
            "status": "artifact_root_not_directory",
            "algorithm": _ALGORITHM,
            "implementation": _IMPLEMENTATION,
        }
    try:
        result = _native.fingerprint_tree(str(path))
    except Exception as exc:
        return {
            "valid": False,
            "status": "native_kernel_error",
            "error": type(exc).__name__,
            "algorithm": _ALGORITHM,
            "implementation": _IMPLEMENTATION,
        }
    if not isinstance(result, dict):
        return {
            "valid": False,
            "status": "native_result_not_object",
            "algorithm": _ALGORITHM,
            "implementation": _IMPLEMENTATION,
        }
    tree_sha256 = result.get("tree_sha256")
    entry_count = result.get("entry_count")
    if (
        not _digest(tree_sha256)
        or isinstance(entry_count, bool)
        or not isinstance(entry_count, int)
        or entry_count < 1
        or result.get("symlinks_forbidden") is not True
        or result.get("special_files_forbidden") is not True
    ):
        return {
            "valid": False,
            "status": "native_result_malformed",
            "algorithm": _ALGORITHM,
            "implementation": _IMPLEMENTATION,
        }
    return {
        "valid": True,
        "status": "native_recomputed",
        "algorithm": _ALGORITHM,
        "implementation": _IMPLEMENTATION,
        "tree_sha256": tree_sha256,
        "entry_count": entry_count,
    }


def native_artifact_witness(
    case_dirs: Iterable[Path], relative_root: str | Path
) -> dict[str, object]:
    """Recompute a deterministic native witness for every repeated run."""
    roots = [Path(case_dir) / Path(relative_root) for case_dir in case_dirs]
    results = [native_tree_fingerprint(root) for root in roots]
    relative = Path(relative_root).as_posix()
    if not results or any(result.get("valid") is not True for result in results):
        return {
            "valid": False,
            "status": "native_recomputation_failed",
            "algorithm": _ALGORITHM,
            "implementation": _IMPLEMENTATION,
            "root_relative": relative,
            "recomputed": False,
            "runs": results,
        }
    digests = [str(result["tree_sha256"]) for result in results]
    counts = [int(result["entry_count"]) for result in results]
    return {
        "valid": True,
        "status": "native_recomputed",
        "algorithm": _ALGORITHM,
        "implementation": _IMPLEMENTATION,
        "root_relative": relative,
        "tree_sha256": digests[0],
        "witness_repeats": digests,
        "entry_count": counts[0],
        "entry_counts": counts,
        "recomputed": True,
    }


__all__ = ["native_tree_fingerprint", "native_artifact_witness"]
