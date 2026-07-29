"""Exact read-only Chen--Zheng-2006 clusterel-type classifier.

Clusterels are classified by how many of their tetrahedron edges strictly cut
through a missing constraint facet: CO_PLAN, ONE_EDG, TWO_EDG, THR_EDG, or
FOU_EDG.  This wrapper adds the non-degenerate-parent precondition that the
earlier triangle/tet penetration census intentionally left to callers.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from fractions import Fraction
from typing import Literal

from core.generator.native_tet.chen_penetration_l0 import (
    ChenPenetrationClassification,
    classify_constraint_triangle_penetration,
)
from core.generator.native_tet.chen_pipe_cluster_l0 import _orient6, _point

ClusterelType = Literal["CO_PLAN", "ONE_EDG", "TWO_EDG", "THR_EDG", "FOU_EDG"]


@dataclass(frozen=True)
class ChenClusterelTypeResult:
    """Fail-closed clusterel result; ambiguous input has no type."""

    accepted: bool
    reason: str
    clusterel_type: ClusterelType | None
    penetration: ChenPenetrationClassification | None


def classify_clusterel_type(
    tetrahedron: Sequence[Sequence[float | int | Fraction]],
    constraint_triangle: Sequence[Sequence[float | int | Fraction]],
) -> ChenClusterelTypeResult:
    """Classify the five documented clusterel cases without changing a mesh."""
    if len(tetrahedron) != 4:
        raise ValueError("a clusterel requires one tetrahedron")
    rational_tet = tuple(_point(point) for point in tetrahedron)
    if len(set(rational_tet)) != 4 or _orient6(rational_tet, (0, 1, 2, 3)) == 0:
        return ChenClusterelTypeResult(False, "degenerate_clusterel_tetrahedron", None, None)
    penetration = classify_constraint_triangle_penetration(tetrahedron, constraint_triangle)
    if penetration.status == "subface":
        return ChenClusterelTypeResult(True, "accepted", "CO_PLAN", penetration)
    if penetration.status != "unique":
        return ChenClusterelTypeResult(False, penetration.status, None, penetration)
    mapping: dict[int, ClusterelType] = {
        1: "ONE_EDG",
        2: "TWO_EDG",
        3: "THR_EDG",
        4: "FOU_EDG",
    }
    clusterel_type = mapping.get(penetration.n_penetrating_edges)
    if (
        clusterel_type is None
        or len(set(penetration.intersection_points)) != penetration.n_penetrating_edges
    ):
        return ChenClusterelTypeResult(
            False, "invalid_or_duplicate_clusterel_intersections", None, penetration
        )
    return ChenClusterelTypeResult(True, "accepted", clusterel_type, penetration)
