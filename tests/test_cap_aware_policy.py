"""Focused tests for deterministic hard-cap policy primitives."""

from __future__ import annotations

import math

import pytest

from core.cap_aware_policy import (
    choose_best_within_max_cells,
    is_safety_eligible,
    recommend_cell_budget,
)


def test_safety_eligibility_requires_safety_and_hard_cap() -> None:
    assert is_safety_eligible(cell_count=100, safety_passed=True, max_cells=100)
    assert not is_safety_eligible(cell_count=101, safety_passed=True, max_cells=100)
    assert not is_safety_eligible(cell_count=10, safety_passed=False, max_cells=100)


def test_target_is_not_an_eligibility_gate() -> None:
    assert is_safety_eligible(cell_count=10, safety_passed=True, max_cells=10)


def test_selection_excludes_unsafe_and_over_cap_candidates() -> None:
    candidates = [
        {"name": "unsafe", "cells": 60, "score": 100.0, "safe": False},
        {"name": "over-cap", "cells": 120, "score": 99.0, "safe": True},
        {"name": "selected", "cells": 90, "score": 4.0, "safe": True},
    ]

    selected = choose_best_within_max_cells(
        candidates,
        cell_count=lambda item: item["cells"],
        quality_score=lambda item: item["score"],
        safety_passed=lambda item: item["safe"],
        max_cells=100,
    )

    assert selected is candidates[2]


def test_selection_tie_breaks_by_lower_cell_count_then_input_order() -> None:
    candidates = [
        {"name": "first", "cells": 80, "score": 1.0, "safe": True},
        {"name": "smaller", "cells": 40, "score": 1.0, "safe": True},
        {"name": "same-as-smaller", "cells": 40, "score": 1.0, "safe": True},
    ]

    selected = choose_best_within_max_cells(
        candidates,
        cell_count=lambda item: item["cells"],
        quality_score=lambda item: item["score"],
        safety_passed=lambda item: item["safe"],
    )

    assert selected is candidates[1]


def test_selection_skips_non_finite_scores() -> None:
    candidates = [
        {"name": "nan", "cells": 10, "score": math.nan, "safe": True},
        {"name": "valid", "cells": 11, "score": 1.0, "safe": True},
    ]

    selected = choose_best_within_max_cells(
        candidates,
        cell_count=lambda item: item["cells"],
        quality_score=lambda item: item["score"],
        safety_passed=lambda item: item["safe"],
    )

    assert selected is candidates[1]


def test_recommendation_has_no_warning_when_cap_satisfies_target() -> None:
    recommendation = recommend_cell_budget(
        minimum_safe_cells=100,
        target_cells=200,
        max_cells=250,
    )

    assert recommendation.recommended_min_cells == 100
    assert recommendation.recommended_target_cells == 200
    assert recommendation.safety_feasible
    assert recommendation.target_within_cap
    assert recommendation.warning is None


def test_recommendation_warns_when_cap_misses_soft_target() -> None:
    recommendation = recommend_cell_budget(
        minimum_safe_cells=100,
        target_cells=200,
        max_cells=150,
    )

    assert recommendation.safety_feasible
    assert not recommendation.target_within_cap
    assert recommendation.warning == (
        "max_cells=150 is below the recommended target of 200; output remains "
        "hard-capped and may be coarser."
    )


def test_recommendation_prioritizes_safety_floor_warning() -> None:
    recommendation = recommend_cell_budget(
        minimum_safe_cells=100,
        target_cells=200,
        max_cells=99,
    )

    assert not recommendation.safety_feasible
    assert not recommendation.target_within_cap
    assert recommendation.warning == (
        "max_cells=99 is below the recommended safety minimum of 100; increase "
        "max_cells to at least 100."
    )


@pytest.mark.parametrize("bad_value", [0, -1, True, 1.5])
def test_invalid_cell_counts_are_rejected(bad_value: object) -> None:
    with pytest.raises(ValueError):
        recommend_cell_budget(minimum_safe_cells=100, max_cells=bad_value)  # type: ignore[arg-type]
