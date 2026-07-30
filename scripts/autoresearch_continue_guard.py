#!/usr/bin/env python3
"""Refuse campaign termination until the local release ledger is mechanically ready."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
LEDGER = ROOT / "docs" / "qa" / "continuous_release_campaign.md"


def git(*args: str) -> str:
    return subprocess.check_output(["git", *args], cwd=ROOT, text=True).strip()


def latest_gate_statuses(text: str) -> list[str]:
    """Return statuses from the latest ledger gate table, never historical tables."""
    latest: list[str] = []
    current: list[str] | None = None
    for line in text.splitlines():
        fields = [field.strip() for field in line.split("|")]
        if len(fields) < 4:
            continue
        if fields[1] == "Gate" and fields[2] == "Status":
            current = []
            continue
        if current is not None and fields[1][:1].isdigit():
            current.append(fields[2])
            latest = current
    return latest


def main() -> int:
    reasons: list[str] = []
    if not LEDGER.is_file():
        reasons.append("campaign ledger missing")
    else:
        text = LEDGER.read_text(encoding="utf-8")
        if "state: `RELEASE_READY`" not in text:
            reasons.append("campaign state is not RELEASE_READY")
        statuses = latest_gate_statuses(text)
        if not statuses:
            reasons.append("current release gate table missing")
        non_pass = [status for status in statuses if status != "PASS"]
        if non_pass:
            reasons.append("release gates not all PASS: " + ", ".join(non_pass))
    if git("branch", "--show-current") != "master":
        reasons.append("current branch is not master")
    if git("status", "--porcelain"):
        reasons.append("working tree is not clean")
    worktrees = [line for line in git("worktree", "list", "--porcelain").splitlines() if line.startswith("worktree ")]
    if len(worktrees) != 1:
        reasons.append("research worktrees remain")
    print(json.dumps({"allowed_to_stop": not reasons, "reasons": reasons}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
