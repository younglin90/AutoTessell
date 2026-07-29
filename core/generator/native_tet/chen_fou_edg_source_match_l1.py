"""L1 finite-source binding for Chen--Zheng Table-12 FOU_EDG SSSS.

The literal row is exposed only after the exact finite-triangle classifier
finds all four documented intersections.  No mixed S/Z choice, H placement,
neighbour update, cavity transaction, or CDT mutation is performed here.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from fractions import Fraction

from core.generator.native_tet.chen_clusterel_type_l0 import classify_clusterel_type
from core.generator.native_tet.chen_fou_edg_table12_l0 import (
    ChenFouEdgSsssResult,
    certify_fou_edg_ssss_table12_l0,
)

_DOCUMENTED_FOU_EDGES = ((0, 2), (0, 3), (1, 2), (1, 3))


@dataclass(frozen=True)
class ChenFouEdgSourceMatchResult:
    """Fail-closed finite-source match; rejection exposes no template candidate."""

    accepted: bool
    reason: str
    candidate: ChenFouEdgSsssResult | None
    source_points_unchanged: bool
    production_mesh_changed: bool


def certify_fou_edg_source_match_l1(
    tetrahedron: Sequence[Sequence[float | int | Fraction]],
    source_triangle: Sequence[Sequence[float | int | Fraction]],
) -> ChenFouEdgSourceMatchResult:
    """Bind a finite FOU_EDG cut to Table-12 SSSS's documented point order."""
    if len(tetrahedron) != 4:
        raise ValueError("a FOU_EDG parent requires exactly four tetrahedron points")
    before_tet = tuple(tuple(point) for point in tetrahedron)
    before_triangle = tuple(tuple(point) for point in source_triangle)
    classification = classify_clusterel_type(before_tet, before_triangle)
    if (
        not classification.accepted
        or classification.clusterel_type != "FOU_EDG"
        or classification.penetration is None
        or classification.penetration.penetrating_edges != _DOCUMENTED_FOU_EDGES
        or len(classification.penetration.intersection_points) != 4
    ):
        return ChenFouEdgSourceMatchResult(
            False,
            "reject_clusterel_not_documented_ac_ad_bc_bd_fou_edg",
            None,
            tuple(tuple(point) for point in tetrahedron) == before_tet
            and tuple(tuple(point) for point in source_triangle) == before_triangle,
            False,
        )
    intersections = dict(
        zip(
            classification.penetration.penetrating_edges,
            classification.penetration.intersection_points,
            strict=True,
        )
    )
    candidate = certify_fou_edg_ssss_table12_l0(
        {
            "A": before_tet[0],
            "B": before_tet[1],
            "C": before_tet[2],
            "D": before_tet[3],
            "P1": intersections[(0, 3)],
            "P2": intersections[(1, 3)],
            "P3": intersections[(1, 2)],
            "P4": intersections[(0, 2)],
        }
    )
    unchanged = bool(
        tuple(tuple(point) for point in tetrahedron) == before_tet
        and tuple(tuple(point) for point in source_triangle) == before_triangle
    )
    return ChenFouEdgSourceMatchResult(
        candidate.accepted and unchanged,
        "accepted" if candidate.accepted and unchanged else "reject_literal_table12_candidate",
        candidate if candidate.accepted and unchanged else None,
        unchanged,
        False,
    )
