from __future__ import annotations

from scripts.native_bounded_corpus_runner import aggregate_status


def test_timeout_is_not_aggregated_as_pass():
    assert aggregate_status([{"status": "pass"}, {"status": "no_conclusion"}]) == "has_no_conclusion"


def test_failure_is_distinct_from_no_conclusion():
    assert aggregate_status([{"status": "pass"}, {"status": "fail"}]) == "has_failures"


def test_all_pass_is_bounded_only_not_release_claim():
    assert aggregate_status([{"status": "pass"}, {"status": "pass"}]) == "all_bounded_nodes_passed"
