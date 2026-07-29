"""Deterministic, non-mutating Si--Gärtner segment-split proposal.

This card implements only the exact rational midpoint branch of Rule 1.  The
paper's distance-offset and acute Rule 2/3 branches can require an algebraic
coordinate or a local-feature-size oracle, so they fail closed here rather
than silently approximating a source-boundary point.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from fractions import Fraction

from core.generator.native_tet.chen_penetration_l0 import _dot, _point, _sub

Point = tuple[Fraction, Fraction, Fraction]
Edge = tuple[int, int]


@dataclass(frozen=True)
class SiSegmentSplitPlanL0:
    """One deterministic Rule-1 proposal, without insertion or re-Delaunay."""

    accepted: bool
    reason: str
    chosen_encroacher_index: int | None
    endpoint_is_acute: tuple[bool, bool]
    candidate_parameter: Fraction | None
    candidate_point: Point | None
    source_points_unchanged: bool
    production_mesh_changed: bool


def _edge(first: int, second: int) -> Edge:
    return (first, second) if first < second else (second, first)


def _is_acute_at(vertex: int, source_edges: Sequence[Edge], points: Sequence[Point]) -> bool:
    directions = [
        _sub(points[other], points[vertex])
        for first, second in source_edges
        for other in ((second,) if first == vertex else (first,) if second == vertex else ())
    ]
    for first_index, first in enumerate(directions):
        first_squared = Fraction(_dot(first, first))
        if first_squared == 0:
            continue
        for second in directions[first_index + 1 :]:
            second_squared = Fraction(_dot(second, second))
            dot = Fraction(_dot(first, second))
            if second_squared and dot > 0 and 4 * dot * dot > first_squared * second_squared:
                return True
    return False


def _point_at(first: Point, second: Point, parameter: Fraction) -> Point:
    return tuple(
        first[index] + parameter * (second[index] - first[index]) for index in range(3)
    )  # type: ignore[return-value]


def plan_si_segment_split_l0(
    points: Sequence[Sequence[float | int | Fraction]],
    source_edge: Sequence[int],
    all_source_edges: Sequence[Sequence[int]],
) -> SiSegmentSplitPlanL0:
    """Propose deterministic exact Rule 1 midpoint only when it is applicable."""
    rational = tuple(_point(point) for point in points)
    before = rational
    edge_values = tuple(int(index) for index in source_edge)
    try:
        source_edges = tuple(_edge(int(edge[0]), int(edge[1])) for edge in all_source_edges)
        if (
            len(edge_values) != 2
            or edge_values[0] == edge_values[1]
            or not source_edges
            or any(len(edge) != 2 for edge in all_source_edges)
            or any(
                index < 0 or index >= len(rational)
                for index in (*edge_values, *sum(source_edges, ()))
            )
        ):
            raise ValueError
    except (TypeError, ValueError):
        return SiSegmentSplitPlanL0(
            False, "invalid_source_edge", None, (False, False), None, None, True, False
        )
    first, second = (rational[index] for index in edge_values)
    direction = _sub(second, first)
    length_squared = Fraction(_dot(direction, direction))
    if length_squared == 0:
        return SiSegmentSplitPlanL0(
            False, "zero_length_source_edge", None, (False, False), None, None, True, False
        )
    acute = (
        _is_acute_at(edge_values[0], source_edges, rational),
        _is_acute_at(edge_values[1], source_edges, rational),
    )
    if acute[0] != acute[1]:
        return SiSegmentSplitPlanL0(
            False, "type1_requires_lfs_rule2_or_rule3", None, acute, None, None, True, False
        )
    midpoint = _point_at(first, second, Fraction(1, 2))
    radius_squared = length_squared / 4
    encroachers: list[
        tuple[Fraction, tuple[Fraction, Fraction, Fraction], int, Fraction, Fraction]
    ] = []
    for index, point in enumerate(rational):
        if index in edge_values:
            continue
        midpoint_distance = Fraction(_dot(_sub(point, midpoint), _sub(point, midpoint)))
        if midpoint_distance >= radius_squared:
            continue
        encroachers.append(
            (
                midpoint_distance,
                point,
                index,
                Fraction(_dot(_sub(point, first), _sub(point, first))),
                Fraction(_dot(_sub(point, second), _sub(point, second))),
            )
        )
    if not encroachers:
        return SiSegmentSplitPlanL0(
            False, "no_strict_diametric_encroacher", None, acute, None, None, True, False
        )
    _, _, selected, distance_first, distance_second = min(encroachers)
    if distance_first < radius_squared or distance_second < radius_squared:
        return SiSegmentSplitPlanL0(
            False,
            "rule1_distance_offset_requires_algebraic_coordinate",
            selected,
            acute,
            None,
            None,
            rational == before,
            False,
        )
    unchanged = rational == before
    return SiSegmentSplitPlanL0(
        unchanged,
        "accepted_rule1_rational_midpoint" if unchanged else "source_points_changed",
        selected,
        acute,
        Fraction(1, 2),
        midpoint,
        unchanged,
        False,
    )
