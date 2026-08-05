"""Immutable, copy-only corpus contract for native release measurements.

The release runner must not regenerate a baseline while it is measuring a
native engine.  This module records a path-independent SHA-256 lock for each
case and verifies the lock before copying a case into a private worktree.
It is control-plane code: the native meshing and artifact-tree kernels remain
responsible for production geometry and topology measurements.
"""

from __future__ import annotations

import hashlib
import json
import os
import shutil
from pathlib import Path
from typing import Any, Mapping, Sequence


SCHEMA = "autotessell/native-frozen-corpus/v1"
VERSION = 1
REQUIRED_MESH_FILES = ("points", "faces", "owner", "neighbour", "boundary")
_HEX = frozenset("0123456789abcdef")


def _canonical(value: Any) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=True,
        allow_nan=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")


def canonical_sha256(value: Any) -> str:
    return hashlib.sha256(_canonical(value)).hexdigest()


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _relative_path(root: Path, path: Path) -> str:
    try:
        relative = path.absolute().relative_to(root.absolute())
    except ValueError as exc:
        raise ValueError("corpus_path_escapes_root") from exc
    return relative.as_posix()


def fingerprint_frozen_case(
    case_root: str | Path,
    *,
    required_files: Sequence[str] = (),
) -> dict[str, Any]:
    """Fingerprint every regular file in one frozen case.

    Symlinks are rejected deliberately: a release lock must bind bytes in the
    corpus itself, not a mutable external path.  The tree digest includes
    relative path, byte length, and file SHA-256 in sorted order.
    """
    root = Path(case_root)
    if not root.is_dir() or root.is_symlink():
        raise ValueError("frozen_case_not_directory")
    entries: list[dict[str, Any]] = []
    for path in sorted(root.rglob("*")):
        if path.is_symlink():
            raise ValueError(f"frozen_case_symlink:{_relative_path(root, path)}")
        if not path.is_file():
            continue
        relative = _relative_path(root, path)
        entries.append(
            {
                "path": relative,
                "size": path.stat().st_size,
                "sha256": _sha256_file(path),
            }
        )
    required = sorted({str(item).replace("\\", "/") for item in required_files})
    paths = {entry["path"] for entry in entries}
    missing = [item for item in required if item not in paths]
    if missing:
        raise ValueError("frozen_case_required_missing:" + ",".join(missing))
    return {
        "tree_sha256": canonical_sha256(entries),
        "entry_count": len(entries),
        "files": entries,
        "required_files": required,
    }


def build_frozen_corpus_lock(
    corpus_root: str | Path,
    cases: Mapping[str, str | Path],
    *,
    required_files: Mapping[str, Sequence[str]] | None = None,
    corpus_id: str = "native-release-corpus",
) -> dict[str, Any]:
    """Build a lock without modifying the corpus."""
    root = Path(corpus_root).resolve()
    if not root.is_dir():
        raise ValueError("corpus_root_not_directory")
    if not cases:
        raise ValueError("frozen_corpus_empty")
    required_files = required_files or {}
    records: dict[str, Any] = {}
    for case_id in sorted(cases):
        if not case_id or case_id in {".", ".."}:
            raise ValueError("frozen_case_id_invalid")
        case_path = Path(cases[case_id])
        if not case_path.is_absolute():
            case_path = root / case_path
        case_path = case_path.resolve()
        relative = _relative_path(root, case_path)
        records[case_id] = {
            "root": relative,
            **fingerprint_frozen_case(
                case_path,
                required_files=required_files.get(case_id, ()),
            ),
        }
    lock = {
        "schema": SCHEMA,
        "version": VERSION,
        "corpus_id": str(corpus_id),
        "cases": records,
    }
    lock["lock_sha256"] = canonical_sha256(lock)
    return lock


def validate_frozen_corpus_lock(
    lock: Mapping[str, Any],
    corpus_root: str | Path,
    *,
    case_ids: Sequence[str] | None = None,
) -> dict[str, Any]:
    """Re-hash locked cases and return auditable reasons, never partial pass."""
    reasons: list[str] = []
    if not isinstance(lock, Mapping) or lock.get("schema") != SCHEMA:
        return {"accepted": False, "reasons": ["schema"], "cases": {}}
    if lock.get("version") != VERSION:
        reasons.append("version")
    cases = lock.get("cases")
    if not isinstance(cases, Mapping) or not cases:
        return {"accepted": False, "reasons": ["cases"], "cases": {}}
    expected_lock = dict(lock)
    supplied_digest = expected_lock.pop("lock_sha256", None)
    if not isinstance(supplied_digest, str) or len(supplied_digest) != 64 or set(supplied_digest) - _HEX:
        reasons.append("lock_sha256_invalid")
    elif supplied_digest != canonical_sha256(expected_lock):
        reasons.append("lock_sha256_mismatch")
    root = Path(corpus_root).resolve()
    selected = set(case_ids) if case_ids is not None else set(cases)
    results: dict[str, Any] = {}
    for case_id in sorted(selected):
        record = cases.get(case_id)
        if not isinstance(record, Mapping):
            results[case_id] = {"accepted": False, "reasons": ["case_record"]}
            reasons.append(f"{case_id}:case_record")
            continue
        relative = record.get("root")
        if not isinstance(relative, str) or not relative or Path(relative).is_absolute():
            results[case_id] = {"accepted": False, "reasons": ["case_root"]}
            reasons.append(f"{case_id}:case_root")
            continue
        case_root = (root / relative).resolve()
        try:
            case_fingerprint = fingerprint_frozen_case(
                case_root,
                required_files=record.get("required_files", ()),
            )
        except (OSError, ValueError) as exc:
            result = {"accepted": False, "reasons": [str(exc)]}
            results[case_id] = result
            reasons.append(f"{case_id}:{exc}")
            continue
        expected = {
            key: record.get(key)
            for key in ("tree_sha256", "entry_count", "files", "required_files")
        }
        accepted = case_fingerprint == expected
        result = {
            "accepted": accepted,
            "reasons": [] if accepted else ["case_fingerprint_mismatch"],
            "tree_sha256": case_fingerprint["tree_sha256"],
            "entry_count": case_fingerprint["entry_count"],
        }
        results[case_id] = result
        if not accepted:
            reasons.append(f"{case_id}:case_fingerprint_mismatch")
    unknown = selected - set(cases)
    for case_id in sorted(unknown):
        results[case_id] = {"accepted": False, "reasons": ["case_unknown"]}
        reasons.append(f"{case_id}:case_unknown")
    return {
        "accepted": not reasons and all(item.get("accepted") for item in results.values()),
        "reasons": sorted(set(reasons)),
        "cases": results,
        "lock_sha256": supplied_digest,
    }


def seal_frozen_corpus_lock(path: str | Path, lock: Mapping[str, Any]) -> None:
    """Write a valid lock once; an existing lock is never overwritten."""
    result = validate_frozen_corpus_lock(lock, Path(path).parent)
    if not result["accepted"]:
        # A lock may be sealed before it is placed beside the corpus. Validate
        # its internal structure here and defer filesystem verification.
        if lock.get("schema") != SCHEMA or lock.get("lock_sha256") != canonical_sha256(
            {key: value for key, value in lock.items() if key != "lock_sha256"}
        ):
            raise ValueError("invalid_frozen_corpus_lock")
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    descriptor = os.open(target, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o644)
    try:
        payload = (_canonical(lock) + b"\n")
        os.write(descriptor, payload)
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def copy_locked_case(
    lock_path: str | Path,
    case_id: str,
    destination: str | Path,
) -> Path:
    """Verify the lock, then copy exactly one case into a new private path."""
    lock_file = Path(lock_path)
    lock = json.loads(lock_file.read_text(encoding="utf-8"))
    verification = validate_frozen_corpus_lock(lock, lock_file.parent)
    if not verification["accepted"]:
        raise ValueError("frozen_corpus_verification_failed:" + ",".join(verification["reasons"]))
    records = lock["cases"]
    if case_id not in records:
        raise KeyError(case_id)
    source = (lock_file.parent / records[case_id]["root"]).resolve()
    target = Path(destination)
    if target.exists():
        raise FileExistsError(target)
    shutil.copytree(source, target, symlinks=False)
    post = fingerprint_frozen_case(target, required_files=records[case_id]["required_files"])
    if post["tree_sha256"] != records[case_id]["tree_sha256"]:
        shutil.rmtree(target)
        raise ValueError("frozen_case_copy_digest_mismatch")
    return target


__all__ = [
    "REQUIRED_MESH_FILES",
    "SCHEMA",
    "VERSION",
    "build_frozen_corpus_lock",
    "canonical_sha256",
    "copy_locked_case",
    "fingerprint_frozen_case",
    "seal_frozen_corpus_lock",
    "validate_frozen_corpus_lock",
]
