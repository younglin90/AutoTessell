"""Configurable quality-first native-engine campaign matrix.

This module schedules evidence collection; it never substitutes a synthetic
result for a failed mesher.  The runner supplied by the caller is responsible
for invoking the product route and returning an explicit ``accepted`` value.
"""
from __future__ import annotations

import hashlib
import json
from collections.abc import Callable, Iterable, Mapping, Sequence
from typing import Any

SCHEMA = "autotessell/native-quality-campaign-matrix/v1"
DEFAULT_PRODUCTS = (
    "native-tet", "native-hex", "native-poly", "native-tri",
    "strict-quad", "tri-quad",
)
DEFAULT_FIXTURES = ("cube", "sphere", "naca", "complex")
DEFAULT_BOUNDARY_LAYERS = (0, 1, 5)


def _tokens(values: Iterable[str], label: str) -> tuple[str, ...]:
    result = tuple(str(value).strip() for value in values)
    if not result or any(not value for value in result) or len(set(result)) != len(result):
        raise ValueError(f"{label}_invalid")
    return result


def _layers(values: Iterable[int]) -> tuple[int, ...]:
    result = tuple(values)
    if not result or any(isinstance(value, bool) or not isinstance(value, int) or value < 0 for value in result):
        raise ValueError("boundary_layers_invalid")
    if len(set(result)) != len(result):
        raise ValueError("boundary_layers_duplicate")
    return result


def _sha256_json(value: object) -> str:
    payload = json.dumps(value, ensure_ascii=True, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def build_quality_campaign_matrix(
    *,
    products: Sequence[str] = DEFAULT_PRODUCTS,
    fixtures: Sequence[str] = DEFAULT_FIXTURES,
    boundary_layers: Sequence[int] = DEFAULT_BOUNDARY_LAYERS,
    replay_count: int = 3,
) -> dict[str, Any]:
    """Build the complete configurable product/fixture/BL/replay schedule."""
    product_values = _tokens(products, "products")
    fixture_values = _tokens(fixtures, "fixtures")
    layer_values = _layers(boundary_layers)
    if isinstance(replay_count, bool) or not isinstance(replay_count, int) or replay_count < 3:
        raise ValueError("replay_count_must_be_at_least_three")
    rows: list[dict[str, Any]] = []
    for product in product_values:
        for fixture in fixture_values:
            for layers in layer_values:
                for replay_index in range(replay_count):
                    rows.append({
                        "row_id": f"{product}-{fixture}-bl{layers}-r{replay_index}",
                        "product": product,
                        "fixture": fixture,
                        "boundary_layers": layers,
                        "replay_index": replay_index,
                        "quality_first": True,
                        "count_target_secondary": True,
                        "positive_boundary_layer_required": layers > 0,
                    })
    config = {
        "products": list(product_values), "fixtures": list(fixture_values),
        "boundary_layers": list(layer_values), "replay_count": replay_count,
    }
    result: dict[str, Any] = {
        "schema": SCHEMA, "version": 1, "config": config,
        "expected_row_count": len(rows), "rows": rows,
    }
    result["plan_sha256"] = _sha256_json(result)
    return result


def _validate_plan(plan: Mapping[str, Any]) -> list[str]:
    reasons: list[str] = []
    if plan.get("schema") != SCHEMA or plan.get("version") != 1:
        reasons.append("schema")
    rows = plan.get("rows")
    if not isinstance(rows, list):
        return reasons + ["rows"]
    expected = plan.get("expected_row_count")
    if expected != len(rows):
        reasons.append("row_count")
    ids = [row.get("row_id") for row in rows if isinstance(row, Mapping)]
    if len(ids) != len(rows) or len(ids) != len(set(ids)):
        reasons.append("row_ids")
    return reasons


def execute_quality_campaign_matrix(
    plan: Mapping[str, Any],
    runner: Callable[[Mapping[str, Any]], Mapping[str, Any]],
) -> dict[str, Any]:
    """Run every scheduled row and retain explicit failures for every row."""
    reasons = _validate_plan(plan)
    if reasons:
        return {"schema": SCHEMA, "accepted": False, "reasons": sorted(set(reasons)), "rows": []}
    executed: list[dict[str, Any]] = []
    for row in plan["rows"]:
        record: dict[str, Any]
        try:
            raw = runner(dict(row))
            if not isinstance(raw, Mapping):
                record = {"accepted": False, "reasons": ["runner_result_not_object"]}
            else:
                record = dict(raw)
        except Exception as error:  # campaign audit must retain the failed row
            record = {"accepted": False, "reasons": [
                f"runner_exception:{type(error).__name__}:{error}"
            ]}
        accepted = record.get("accepted") is True
        executed.append({
            **dict(row), "status": "passed" if accepted else "failed",
            "result": record,
        })
    passed = sum(row["status"] == "passed" for row in executed)
    return {
        "schema": SCHEMA, "accepted": passed == len(executed),
        "plan_sha256": plan.get("plan_sha256"), "rows": executed,
        "summary": {
            "total": len(executed), "passed": passed,
            "failed": len(executed) - passed,
            "all_passed": passed == len(executed),
        },
    }


__all__ = [
    "SCHEMA", "DEFAULT_PRODUCTS", "DEFAULT_FIXTURES", "DEFAULT_BOUNDARY_LAYERS",
    "build_quality_campaign_matrix", "execute_quality_campaign_matrix",
]
