"""Fail-closed complete-cavity binding for documented Chen template plans.

The explicit L3 planner correctly certifies a supplied collection of parent
replacements, but a caller could otherwise supply only a convenient subset of
the tetrahedra intersected by one finite source triangle.  This read-only L2
adapter first performs the exact full triangle-cavity census and then admits a
plan only if it names every non-coplanar clusterel in that census.  It still
does not infer an S/Z-to-row mapping: each row remains an explicit, already
documented caller instruction.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from fractions import Fraction

from core.generator.native_tet.chen_explicit_cavity_plan_l3 import (
    ChenCavityTemplateInstruction,
    ChenExplicitCavityPlanResult,
    TemplateName,
    certify_explicit_cavity_template_plan_l3,
)
from core.generator.native_tet.chen_source_triangle_cavity_l0 import (
    ChenSourceTriangleCavityResult,
    classify_source_triangle_cavity,
)


@dataclass(frozen=True)
class ChenCompleteTriangleCavityPlanResult:
    """Result of binding an explicit plan to the whole finite triangle cavity."""

    accepted: bool
    reason: str
    active_parent_indices: tuple[int, ...]
    face_connected_components: tuple[tuple[int, ...], ...]
    plan: ChenExplicitCavityPlanResult | None
    source_points_unchanged: bool
    production_mesh_changed: bool


def _template_matches_clusterel(template: TemplateName, clusterel_type: str | None) -> bool:
    """Allow only literal rows already certified for that clusterel type."""
    if clusterel_type == "THR_EDG":
        return template in {"THR_S2_Z1", "THR_S1_Z2"}
    return clusterel_type == "FOU_EDG" and template == "FOU_SSSS"


def certify_complete_explicit_triangle_cavity_plan_l2(
    points: Sequence[Sequence[float | int | Fraction]],
    parent_tets: Sequence[Sequence[int]],
    source_triangle: Sequence[Sequence[float | int | Fraction]],
    instructions: Sequence[ChenCavityTemplateInstruction],
) -> ChenCompleteTriangleCavityPlanResult:
    """Certify an explicit plan only when it replaces every active parent.

    Parent identifiers are global ``parent_tets`` indices.  A local A/B/C/D
    order may be a permutation of that parent, because the paper's documented
    row order is geometric rather than input-array order.  Any unsupported
    clusterel or omitted/extra parent rejects before the L3 planner receives a
    candidate.
    """
    before = tuple(tuple(point) for point in points)
    cavity: ChenSourceTriangleCavityResult = classify_source_triangle_cavity(
        points, parent_tets, source_triangle
    )
    if not cavity.accepted:
        return ChenCompleteTriangleCavityPlanResult(
            False, f"cavity_census_failed:{cavity.reason}", (), (), None, before == tuple(points), False
        )
    active = tuple(item.parent_index for item in cavity.clusterels)
    if not active:
        return ChenCompleteTriangleCavityPlanResult(
            False,
            "source_triangle_has_no_noncoplanar_clusterel",
            (),
            cavity.face_connected_components,
            None,
            before == tuple(points),
            False,
        )
    supplied = tuple(instruction.parent_identifier for instruction in instructions)
    if len(set(supplied)) != len(supplied):
        return ChenCompleteTriangleCavityPlanResult(
            False,
            "duplicate_plan_parent_identifier",
            active,
            cavity.face_connected_components,
            None,
            before == tuple(points),
            False,
        )
    if set(supplied) != set(active):
        return ChenCompleteTriangleCavityPlanResult(
            False,
            "plan_must_cover_exactly_all_active_triangle_clusterels",
            active,
            cavity.face_connected_components,
            None,
            before == tuple(points),
            False,
        )
    clusterels = {item.parent_index: item.classification.clusterel_type for item in cavity.clusterels}
    for instruction in instructions:
        if not _template_matches_clusterel(
            instruction.template, clusterels[instruction.parent_identifier]
        ):
            return ChenCompleteTriangleCavityPlanResult(
                False,
                "template_not_certified_for_active_clusterel_type",
                active,
                cavity.face_connected_components,
                None,
                before == tuple(points),
                False,
            )
        if set(instruction.local_parent) != set(parent_tets[instruction.parent_identifier]):
            return ChenCompleteTriangleCavityPlanResult(
                False,
                "local_parent_is_not_a_permutation_of_its_global_parent",
                active,
                cavity.face_connected_components,
                None,
                before == tuple(points),
                False,
            )
    plan = certify_explicit_cavity_template_plan_l3(points, source_triangle, instructions)
    unchanged = before == tuple(tuple(point) for point in points)
    return ChenCompleteTriangleCavityPlanResult(
        plan.accepted and unchanged,
        "accepted" if plan.accepted and unchanged else f"explicit_plan_failed:{plan.reason}",
        active,
        cavity.face_connected_components,
        plan,
        unchanged,
        False,
    )
