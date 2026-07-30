from __future__ import annotations

from scripts.autoresearch_continue_guard import latest_gate_statuses


def test_latest_gate_statuses_ignores_historical_checkpoint() -> None:
    ledger = """
| Gate | Status | Evidence |
|---|---|---|
| 1 Repository | FAIL | old |
| 2 Build | UNVERIFIED | old |

| Gate | Status | Evidence |
|---|---|---|
| 1 Repository | PASS | current |
| 2 Build | PASS | current |
"""
    assert latest_gate_statuses(ledger) == ["PASS", "PASS"]


def test_latest_gate_statuses_returns_empty_without_gate_table() -> None:
    assert latest_gate_statuses("# no gates") == []
