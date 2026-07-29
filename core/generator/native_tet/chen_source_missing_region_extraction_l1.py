"""Read-only L1 extraction of a whole-source-triangle missing region.

This is the smallest real-mesh bridge to the Si--Gärtner recovery sequence.
With no segment Steiner points on a source triangle, its facet 2-D CDT contains
one subface.  The module determines whether that absent subface has all source
boundary edges present and whether edge-touching tetrahedra expose exactly one
strict source-plane shell.  It never removes, creates, or reorders a tet.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from fractions import Fraction

from core.generator.native_tet.chen_penetration_l0 import _cross, _dot, _point, _sub
from core.generator.native_tet.chen_source_missing_region_plan_l0 import (
    ChenSourceMissingRegionPlan,
    plan_source_missing_region_l0,
)

Point = tuple[Fraction, Fraction, Fraction]
Face = tuple[int, int, int]
Tet = tuple[int, int, int, int]


@dataclass(frozen=True)
class ChenSourceMissingRegionExtractionL1:
    """Current-complex diagnosis for one direct-missing source face."""

    accepted: bool
    reason: str
    plan: ChenSourceMissingRegionPlan | None
    source_edge_touch_tet_ids: tuple[int, ...]
    crossing_tet_ids: tuple[int, ...]
    zero_side_tet_ids: tuple[int, ...]
    source_points_unchanged: bool
    production_mesh_changed: bool


def _face(value: Sequence[int]) -> Face | None:
    result = tuple(int(index) for index in value)
    if len(result) != 3 or len(set(result)) != 3:
        return None
    return result[0], result[1], result[2]


def _tet(value: Sequence[int]) -> Tet | None:
    result = tuple(int(index) for index in value)
    if len(result) != 4 or len(set(result)) != 4:
        return None
    return result[0], result[1], result[2], result[3]


def _canonical_face(face: Face) -> Face:
    ordered = tuple(sorted(face))
    return ordered[0], ordered[1], ordered[2]


def _tet_faces(tet: Tet) -> tuple[Face, Face, Face, Face]:
    return tuple(
        tuple(tet[index] for index in range(4) if index != omitted)  # type: ignore[return-value]
        for omitted in range(4)
    )


def _contains_source_edge(tet: Tet, source: Face) -> bool:
    vertices = set(tet)
    return any({source[index], source[(index + 1) % 3]}.issubset(vertices) for index in range(3))


def _strict_side(tet: Tet, points: Sequence[Point], source: Face) -> int | None:
    source_points = tuple(points[index] for index in source)
    normal = _cross(
        _sub(source_points[1], source_points[0]),
        _sub(source_points[2], source_points[0]),
    )
    signed = tuple(Fraction(_dot(normal, _sub(points[index], source_points[0]))) for index in tet)
    if all(value >= 0 for value in signed) and any(value > 0 for value in signed):
        return 1
    if all(value <= 0 for value in signed) and any(value < 0 for value in signed):
        return -1
    return None


def extract_source_missing_region_l1(
    points: Sequence[Sequence[float | int | Fraction]],
    source_face: Sequence[int],
    current_tets: Sequence[Sequence[int]],
) -> ChenSourceMissingRegionExtractionL1:
    """Extract one whole-face missing-region plan, or explain why it is unsafe."""
    rational = tuple(_point(point) for point in points)
    before = rational
    source = _face(source_face)
    tets = tuple(_tet(tet) for tet in current_tets)
    if (
        source is None
        or not tets
        or any(tet is None for tet in tets)
        or any(index < 0 or index >= len(rational) for index in source or ())
        or any(
            index < 0 or index >= len(rational) for tet in tets if tet is not None for index in tet
        )
    ):
        return ChenSourceMissingRegionExtractionL1(
            False, "invalid_index_input", None, (), (), (), True, False
        )
    typed_tets = tuple(tet for tet in tets if tet is not None)
    if any(
        _canonical_face(face) == _canonical_face(source)
        for tet in typed_tets
        for face in _tet_faces(tet)
    ):
        return ChenSourceMissingRegionExtractionL1(
            False, "source_face_already_present", None, (), (), (), rational == before, False
        )
    touch_ids = tuple(
        index for index, tet in enumerate(typed_tets) if _contains_source_edge(tet, source)
    )
    positive: list[int] = []
    negative: list[int] = []
    crossing: list[int] = []
    zero_side: list[int] = []
    for index in touch_ids:
        side = _strict_side(typed_tets[index], rational, source)
        if side == 1:
            positive.append(index)
        elif side == -1:
            negative.append(index)
        else:
            signs = tuple(
                Fraction(
                    _dot(
                        _cross(
                            _sub(rational[source[1]], rational[source[0]]),
                            _sub(rational[source[2]], rational[source[0]]),
                        ),
                        _sub(rational[vertex], rational[source[0]]),
                    )
                )
                for vertex in typed_tets[index]
            )
            if all(value == 0 for value in signs):
                zero_side.append(index)
            else:
                crossing.append(index)
    plan = plan_source_missing_region_l0(
        rational,
        source,
        (source,),
        typed_tets,
        positive_shell_owner_ids=positive,
        negative_shell_owner_ids=negative,
    )
    unchanged = rational == before
    return ChenSourceMissingRegionExtractionL1(
        plan.accepted and unchanged,
        plan.reason if unchanged else "source_points_changed",
        plan,
        touch_ids,
        tuple(crossing),
        tuple(zero_side),
        unchanged,
        False,
    )
