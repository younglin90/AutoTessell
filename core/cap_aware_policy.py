"""Deterministic hard-cap and soft-target policy helpers for volume engines.

``max_cells`` is a hard resource limit: an over-cap candidate is never
eligible.  ``target_cells`` only expresses the preferred resolution and is
used for recommendations, never to reject an otherwise safe candidate.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable
from dataclasses import dataclass
from math import isfinite
from typing import TypeVar


CandidateT = TypeVar("CandidateT")


@dataclass(frozen=True, slots=True)
class CapRecommendation:
    """Resolution advice derived from a safety floor and user cell settings."""

    max_cells: int | None
    target_cells: int | None
    recommended_min_cells: int
    recommended_target_cells: int
    safety_feasible: bool
    target_within_cap: bool
    warning: str | None


def _validate_optional_cell_count(value: int | None, name: str) -> int | None:
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, int) or value < 1:
        raise ValueError(f"{name} must be a positive integer or None")
    return value


def _validate_cell_count(value: int, name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ValueError(f"{name} must be a non-negative integer")
    return value


def is_safety_eligible(
    *,
    cell_count: int,
    safety_passed: bool,
    max_cells: int | None = None,
) -> bool:
    """Return whether a candidate passes safety and the hard cell cap.

    The target is deliberately absent: it is a resolution preference, not an
    eligibility gate.
    """
    checked_count = _validate_cell_count(cell_count, "cell_count")
    checked_cap = _validate_optional_cell_count(max_cells, "max_cells")
    return bool(safety_passed) and (
        checked_cap is None or checked_count <= checked_cap
    )


def choose_best_within_max_cells(
    candidates: Iterable[CandidateT],
    *,
    cell_count: Callable[[CandidateT], int],
    quality_score: Callable[[CandidateT], float],
    safety_passed: Callable[[CandidateT], bool],
    max_cells: int | None = None,
) -> CandidateT | None:
    """Choose the highest-quality safe candidate that respects ``max_cells``.

    Ties are resolved by lower cell count and then original iterable order,
    keeping decisions reproducible across runs.  A non-finite quality score is
    not a valid candidate because it cannot be compared safely.
    """
    checked_cap = _validate_optional_cell_count(max_cells, "max_cells")
    best: CandidateT | None = None
    best_score: float | None = None
    best_cells: int | None = None

    for candidate in candidates:
        candidate_cells = _validate_cell_count(cell_count(candidate), "cell_count")
        if not is_safety_eligible(
            cell_count=candidate_cells,
            safety_passed=safety_passed(candidate),
            max_cells=checked_cap,
        ):
            continue

        candidate_score = float(quality_score(candidate))
        if not isfinite(candidate_score):
            continue

        if (
            best is None
            or candidate_score > best_score  # type: ignore[operator]
            or (
                candidate_score == best_score
                and candidate_cells < best_cells  # type: ignore[operator]
            )
        ):
            best = candidate
            best_score = candidate_score
            best_cells = candidate_cells

    return best


def recommend_cell_budget(
    *,
    minimum_safe_cells: int,
    target_cells: int | None = None,
    max_cells: int | None = None,
) -> CapRecommendation:
    """Return cap advice without weakening the hard ``max_cells`` constraint.

    ``minimum_safe_cells`` is the engine's estimated floor for a safe mesh.
    The recommendation preserves a larger user soft target, but reports when
    the hard cap makes that target—or safety itself—unattainable.
    """
    checked_minimum = _validate_optional_cell_count(
        minimum_safe_cells, "minimum_safe_cells"
    )
    # ``minimum_safe_cells`` is non-optional at the public boundary.
    assert checked_minimum is not None
    checked_target = _validate_optional_cell_count(target_cells, "target_cells")
    checked_cap = _validate_optional_cell_count(max_cells, "max_cells")
    recommended_target = max(checked_minimum, checked_target or checked_minimum)
    safety_feasible = checked_cap is None or checked_cap >= checked_minimum
    target_within_cap = checked_cap is None or checked_cap >= recommended_target

    warning: str | None = None
    if not safety_feasible:
        warning = (
            f"max_cells={checked_cap} is below the recommended safety minimum "
            f"of {checked_minimum}; increase max_cells to at least "
            f"{checked_minimum}."
        )
    elif not target_within_cap:
        warning = (
            f"max_cells={checked_cap} is below the recommended target of "
            f"{recommended_target}; output remains hard-capped and may be coarser."
        )

    return CapRecommendation(
        max_cells=checked_cap,
        target_cells=checked_target,
        recommended_min_cells=checked_minimum,
        recommended_target_cells=recommended_target,
        safety_feasible=safety_feasible,
        target_within_cap=target_within_cap,
        warning=warning,
    )
