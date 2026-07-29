"""L1 exact binding of a finite source triangle to no-H Table-11 THR_EDG rows.

The Table-11 certificates use names P1/P2/P3. This report-only adapter derives
those points from a real finite source triangle and one parent tetrahedron,
requiring the documented AD, BD, CD cut-edge order before exposing either
literal no-H candidate. It does not select S/Z, traverse Phi neighbours, or
modify a recovery mesh.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from fractions import Fraction
from typing import Literal

from core.generator.native_tet.chen_clusterel_type_l0 import classify_clusterel_type
from core.generator.native_tet.chen_thr_edg_table11_l0 import (
    ChenThrEdgS2Z1Result,
    certify_thr_edg_s1_z2_table11_l0,
    certify_thr_edg_s2_z1_table11_l0,
)

NoHTable11Subcase = Literal["S2/Z1", "S1/Z2"]


@dataclass(frozen=True)
class ChenThrEdgSourceMatchResult:
    """Fail-closed source-to-table match; rejection exposes no candidate."""

    accepted: bool
    reason: str
    subcase: NoHTable11Subcase | None
    candidate: ChenThrEdgS2Z1Result | None
    source_points_unchanged: bool
    production_mesh_changed: bool


def certify_thr_edg_source_match_l1(
    tetrahedron: Sequence[Sequence[float | int | Fraction]],
    source_triangle: Sequence[Sequence[float | int | Fraction]],
    *,
    subcase: NoHTable11Subcase,
) -> ChenThrEdgSourceMatchResult:
    """Match finite THR_EDG geometry to one literal no-H row, without choosing it."""
    if len(tetrahedron) != 4:
        raise ValueError("a THR_EDG parent requires exactly four tetrahedron points")
    before_tet = tuple(tuple(point) for point in tetrahedron)
    before_triangle = tuple(tuple(point) for point in source_triangle)
    classification = classify_clusterel_type(before_tet, before_triangle)
    if (
        not classification.accepted
        or classification.clusterel_type != "THR_EDG"
        or classification.penetration is None
        or classification.penetration.penetrating_edges != ((0, 3), (1, 3), (2, 3))
        or len(classification.penetration.intersection_points) != 3
    ):
        return ChenThrEdgSourceMatchResult(
            False,
            "reject_clusterel_not_documented_ad_bd_cd_thr_edg",
            None,
            None,
            tuple(tuple(point) for point in tetrahedron) == before_tet
            and tuple(tuple(point) for point in source_triangle) == before_triangle,
            False,
        )
    p1, p2, p3 = classification.penetration.intersection_points
    points_by_label = {
        "A": before_tet[0],
        "B": before_tet[1],
        "C": before_tet[2],
        "D": before_tet[3],
        "P1": p1,
        "P2": p2,
        "P3": p3,
    }
    candidate = (
        certify_thr_edg_s2_z1_table11_l0(points_by_label)
        if subcase == "S2/Z1"
        else certify_thr_edg_s1_z2_table11_l0(points_by_label)
    )
    unchanged = bool(
        tuple(tuple(point) for point in tetrahedron) == before_tet
        and tuple(tuple(point) for point in source_triangle) == before_triangle
    )
    return ChenThrEdgSourceMatchResult(
        candidate.accepted and unchanged,
        "accepted" if candidate.accepted and unchanged else "reject_literal_table11_candidate",
        subcase if candidate.accepted and unchanged else None,
        candidate if candidate.accepted and unchanged else None,
        unchanged,
        False,
    )
