"""Read-only Chen--Zheng S/Z compatibility ledger.

Chen--Zheng 2006 p.2035 specifies a neighbour-driven rule for a cut facet:
if its opposite neighbour is already decomposed, choose the opposite of that
neighbour's S/Z type; otherwise both are eligible.  This module records that
fact without inventing a tie-breaker, traversing neighbours, or changing a
template/mesh.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

DecompositionType = Literal["S", "Z"]


@dataclass(frozen=True)
class ChenSzChoiceResult:
    """Fail-closed local eligibility report; undecided is not a chosen type."""

    accepted: bool
    reason: str
    eligible_types: frozenset[DecompositionType]
    forced_by_neighbour: bool
    production_mesh_changed: bool


def eligible_sz_types_l0(
    *,
    neighbour_exists: bool,
    neighbour_decomposed: bool,
    neighbour_type: DecompositionType | None,
) -> ChenSzChoiceResult:
    """Apply the literal p.2035 neighbour compatibility rule without tie-breaking."""
    if not neighbour_exists:
        if neighbour_decomposed or neighbour_type is not None:
            return ChenSzChoiceResult(
                False, "invalid_null_neighbour_state", frozenset(), False, False
            )
        return ChenSzChoiceResult(True, "both_types_eligible", frozenset({"S", "Z"}), False, False)
    if not neighbour_decomposed:
        if neighbour_type is not None:
            return ChenSzChoiceResult(
                False, "invalid_undecomposed_neighbour_type", frozenset(), False, False
            )
        return ChenSzChoiceResult(True, "both_types_eligible", frozenset({"S", "Z"}), False, False)
    if neighbour_type is None:
        return ChenSzChoiceResult(
            False, "missing_decomposed_neighbour_type", frozenset(), False, False
        )
    opposite: DecompositionType = "Z" if neighbour_type == "S" else "S"
    return ChenSzChoiceResult(
        True, "opposite_neighbour_type_forced", frozenset({opposite}), True, False
    )
