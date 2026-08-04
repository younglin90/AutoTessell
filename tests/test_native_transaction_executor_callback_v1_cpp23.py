from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent))
from test_native_transaction_executor_v1_cpp23 import (  # noqa: E402
    _authority,
    _candidate,
    _corridor,
    _disk,
    _intent,
    executor,
)


def test_cpp_callback_boundary_runs_real_writer_and_reread_sequence() -> None:
    transaction = executor.begin_transaction_v1(_intent(0, 301), _authority(), None)
    assert transaction["accepted"] is True, transaction
    candidate = _candidate(transaction, 0)
    disk = _disk(candidate)
    calls: list[str] = []

    def writer(value: dict[str, object]) -> dict[str, object]:
        calls.append(value["transaction_state"])
        return candidate

    def reread(value: dict[str, object]) -> dict[str, object]:
        calls.append(value["transaction_state"])
        return disk

    published = executor.run_writer_transaction_v1(transaction, writer, reread)
    assert published["accepted"] is True, published
    assert published["transaction_state"] == "published"
    assert published["published"] is True
    assert calls == ["staging", "candidate_validated"]


def test_cpp_callback_exception_returns_atomic_rollback() -> None:
    transaction = executor.begin_transaction_v1(_intent(0, 302), _authority(), None)
    assert transaction["accepted"] is True, transaction

    def writer(_: dict[str, object]) -> dict[str, object]:
        raise RuntimeError("writer_failed")

    refused = executor.run_writer_transaction_v1(transaction, writer, lambda _: {})
    assert refused["accepted"] is True, refused
    assert refused["transaction_state"] == "rolled_back"
    assert refused["candidate_discarded"] is True
    assert refused["rollback_reason"] == "executor_writer_callback_exception"


def test_cpp_callback_reread_tamper_stops_before_publish() -> None:
    transaction = executor.begin_transaction_v1(_intent(0, 303), _authority(), None)
    assert transaction["accepted"] is True, transaction
    candidate = _candidate(transaction, 0)
    disk = _disk(candidate)
    disk["entity_uids"] = ["cell-0", "face-tampered"]
    disk["artifact_sha256"] = executor.canonical_artifact_sha256_v1(disk)["sha256"]
    refused = executor.run_writer_transaction_v1(transaction, lambda _: candidate, lambda _: disk)
    assert refused["accepted"] is False
    assert refused["reason"] == "executor_feature_patch_group_component_lost"
    assert refused["published"] is False
