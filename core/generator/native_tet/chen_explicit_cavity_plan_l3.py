"""Fail-closed L3 assembler for explicitly documented Chen cavity templates.

This intentionally accepts an explicit per-parent template instruction rather
than inventing a global S/Z selection rule.  It realizes only literal rows that
already have local certificates, then delegates the whole cavity shell to the
parallel exact-subdivision staging audit.  No CDT arrays are mutated.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from fractions import Fraction
from typing import Literal

from core.generator.native_tet.chen_clusterel_type_l0 import classify_clusterel_type
from core.generator.native_tet.chen_fou_edg_source_match_l1 import (
    certify_fou_edg_source_match_l1,
)
from core.generator.native_tet.chen_penetration_l0 import _point
from core.generator.native_tet.chen_staged_state_l0 import _boundary_faces
from core.generator.native_tet.chen_subdivided_staged_state_l3 import (
    ChenSubdividedStagedCommitResult,
    certify_atomic_subdivided_boundary_replacement_l3,
)
from core.generator.native_tet.chen_thr_edg_source_match_l1 import (
    certify_thr_edg_source_match_l1,
)

TemplateName = Literal["THR_S2_Z1", "THR_S1_Z2", "FOU_SSSS"]
Point = tuple[Fraction, Fraction, Fraction]
IndexTet = tuple[int, int, int, int]


@dataclass(frozen=True)
class ChenCavityTemplateInstruction:
    """One local parent in the paper's documented A/B/C/D order."""

    parent_identifier: int
    local_parent: IndexTet
    template: TemplateName


@dataclass(frozen=True)
class ChenExplicitCavityPlanResult:
    """Atomic report-only explicit-template plan; no implicit selection occurs."""

    accepted: bool
    reason: str
    template_sequence: tuple[TemplateName, ...]
    constructed_points: int
    staging: ChenSubdividedStagedCommitResult | None
    source_points_unchanged: bool
    production_mesh_changed: bool


def _point_map_for_template(
    template: TemplateName,
    tetrahedron: Sequence[Point],
    source_triangle: Sequence[Sequence[float | int | Fraction]],
) -> tuple[dict[str, Point], tuple[tuple[str, str, str, str], ...]] | None:
    """Return literal child labels only after the matching finite-source check."""
    expected: tuple[tuple[int, int], ...]
    labels: tuple[str, ...]
    p_labels: tuple[tuple[str, tuple[int, int]], ...]
    if template in {"THR_S2_Z1", "THR_S1_Z2"}:
        subcase = "S2/Z1" if template == "THR_S2_Z1" else "S1/Z2"
        matched = certify_thr_edg_source_match_l1(tetrahedron, source_triangle, subcase=subcase)
        expected = ((0, 3), (1, 3), (2, 3))
        if not matched.accepted or matched.candidate is None:
            return None
        children = matched.candidate.oriented_children
        labels = ("A", "B", "C", "D", "P1", "P2", "P3")
        p_labels = (("P1", (0, 3)), ("P2", (1, 3)), ("P3", (2, 3)))
    else:
        matched = certify_fou_edg_source_match_l1(tetrahedron, source_triangle)
        expected = ((0, 2), (0, 3), (1, 2), (1, 3))
        if not matched.accepted or matched.candidate is None:
            return None
        children = matched.candidate.oriented_children
        labels = ("A", "B", "C", "D", "P1", "P2", "P3", "P4")
        p_labels = (
            ("P1", (0, 3)),
            ("P2", (1, 3)),
            ("P3", (1, 2)),
            ("P4", (0, 2)),
        )
    classification = classify_clusterel_type(tetrahedron, source_triangle)
    if (
        not classification.accepted
        or classification.penetration is None
        or classification.penetration.penetrating_edges != expected
    ):
        return None
    intersections = dict(
        zip(
            classification.penetration.penetrating_edges,
            classification.penetration.intersection_points,
            strict=True,
        )
    )
    points = {label: tetrahedron[index] for index, label in enumerate(labels[:4])}
    points.update({label: intersections[edge] for label, edge in p_labels})
    return points, children


def certify_explicit_cavity_template_plan_l3(
    points: Sequence[Sequence[float | int | Fraction]],
    source_triangle: Sequence[Sequence[float | int | Fraction]],
    instructions: Sequence[ChenCavityTemplateInstruction],
) -> ChenExplicitCavityPlanResult:
    """Assemble documented rows only, then certify their complete cavity shell."""
    before = tuple(_point(point) for point in points)
    if not instructions:
        return ChenExplicitCavityPlanResult(False, "empty_template_plan", (), 0, None, True, False)
    if len({instruction.parent_identifier for instruction in instructions}) != len(instructions):
        return ChenExplicitCavityPlanResult(
            False, "duplicate_parent_identifier", (), 0, None, True, False
        )
    if any(
        len(set(instruction.local_parent)) != 4
        or any(index < 0 or index >= len(before) for index in instruction.local_parent)
        for instruction in instructions
    ):
        return ChenExplicitCavityPlanResult(False, "invalid_local_parent", (), 0, None, True, False)
    global_points = list(before)
    ids = {point: index for index, point in enumerate(global_points)}

    def point_id(point: Point) -> int:
        if point not in ids:
            ids[point] = len(global_points)
            global_points.append(point)
        return ids[point]

    parents: dict[int, IndexTet] = {}
    children: dict[int, tuple[IndexTet, ...]] = {}
    sequence: list[TemplateName] = []
    for instruction in instructions:
        tetrahedron = tuple(before[index] for index in instruction.local_parent)
        materialized = _point_map_for_template(instruction.template, tetrahedron, source_triangle)
        if materialized is None:
            return ChenExplicitCavityPlanResult(
                False,
                "template_does_not_match_documented_finite_clusterel",
                tuple(sequence),
                len(global_points) - len(before),
                None,
                tuple(_point(point) for point in points) == before,
                False,
            )
        labels, local_children = materialized
        parents[instruction.parent_identifier] = instruction.local_parent
        mapped_children: list[IndexTet] = []
        for child in local_children:
            mapped_children.append(
                (
                    point_id(labels[child[0]]),
                    point_id(labels[child[1]]),
                    point_id(labels[child[2]]),
                    point_id(labels[child[3]]),
                )
            )
        children[instruction.parent_identifier] = tuple(mapped_children)
        sequence.append(instruction.template)
    boundary = tuple(sorted(_boundary_faces(tuple(parents.values()))))
    staging = certify_atomic_subdivided_boundary_replacement_l3(
        global_points, parents, boundary, children
    )
    unchanged = tuple(_point(point) for point in points) == before
    return ChenExplicitCavityPlanResult(
        staging.accepted and unchanged,
        "accepted" if staging.accepted and unchanged else "explicit_cavity_staging_failed",
        tuple(sequence),
        len(global_points) - len(before),
        staging,
        unchanged,
        False,
    )
