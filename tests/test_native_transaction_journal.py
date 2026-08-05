from __future__ import annotations

import hashlib
import json
import shutil
from pathlib import Path

import pytest

from core.evaluator.native_transaction_journal import (
    advance_journal,
    recover_journal,
    start_journal,
)


def _hash_directory(root: Path) -> dict[str, str]:
    result: dict[str, str] = {}
    for path in sorted(root.iterdir()):
        if path.is_file():
            result[path.name] = hashlib.sha256(path.read_bytes()).hexdigest()
    return result


def _transaction(tmp_path: Path) -> tuple[Path, Path, dict[str, str]]:
    case = tmp_path / "case"
    constant = case / "constant"
    live = constant / "polyMesh"
    live.mkdir(parents=True)
    (live / "points").write_text("baseline\n", encoding="utf-8")
    stage = case / ".native_bl_stage.test"
    candidate = stage / "constant" / "polyMesh"
    candidate.mkdir(parents=True)
    (candidate / "points").write_text("candidate\n", encoding="utf-8")
    journal = case / "native_bl_transaction_journal.json"
    baseline = _hash_directory(live)
    return case, journal, baseline


def test_stage_and_backup_states_restore_baseline(tmp_path: Path) -> None:
    case, journal, baseline = _transaction(tmp_path)
    start_journal(
        journal,
        token="test",
        live="constant/polyMesh",
        stage=".native_bl_stage.test",
        backup="constant/.native_bl_backup.test",
        baseline_hashes=baseline,
    )
    result = recover_journal(case, journal, hash_directory=_hash_directory)
    assert result == {"status": "recovered_baseline", "state": "stage_created"}
    assert _hash_directory(case / "constant/polyMesh") == baseline
    assert not (case / ".native_bl_stage.test").exists()

    case, journal, baseline = _transaction(tmp_path / "second")
    backup = case / "constant/.native_bl_backup.test"
    shutil.move(case / "constant/polyMesh", backup)
    start_journal(
        journal,
        token="test",
        live="constant/polyMesh",
        stage=".native_bl_stage.test",
        backup="constant/.native_bl_backup.test",
        baseline_hashes=baseline,
    )
    advance_journal(journal, "backup_renamed")
    result = recover_journal(case, journal, hash_directory=_hash_directory)
    assert result == {"status": "recovered_baseline", "state": "backup_renamed"}
    assert _hash_directory(case / "constant/polyMesh") == baseline


def test_candidate_state_accepts_only_exact_candidate_or_restores_baseline(tmp_path: Path) -> None:
    case, journal, baseline = _transaction(tmp_path)
    backup = case / "constant/.native_bl_backup.test"
    shutil.move(case / "constant/polyMesh", backup)
    candidate = case / ".native_bl_stage.test/constant/polyMesh"
    shutil.move(candidate, case / "constant/polyMesh")
    candidate_hashes = _hash_directory(case / "constant/polyMesh")
    start_journal(
        journal,
        token="test",
        live="constant/polyMesh",
        stage=".native_bl_stage.test",
        backup="constant/.native_bl_backup.test",
        baseline_hashes=baseline,
    )
    advance_journal(journal, "commit_receipt_published", candidate_hashes=candidate_hashes)
    result = recover_journal(case, journal, hash_directory=_hash_directory)
    assert result == {"status": "recovered_candidate", "state": "commit_receipt_published"}
    assert _hash_directory(case / "constant/polyMesh") == candidate_hashes

    case, journal, baseline = _transaction(tmp_path / "mismatch")
    backup = case / "constant/.native_bl_backup.test"
    shutil.move(case / "constant/polyMesh", backup)
    shutil.move(case / ".native_bl_stage.test/constant/polyMesh", case / "constant/polyMesh")
    start_journal(
        journal,
        token="test",
        live="constant/polyMesh",
        stage=".native_bl_stage.test",
        backup="constant/.native_bl_backup.test",
        baseline_hashes=baseline,
    )
    advance_journal(journal, "candidate_renamed", candidate_hashes={"points": "0" * 64})
    result = recover_journal(case, journal, hash_directory=_hash_directory)
    assert result == {"status": "recovered_baseline", "state": "candidate_renamed"}
    assert _hash_directory(case / "constant/polyMesh") == baseline


def test_invalid_journal_path_is_rejected(tmp_path: Path) -> None:
    case, journal, baseline = _transaction(tmp_path)
    payload = {
        "schema": "autotessell/native-transaction-journal/v1",
        "version": 1,
        "state": "stage_created",
        "live": "../../outside",
        "stage": ".native_bl_stage.test",
        "backup": "constant/.native_bl_backup.test",
        "baseline_hashes": baseline,
        "history": ["stage_created"],
    }
    journal.write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(ValueError, match="path_escape|path_invalid"):
        recover_journal(case, journal, hash_directory=_hash_directory)
