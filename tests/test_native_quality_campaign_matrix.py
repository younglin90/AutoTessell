from __future__ import annotations

import pytest

from core.evaluator.native_quality_campaign_matrix import (
    DEFAULT_PRODUCTS,
    build_quality_campaign_matrix,
    execute_quality_campaign_matrix,
)


def test_default_matrix_has_all_products_shapes_layers_and_replays():
    plan = build_quality_campaign_matrix()
    assert plan["expected_row_count"] == 216
    assert len(plan["rows"]) == 216
    assert {row["product"] for row in plan["rows"]} == set(DEFAULT_PRODUCTS)
    assert {row["boundary_layers"] for row in plan["rows"]} == {0, 1, 5}
    assert {row["replay_index"] for row in plan["rows"]} == {0, 1, 2}
    assert all(row["quality_first"] and row["count_target_secondary"] for row in plan["rows"])
    assert sum(row["positive_boundary_layer_required"] for row in plan["rows"]) == 144


def test_matrix_is_configurable_and_replay_count_remains_at_least_three():
    plan = build_quality_campaign_matrix(
        products=("native-tet",), fixtures=("cube", "naca"),
        boundary_layers=(0, 2), replay_count=4,
    )
    assert plan["expected_row_count"] == 16
    assert plan["config"]["boundary_layers"] == [0, 2]
    assert {row["replay_index"] for row in plan["rows"]} == {0, 1, 2, 3}
    with pytest.raises(ValueError, match="replay_count"):
        build_quality_campaign_matrix(replay_count=2)
    with pytest.raises(ValueError, match="boundary_layers"):
        build_quality_campaign_matrix(boundary_layers=(1, 1))


def test_executor_retains_failed_rows_without_promoting_them():
    plan = build_quality_campaign_matrix(
        products=("native-tet",), fixtures=("cube",), boundary_layers=(0,), replay_count=3,
    )

    def runner(row):
        return {"accepted": row["replay_index"] != 1,
                "reasons": [] if row["replay_index"] != 1 else ["quality_gate"]}

    result = execute_quality_campaign_matrix(plan, runner)
    assert result["accepted"] is False
    assert result["summary"] == {"total": 3, "passed": 2, "failed": 1, "all_passed": False}
    assert [row["status"] for row in result["rows"]] == ["passed", "failed", "passed"]


def test_executor_records_runner_exceptions_as_failed_rows():
    plan = build_quality_campaign_matrix(
        products=("native-tet",), fixtures=("cube",), boundary_layers=(1,), replay_count=3,
    )

    def runner(row):
        if row["replay_index"] == 2:
            raise RuntimeError("mesher unavailable")
        return {"accepted": True}

    result = execute_quality_campaign_matrix(plan, runner)
    assert result["summary"]["failed"] == 1
    assert result["rows"][2]["result"]["reasons"][0].startswith("runner_exception:RuntimeError:")
