from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

from core.generator.native_tet.staged_runner import run_tet_in_private_stage


def _runner(_vertices: object, _faces: object, stage: Path, **_kwargs: object) -> SimpleNamespace:
    (stage / "mesh").write_text("candidate", encoding="utf-8")
    return SimpleNamespace(success=True)


def _run(tmp_path: Path, post_audit):
    destination = tmp_path / "case"
    destination.mkdir()
    (destination / "old").write_text("baseline", encoding="utf-8")
    return run_tet_in_private_stage(
        _runner,
        [],
        [],
        destination,
        audit_callback=lambda _stage: {"accepted": True},
        post_publish_audit_callback=post_audit,
        journal_path=tmp_path / "journal.json",
        journal_history_path=tmp_path / "history.json",
    ), destination


def test_transaction_commit_closes_journal_and_retires_backup(tmp_path: Path) -> None:
    result, destination = _run(tmp_path, lambda _destination: {"accepted": True})

    assert result.published is True
    assert (destination / "mesh").read_text(encoding="utf-8") == "candidate"
    assert not (tmp_path / "journal.json").exists()
    history = json.loads((tmp_path / "history.json").read_text(encoding="utf-8"))
    assert history["state"] == "backup_retired"
    assert history["closed"] is True
    assert "candidate_admitted" in history["history"]
    assert "candidate_renamed" in history["history"]
    assert "directory_fsynced" in history["history"]
    assert "commit_receipt_published" in history["history"]
    assert history["history"][-1] == "backup_retired"
    assert not Path(result.publish["rollback_backup"]).exists()


def test_transaction_refusal_restores_baseline_and_closes_journal(tmp_path: Path) -> None:
    result, destination = _run(
        tmp_path,
        lambda _destination: {"accepted": False, "reason": "destination_quality_refused"},
    )

    assert result.published is False
    assert result.refused_reason == "destination_quality_refused"
    assert (destination / "old").read_text(encoding="utf-8") == "baseline"
    assert not (destination / "mesh").exists()
    assert not (tmp_path / "journal.json").exists()
    history = json.loads((tmp_path / "history.json").read_text(encoding="utf-8"))
    assert history["state"] == "backup_retired"
    assert history["outcome"] == "rolled_back"
    assert history["closed"] is True


def test_transaction_refuses_destination_manifest_tamper_and_restores_baseline(
    tmp_path: Path,
) -> None:
    def tampering_audit(destination: Path) -> dict[str, object]:
        (destination / "tampered-after-audit").write_text("tamper", encoding="utf-8")
        return {"accepted": True}

    result, destination = _run(tmp_path, tampering_audit)

    assert result.published is False
    assert result.refused_reason == "destination_manifest_mismatch"
    assert result.destination_audit["reason"] == "destination_manifest_mismatch"
    assert (destination / "old").read_text(encoding="utf-8") == "baseline"
    assert not (destination / "mesh").exists()
    assert not (destination / "tampered-after-audit").exists()
    assert not (tmp_path / "journal.json").exists()


def test_transaction_requires_destination_audit_before_publish(tmp_path: Path) -> None:
    destination = tmp_path / "case"
    destination.mkdir()
    (destination / "old").write_text("baseline", encoding="utf-8")
    result = run_tet_in_private_stage(
        _runner,
        [],
        [],
        destination,
        audit_callback=lambda _stage: {"accepted": True},
        journal_path=tmp_path / "journal.json",
        journal_history_path=tmp_path / "history.json",
    )

    assert result.published is False
    assert result.refused_reason == "destination_audit_missing"
    assert (destination / "old").read_text(encoding="utf-8") == "baseline"
    assert not (destination / "mesh").exists()
    assert not (tmp_path / "journal.json").exists()
