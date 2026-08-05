"""Durable journal and recovery primitives for native directory transactions."""

from __future__ import annotations

import json
import os
import shutil
from pathlib import Path
from typing import Any, Callable, Mapping


SCHEMA = "autotessell/native-transaction-journal/v1"
STATES = (
    "stage_created",
    "candidate_admitted",
    "backup_renamed",
    "candidate_renamed",
    "directory_fsynced",
    "commit_receipt_published",
    "backup_retired",
)
_STATE_SET = frozenset(STATES)


def _fsync_directory(path: Path) -> None:
    descriptor = os.open(path, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0))
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def _write_json(path: Path, payload: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.parent / f".{path.name}.{os.getpid()}.{id(payload)}.tmp"
    try:
        with temporary.open("xb") as stream:
            stream.write(
                json.dumps(payload, ensure_ascii=True, sort_keys=True, separators=(",", ":")).encode("utf-8")
            )
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
        _fsync_directory(path.parent)
    finally:
        if temporary.exists():
            temporary.unlink()


def start_journal(
    path: str | Path,
    *,
    token: str,
    live: str,
    stage: str,
    backup: str,
    baseline_hashes: Mapping[str, str],
) -> dict[str, Any]:
    payload = {
        "schema": SCHEMA,
        "version": 1,
        "token": str(token),
        "state": "stage_created",
        "live": str(live),
        "stage": str(stage),
        "backup": str(backup),
        "baseline_hashes": dict(baseline_hashes),
        "candidate_hashes": None,
        "history": ["stage_created"],
    }
    _write_json(Path(path), payload)
    return payload


def advance_journal(
    path: str | Path,
    state: str,
    *,
    candidate_hashes: Mapping[str, str] | None = None,
    extra: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    if state not in _STATE_SET:
        raise ValueError(f"invalid_transaction_journal_state:{state}")
    journal_path = Path(path)
    payload = json.loads(journal_path.read_text(encoding="utf-8"))
    if payload.get("schema") != SCHEMA or payload.get("state") not in _STATE_SET:
        raise ValueError("invalid_transaction_journal")
    history = list(payload.get("history", ()))
    if not history or history[-1] != state:
        history.append(state)
    payload["state"] = state
    payload["history"] = history
    if candidate_hashes is not None:
        payload["candidate_hashes"] = dict(candidate_hashes)
    if extra:
        payload.update(dict(extra))
    _write_json(journal_path, payload)
    return payload


def read_journal(path: str | Path) -> dict[str, Any] | None:
    journal_path = Path(path)
    if not journal_path.exists():
        return None
    payload = json.loads(journal_path.read_text(encoding="utf-8"))
    if payload.get("schema") != SCHEMA or payload.get("state") not in _STATE_SET:
        raise ValueError("invalid_transaction_journal")
    return payload


def close_journal(path: str | Path, *, history_path: str | Path | None = None) -> dict[str, Any] | None:
    journal_path = Path(path)
    payload = read_journal(journal_path)
    if payload is None:
        return None
    if payload.get("state") != "backup_retired":
        raise ValueError("transaction_journal_not_retired")
    if history_path is not None:
        history_payload = dict(payload)
        history_payload["closed"] = True
        _write_json(Path(history_path), history_payload)
    journal_path.unlink()
    _fsync_directory(journal_path.parent)
    return payload


def failpoint(state: str) -> None:
    """Test-only exception injection; unset in every normal production run."""
    if os.environ.get("AUTO_TESSELL_NATIVE_TX_FAIL_AFTER", "") == state:
        raise RuntimeError(f"injected_transaction_failpoint:{state}")


def _safe_child(case_root: Path, relative: str) -> Path:
    if not isinstance(relative, str) or not relative or Path(relative).is_absolute():
        raise ValueError("transaction_journal_path_invalid")
    path = (case_root / relative).resolve(strict=False)
    if case_root.resolve() not in path.parents and path != case_root.resolve():
        raise ValueError("transaction_journal_path_escape")
    return path


def recover_journal(
    case_root: str | Path,
    journal_path: str | Path,
    *,
    hash_directory: Callable[[Path], Mapping[str, str]],
) -> dict[str, Any] | None:
    """Recover a transaction to baseline or verified candidate, never mixed."""
    root = Path(case_root).resolve()
    payload = read_journal(journal_path)
    if payload is None:
        return None
    live = _safe_child(root, payload["live"])
    stage = _safe_child(root, payload["stage"])
    backup = _safe_child(root, payload["backup"])
    baseline = dict(payload.get("baseline_hashes") or {})
    candidate = payload.get("candidate_hashes")
    state = payload["state"]

    def hashes(path: Path) -> Mapping[str, str] | None:
        if not path.is_dir() or path.is_symlink():
            return None
        return hash_directory(path)

    live_hashes = hashes(live)
    backup_hashes = hashes(backup)
    candidate_hashes = dict(candidate) if isinstance(candidate, Mapping) else None

    # Before candidate rename, the live directory is still authoritative.
    if state in {"stage_created", "candidate_admitted", "backup_renamed"}:
        if backup_hashes == baseline and live_hashes != baseline:
            if live.exists():
                shutil.rmtree(live)
            os.replace(backup, live)
        elif backup.exists() and live_hashes == baseline:
            shutil.rmtree(backup)
        elif backup.exists() and live_hashes is None:
            os.replace(backup, live)
        elif backup.exists() and backup_hashes != baseline:
            raise ValueError("transaction_recovery_baseline_hash_mismatch")
        if stage.exists():
            shutil.rmtree(stage)
        _write_json(Path(journal_path), {**payload, "recovered": "baseline", "state": "backup_retired"})
        Path(journal_path).unlink()
        _fsync_directory(Path(journal_path).parent)
        return {"status": "recovered_baseline", "state": state}

    # Once candidate was renamed, accept it only if its complete locked mesh
    # hashes match the admitted candidate. Otherwise restore the baseline.
    if state in {"candidate_renamed", "directory_fsynced", "commit_receipt_published", "backup_retired"}:
        if live_hashes == baseline:
            if backup.exists():
                shutil.rmtree(backup)
            if stage.exists():
                shutil.rmtree(stage)
            Path(journal_path).unlink()
            _fsync_directory(Path(journal_path).parent)
            return {"status": "recovered_baseline", "state": state}
        if state in {"candidate_renamed", "directory_fsynced"}:
            if backup_hashes == baseline:
                if live.exists():
                    shutil.rmtree(live)
                os.replace(backup, live)
                if stage.exists():
                    shutil.rmtree(stage)
                Path(journal_path).unlink()
                _fsync_directory(Path(journal_path).parent)
                return {"status": "recovered_baseline", "state": state}
            raise ValueError("transaction_recovery_candidate_not_fsynced")
        if candidate_hashes is not None and live_hashes == candidate_hashes:
            if backup.exists():
                shutil.rmtree(backup)
            if stage.exists():
                shutil.rmtree(stage)
            Path(journal_path).unlink()
            _fsync_directory(Path(journal_path).parent)
            return {"status": "recovered_candidate", "state": state}
        if backup_hashes == baseline:
            if live.exists():
                shutil.rmtree(live)
            os.replace(backup, live)
            if stage.exists():
                shutil.rmtree(stage)
            Path(journal_path).unlink()
            _fsync_directory(Path(journal_path).parent)
            return {"status": "recovered_baseline", "state": state}
        raise ValueError("transaction_recovery_no_verified_generation")
    raise ValueError("transaction_recovery_state_unknown")


__all__ = [
    "SCHEMA",
    "STATES",
    "advance_journal",
    "close_journal",
    "failpoint",
    "read_journal",
    "recover_journal",
    "start_journal",
]
