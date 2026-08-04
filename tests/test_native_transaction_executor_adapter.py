from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from core.evaluator.native_transaction_executor import (  # noqa: E402
    begin_authoritative_transaction,
    publish_authoritative_transaction,
    run_authoritative_writer_transaction,
    validate_persisted_reread,
    validate_staged_candidate,
)
from test_native_transaction_executor_v1_cpp23 import (  # noqa: E402
    _authority,
    _candidate,
    _corridor,
    _disk,
    _intent,
)
import native_transaction_executor  # noqa: E402


def test_adapter_transports_bl0_without_defaults_or_writer_work() -> None:
    transaction = begin_authoritative_transaction(_intent(0, 201), _authority())
    assert transaction["accepted"] is True, transaction
    candidate = _candidate(transaction, 0)
    staged = validate_staged_candidate(transaction, candidate)
    assert staged["accepted"] is True, staged
    reread = validate_persisted_reread(staged, _disk(candidate))
    assert reread["accepted"] is True, reread
    published = publish_authoritative_transaction(reread)
    assert published["published"] is True
    assert published["generated_entity_count"] == 2


def test_adapter_transports_bl1_and_preserves_corridor_receipt() -> None:
    corridor = _corridor(1)
    transaction = begin_authoritative_transaction(_intent(1, 202), _authority(), corridor)
    assert transaction["accepted"] is True, transaction
    assert transaction["corridor_receipt_sha256"] == corridor["receipt_sha256"]
    candidate = _candidate(transaction, 1)
    staged = validate_staged_candidate(transaction, candidate)
    assert staged["accepted"] is True, staged
    reread = validate_persisted_reread(staged, _disk(candidate))
    assert reread["accepted"] is True, reread
    assert publish_authoritative_transaction(reread)["published"] is True


def test_adapter_does_not_hide_corridor_or_candidate_mutation() -> None:
    corridor = _corridor(1)
    corridor["actual_layers"] = 2
    refused = begin_authoritative_transaction(_intent(1, 203), _authority(), corridor)
    assert refused["accepted"] is False
    assert refused["reason"] == "executor_positive_bl_corridor_missing"

    transaction = begin_authoritative_transaction(_intent(0, 204), _authority())
    candidate = _candidate(transaction, 0)
    candidate["quality"]["skewness_max"] = 0.5
    candidate["artifact_sha256"] = native_transaction_executor.canonical_artifact_sha256_v1(candidate)["sha256"]
    refused_candidate = validate_staged_candidate(transaction, candidate)
    assert refused_candidate["accepted"] is True, refused_candidate
    tampered = _disk(candidate)
    tampered["published"] = True
    tampered["artifact_sha256"] = native_transaction_executor.canonical_artifact_sha256_v1(tampered)["sha256"]
    refused_disk = validate_persisted_reread(refused_candidate, tampered)
    assert refused_disk["accepted"] is False


def test_adapter_transports_actual_writer_and_reread_callbacks() -> None:
    transaction = begin_authoritative_transaction(_intent(0, 205), _authority())
    assert transaction["accepted"] is True, transaction
    candidate = _candidate(transaction, 0)
    disk = _disk(candidate)
    published = run_authoritative_writer_transaction(transaction, lambda _: candidate, lambda _: disk)
    assert published["published"] is True
    assert published["transaction_state"] == "published"
