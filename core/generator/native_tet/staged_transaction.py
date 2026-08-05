"""Receipt-route adapter for the durable native transaction journal."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping

from core.evaluator.native_transaction_journal import (
    advance_journal,
    close_journal,
    start_journal,
)


def directory_manifest(root: Path) -> dict[str, str]:
    result: dict[str, str] = {}
    if not root.is_dir():
        return result
    for path in sorted(root.rglob("*")):
        if not path.is_file() or path.is_symlink():
            continue
        result[str(path.relative_to(root))] = hashlib.sha256(path.read_bytes()).hexdigest()
    return result


@dataclass
class StagedTransaction:
    path: Path
    history_path: Path
    root: Path
    destination: Path
    stage: Path

    @classmethod
    def start(
        cls,
        path: str | Path,
        destination: Path,
        stage: Path,
        history_path: str | Path | None = None,
    ) -> "StagedTransaction":
        journal_path = Path(path)
        history = (
            Path(history_path)
            if history_path is not None
            else journal_path.with_name(journal_path.stem + ".history.json")
        )
        start_journal(
            journal_path,
            token=f"{destination.name}:{stage.name}",
            live=destination.name,
            stage=stage.name,
            backup=stage.name,
            baseline_hashes=directory_manifest(destination),
        )
        return cls(journal_path, history, destination.parent, destination, stage)

    def admit(self, candidate: Mapping[str, str]) -> dict[str, Any]:
        return advance_journal(self.path, "candidate_admitted", candidate_hashes=candidate)

    def published(self, candidate: Mapping[str, str], publish: Mapping[str, Any]) -> dict[str, Any]:
        advance_journal(
            self.path,
            "candidate_renamed",
            candidate_hashes=candidate,
            extra={"publish": dict(publish)},
        )
        return advance_journal(self.path, "directory_fsynced")

    def committed(self, extra: Mapping[str, Any] | None = None) -> dict[str, Any] | None:
        advance_journal(self.path, "commit_receipt_published", extra=extra)
        advance_journal(self.path, "backup_retired")
        return close_journal(self.path, history_path=self.history_path)

    def rolled_back(self, extra: Mapping[str, Any] | None = None) -> dict[str, Any] | None:
        payload = dict(extra or {})
        payload["outcome"] = "rolled_back"
        advance_journal(self.path, "backup_retired", extra=payload)
        return close_journal(self.path, history_path=self.history_path)


__all__ = ["StagedTransaction", "directory_manifest"]
