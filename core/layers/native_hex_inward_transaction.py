"""Crash-recoverable same-filesystem transaction for native hex BL."""

from __future__ import annotations

import json
import os
import re
import shutil
import uuid
from dataclasses import dataclass
from pathlib import Path

from core.layers.native_hex_inward_lock import (
    HexBLTransactionError,
    HexBLTransactionLock,
    _require_held_lock,
)

_TOKEN_PATTERN = re.compile(r"[0-9a-f]{32}")
_MARKER_NAME = ".autotessell_hexbl_transaction.json"
_VALID_STATES = frozenset({"staging", "prepared", "backed_up", "committed"})


@dataclass(frozen=True)
class HexBLTransactionPaths:
    constant_dir: Path
    token: str
    target: Path
    stage_root: Path
    stage_poly: Path
    candidate: Path
    backup: Path
    marker: Path
    marker_update: Path


def _validated_paths(constant_dir: Path, token: str) -> HexBLTransactionPaths:
    if _TOKEN_PATTERN.fullmatch(token) is None:
        raise HexBLTransactionError("invalid transaction token")
    constant = constant_dir.resolve()
    target = constant / "polyMesh"
    stage_root = constant / f".autotessell_hexbl_stage_{token}"
    candidate = constant / f".autotessell_hexbl_candidate_{token}"
    backup = constant / f".autotessell_hexbl_backup_{token}"
    marker = constant / _MARKER_NAME
    marker_update = constant / f".autotessell_hexbl_marker_update_{token}"
    for path in (target, stage_root, candidate, backup, marker, marker_update):
        if path.resolve(strict=False).parent != constant:
            raise HexBLTransactionError("transaction path escaped constant directory")
    return HexBLTransactionPaths(
        constant_dir=constant,
        token=token,
        target=target,
        stage_root=stage_root,
        stage_poly=stage_root / "constant" / "polyMesh",
        candidate=candidate,
        backup=backup,
        marker=marker,
        marker_update=marker_update,
    )


def _fsync_directory(path: Path) -> None:
    try:
        descriptor = os.open(path, os.O_RDONLY | os.O_DIRECTORY)
        try:
            os.fsync(descriptor)
        finally:
            os.close(descriptor)
    except OSError as exc:
        raise HexBLTransactionError(f"directory fsync failed:{path}:{exc}") from exc


def _fsync_tree(root: Path) -> None:
    try:
        directories: list[Path] = []
        for current, dir_names, file_names in os.walk(root, followlinks=False):
            current_path = Path(current)
            directories.append(current_path)
            for name in file_names:
                file_path = current_path / name
                if file_path.is_symlink():
                    continue
                descriptor = os.open(file_path, os.O_RDONLY)
                try:
                    os.fsync(descriptor)
                finally:
                    os.close(descriptor)
            for name in dir_names:
                directory = current_path / name
                if directory.is_symlink():
                    continue
        for directory in reversed(directories):
            _fsync_directory(directory)
    except HexBLTransactionError:
        raise
    except OSError as exc:
        raise HexBLTransactionError(f"tree fsync failed:{root}:{exc}") from exc


def _write_marker(
    lock: HexBLTransactionLock,
    paths: HexBLTransactionPaths,
    state: str,
    *,
    create: bool,
) -> None:
    _require_held_lock(lock, paths.constant_dir)
    if state not in _VALID_STATES:
        raise HexBLTransactionError(f"invalid transaction state:{state}")
    payload = json.dumps(
        {"version": 1, "token": paths.token, "state": state},
        sort_keys=True,
        separators=(",", ":"),
    ).encode("ascii")
    try:
        if create:
            with paths.marker.open("xb") as stream:
                stream.write(payload)
                stream.flush()
                os.fsync(stream.fileno())
        else:
            if paths.marker_update.exists() or paths.marker_update.is_symlink():
                raise HexBLTransactionError("marker update path already exists")
            with paths.marker_update.open("xb") as stream:
                stream.write(payload)
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(paths.marker_update, paths.marker)
        _fsync_directory(paths.constant_dir)
    except HexBLTransactionError:
        raise
    except OSError as exc:
        raise HexBLTransactionError(f"marker durability failed:{state}:{exc}") from exc


def _read_marker(constant_dir: Path) -> tuple[HexBLTransactionPaths, str] | None:
    marker = constant_dir / _MARKER_NAME
    if marker.is_symlink():
        raise HexBLTransactionError("transaction marker is a symlink")
    if not marker.exists():
        return None
    try:
        payload = json.loads(marker.read_text(encoding="ascii"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise HexBLTransactionError(f"invalid transaction marker:{exc}") from exc
    if set(payload) != {"version", "token", "state"} or payload["version"] != 1:
        raise HexBLTransactionError("invalid transaction marker schema")
    token = payload["token"]
    state = payload["state"]
    if not isinstance(token, str) or _TOKEN_PATTERN.fullmatch(token) is None:
        raise HexBLTransactionError("invalid transaction marker token")
    if not isinstance(state, str) or state not in _VALID_STATES:
        raise HexBLTransactionError("invalid transaction marker state")
    return _validated_paths(constant_dir, token), state


def _assert_directory_or_absent(path: Path, label: str) -> None:
    if path.is_symlink():
        raise HexBLTransactionError(f"{label} is a symlink")
    if path.exists() and not path.is_dir():
        raise HexBLTransactionError(f"{label} is not a directory")


def _remove_tree(path: Path) -> None:
    if path.is_symlink():
        raise HexBLTransactionError(f"refuse to remove symlink:{path.name}")
    if path.exists():
        shutil.rmtree(path)


def recover_hexbl_transaction(lock: HexBLTransactionLock) -> str:
    """Recover one marker-owned transaction using directory topology."""
    constant = _require_held_lock(lock)
    target = constant / "polyMesh"
    if target.is_symlink():
        raise HexBLTransactionError("polyMesh is a symlink")
    marker_record = _read_marker(constant)
    if marker_record is None:
        return "none"
    paths, state = marker_record
    if paths.marker_update.is_symlink():
        raise HexBLTransactionError("marker update is a symlink")
    for path, label in (
        (paths.target, "polyMesh"),
        (paths.stage_root, "stage"),
        (paths.candidate, "candidate"),
        (paths.backup, "backup"),
    ):
        _assert_directory_or_absent(path, label)

    target_exists = paths.target.is_dir()
    backup_exists = paths.backup.is_dir()
    candidate_exists = paths.candidate.is_dir()
    topology = target_exists, backup_exists, candidate_exists
    action: str
    if topology == (True, False, False):
        _remove_tree(paths.stage_root)
        action = (
            "rolled_back_before_backup" if state in {"staging", "prepared"} else "finalized_commit"
        )
    elif topology == (True, False, True):
        if state not in {"staging", "prepared"}:
            raise HexBLTransactionError(
                f"ambiguous transaction topology:{state}:target+candidate",
            )
        if candidate_exists:
            _remove_tree(paths.candidate)
        _remove_tree(paths.stage_root)
        action = "rolled_back_before_backup"
    elif topology in {(False, True, True), (False, True, False)}:
        os.replace(paths.backup, paths.target)
        _fsync_directory(paths.constant_dir)
        if candidate_exists:
            _remove_tree(paths.candidate)
        _remove_tree(paths.stage_root)
        action = "restored_backup"
    elif topology == (True, True, False):
        if state not in {"backed_up", "committed"}:
            raise HexBLTransactionError(
                f"ambiguous transaction topology:{state}:target+backup",
            )
        _remove_tree(paths.backup)
        _remove_tree(paths.stage_root)
        action = "finalized_commit"
    elif topology == (True, True, True):
        raise HexBLTransactionError(
            f"ambiguous transaction topology:{state}:target+backup+candidate",
        )
    else:
        raise HexBLTransactionError(
            f"unrecoverable transaction topology:{state}:{topology}",
        )

    paths.marker.unlink()
    if paths.marker_update.exists() and not paths.marker_update.is_symlink():
        paths.marker_update.unlink()
    _fsync_directory(paths.constant_dir)
    return action


def begin_hexbl_transaction(lock: HexBLTransactionLock) -> HexBLTransactionPaths:
    """Create a durable staging marker and copy the entire original polyMesh."""
    constant = _require_held_lock(lock)
    if not constant.is_dir():
        raise HexBLTransactionError("constant directory missing")
    token = uuid.uuid4().hex
    paths = _validated_paths(constant, token)
    if paths.target.is_symlink() or not paths.target.is_dir():
        raise HexBLTransactionError("polyMesh must be a real directory")
    for path, label in (
        (paths.stage_root, "stage"),
        (paths.candidate, "candidate"),
        (paths.backup, "backup"),
        (paths.marker, "marker"),
        (paths.marker_update, "marker update"),
    ):
        if path.exists() or path.is_symlink():
            raise HexBLTransactionError(f"pre-existing {label} path")
    _write_marker(lock, paths, "staging", create=True)
    try:
        paths.stage_poly.parent.mkdir(parents=True)
        shutil.copytree(paths.target, paths.stage_poly, symlinks=True)
    except OSError as exc:
        raise HexBLTransactionError(f"polyMesh staging copy failed:{exc}") from exc
    return paths


def prepare_hexbl_candidate(
    lock: HexBLTransactionLock,
    paths: HexBLTransactionPaths,
) -> None:
    """Durably move the validated staged polyMesh to the candidate slot."""
    _require_held_lock(lock, paths.constant_dir)
    _assert_directory_or_absent(paths.target, "polyMesh")
    _assert_directory_or_absent(paths.stage_poly, "staged polyMesh")
    if not paths.target.is_dir() or not paths.stage_poly.is_dir():
        raise HexBLTransactionError("target or staged polyMesh missing")
    for path, label in ((paths.candidate, "candidate"), (paths.backup, "backup")):
        if path.exists() or path.is_symlink():
            raise HexBLTransactionError(f"pre-existing {label} path")
    _fsync_tree(paths.stage_poly)
    os.replace(paths.stage_poly, paths.candidate)
    _fsync_directory(paths.stage_poly.parent)
    _fsync_directory(paths.constant_dir)
    _write_marker(lock, paths, "prepared", create=False)


def commit_hexbl_candidate(
    lock: HexBLTransactionLock,
    paths: HexBLTransactionPaths,
) -> None:
    """Commit the candidate with two atomic directory renames."""
    _require_held_lock(lock, paths.constant_dir)
    for path, label in (
        (paths.target, "polyMesh"),
        (paths.candidate, "candidate"),
        (paths.backup, "backup"),
    ):
        _assert_directory_or_absent(path, label)
    if not paths.target.is_dir() or not paths.candidate.is_dir():
        raise HexBLTransactionError("target or candidate missing before commit")
    if paths.backup.exists():
        raise HexBLTransactionError("backup already exists before commit")

    os.replace(paths.target, paths.backup)
    _fsync_directory(paths.constant_dir)
    _write_marker(lock, paths, "backed_up", create=False)
    os.replace(paths.candidate, paths.target)
    _fsync_directory(paths.constant_dir)
    _write_marker(lock, paths, "committed", create=False)
    _remove_tree(paths.backup)
    _remove_tree(paths.stage_root)
    paths.marker.unlink()
    _fsync_directory(paths.constant_dir)
