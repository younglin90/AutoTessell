"""Exact, read-only source-edge-to-pipel ownership worklist.

This is the geometry prerequisite missing from the local Chen transactions:
clip a source segment against every non-degenerate tetrahedron using rational
barycentric coordinates, require a gap-free non-overlapping ordered covering,
and classify each real interior traversal with Table-2 endpoint kinds.  It
does not decompose pipels or mutate connectivity.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from fractions import Fraction

from core.generator.native_tet.chen_penetration_l0 import RationalPoint, _point
from core.generator.native_tet.chen_pipel_type_l0 import ChenPipelTypeResult, classify_pipel_type

IndexTet = tuple[int, int, int, int]


@dataclass(frozen=True)
class ChenSourcePipel:
    """One exact interior source-segment interval owned by one tetrahedron."""

    parent_index: int
    entry_parameter: Fraction
    exit_parameter: Fraction
    pipel_type: ChenPipelTypeResult


@dataclass(frozen=True)
class ChenSourceEdgeWorklistResult:
    """Fail-closed source-edge coverage result; rejected cases expose no pipels."""

    accepted: bool
    reason: str
    pipels: tuple[ChenSourcePipel, ...]


def _sub(first: RationalPoint, second: RationalPoint) -> RationalPoint:
    return (
        first[0] - second[0],
        first[1] - second[1],
        first[2] - second[2],
    )


def _cross(first: RationalPoint, second: RationalPoint) -> RationalPoint:
    return (
        first[1] * second[2] - first[2] * second[1],
        first[2] * second[0] - first[0] * second[2],
        first[0] * second[1] - first[1] * second[0],
    )


def _dot(first: RationalPoint, second: RationalPoint) -> Fraction:
    return sum((left * right for left, right in zip(first, second, strict=True)), Fraction(0))


def _orient6_points(
    first: RationalPoint,
    second: RationalPoint,
    third: RationalPoint,
    fourth: RationalPoint,
) -> Fraction:
    return _dot(_sub(second, first), _cross(_sub(third, first), _sub(fourth, first)))


def _as_index_tet(tet: Sequence[int]) -> IndexTet | None:
    values = tuple(int(vertex) for vertex in tet)
    if len(values) != 4 or len(set(values)) != 4:
        return None
    return values[0], values[1], values[2], values[3]


def _point_at(start: RationalPoint, end: RationalPoint, parameter: Fraction) -> RationalPoint:
    direction = _sub(end, start)
    return (
        start[0] + parameter * direction[0],
        start[1] + parameter * direction[1],
        start[2] + parameter * direction[2],
    )


def _barycentric(
    point: RationalPoint, tet: IndexTet, points: Sequence[RationalPoint]
) -> tuple[Fraction, ...] | None:
    first, second, third, fourth = (points[index] for index in tet)
    denominator = _orient6_points(first, second, third, fourth)
    if denominator == 0:
        return None
    return (
        _orient6_points(point, second, third, fourth) / denominator,
        _orient6_points(first, point, third, fourth) / denominator,
        _orient6_points(first, second, point, fourth) / denominator,
        _orient6_points(first, second, third, point) / denominator,
    )


def _clip_segment_to_tet(
    start: RationalPoint, end: RationalPoint, tet: IndexTet, points: Sequence[RationalPoint]
) -> tuple[Fraction, Fraction] | None:
    at_start = _barycentric(start, tet, points)
    at_end = _barycentric(end, tet, points)
    if at_start is None or at_end is None:
        return None
    lower, upper = Fraction(0), Fraction(1)
    for start_value, end_value in zip(at_start, at_end, strict=True):
        delta = end_value - start_value
        if delta > 0:
            lower = max(lower, -start_value / delta)
        elif delta < 0:
            upper = min(upper, -start_value / delta)
        elif start_value < 0:
            return None
    return (lower, upper) if lower < upper else None


def _strictly_inside_at(
    start: RationalPoint,
    end: RationalPoint,
    parameter: Fraction,
    tet: IndexTet,
    points: Sequence[RationalPoint],
) -> bool:
    barycentric = _barycentric(_point_at(start, end, parameter), tet, points)
    return barycentric is not None and all(value > 0 for value in barycentric)


def build_source_edge_pipel_worklist(
    points: Sequence[Sequence[float | int | Fraction]],
    parent_tets: Sequence[Sequence[int]],
    source_start: Sequence[float | int | Fraction],
    source_end: Sequence[float | int | Fraction],
) -> ChenSourceEdgeWorklistResult:
    """Return an exact ordered Table-2 worklist for a fully covered source segment."""
    rational_points = tuple(_point(point) for point in points)
    start, end = _point(source_start), _point(source_end)
    if start == end:
        return ChenSourceEdgeWorklistResult(False, "zero_length_source_edge", ())
    typed_tets = tuple(_as_index_tet(tet) for tet in parent_tets)
    if not typed_tets or any(tet is None for tet in typed_tets):
        return ChenSourceEdgeWorklistResult(False, "invalid_parent_tetrahedron", ())
    tets = tuple(tet for tet in typed_tets if tet is not None)
    if any(vertex < 0 or vertex >= len(rational_points) for tet in tets for vertex in tet):
        return ChenSourceEdgeWorklistResult(False, "parent_index_out_of_range", ())

    intervals: list[tuple[Fraction, Fraction, int, IndexTet]] = []
    for index, tet in enumerate(tets):
        interval = _clip_segment_to_tet(start, end, tet, rational_points)
        if interval is not None:
            intervals.append((interval[0], interval[1], index, tet))
    intervals.sort()
    if not intervals or intervals[0][0] != 0 or intervals[-1][1] != 1:
        return ChenSourceEdgeWorklistResult(False, "source_edge_has_gap_or_uncovered_endpoint", ())

    pipels: list[ChenSourcePipel] = []
    previous_exit = Fraction(0)
    for entry, exit, index, tet in intervals:
        if entry != previous_exit:
            return ChenSourceEdgeWorklistResult(
                False, "source_edge_has_gap_or_overlapping_pipels", ()
            )
        midpoint = (entry + exit) / 2
        if not _strictly_inside_at(start, end, midpoint, tet, rational_points):
            return ChenSourceEdgeWorklistResult(False, "cofacial_or_noninterior_pipel_segment", ())
        entry_point = _point_at(start, end, entry)
        exit_point = _point_at(start, end, exit)
        pipel_type = classify_pipel_type(
            tuple(rational_points[vertex] for vertex in tet), entry_point, exit_point
        )
        if not pipel_type.accepted:
            return ChenSourceEdgeWorklistResult(False, "unsupported_table2_pipel_type", ())
        pipels.append(ChenSourcePipel(index, entry, exit, pipel_type))
        previous_exit = exit
    return ChenSourceEdgeWorklistResult(True, "accepted", tuple(pipels))
