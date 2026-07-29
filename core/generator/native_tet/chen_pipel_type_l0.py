"""Exact read-only classifier for Chen--Zheng-2006 Table-2 pipel types.

A ``pipel`` is one tetrahedron traversed by a missing source edge.  Chen and
Zheng classify its two intersection positions as NOD, EDG, FAC, or DEG before
selecting a decomposition table.  This module establishes that prerequisite
without choosing a decomposition or mutating tetrahedral connectivity.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from fractions import Fraction
from typing import Literal

from core.generator.native_tet.chen_penetration_l0 import RationalPoint, _point

IntersectionKind = Literal["NOD", "EDG", "FAC", "DEG"]
PipelCase = Literal["CASE1", "CASE2", "CASE3", "CASE4", "CASE5"]


@dataclass(frozen=True)
class ChenPipelTypeResult:
    """Table-2 classification result; unsupported combinations fail closed."""

    accepted: bool
    reason: str
    first_kind: IntersectionKind
    second_kind: IntersectionKind
    pipel_case: PipelCase | None


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


def _point_on_open_segment(point: RationalPoint, start: RationalPoint, end: RationalPoint) -> bool:
    direction = _sub(end, start)
    offset = _sub(point, start)
    coordinate = next((index for index, value in enumerate(direction) if value != 0), None)
    if coordinate is None:
        return False
    parameter = offset[coordinate] / direction[coordinate]
    return Fraction(0) < parameter < Fraction(1) and all(
        offset[index] == parameter * direction[index] for index in range(3)
    )


def _strictly_inside_triangle(
    point: RationalPoint, triangle: tuple[RationalPoint, RationalPoint, RationalPoint]
) -> bool:
    origin, second, third = triangle
    first_vector = _sub(second, origin)
    second_vector = _sub(third, origin)
    offset = _sub(point, origin)
    first_norm = _dot(first_vector, first_vector)
    mixed = _dot(first_vector, second_vector)
    second_norm = _dot(second_vector, second_vector)
    determinant = first_norm * second_norm - mixed * mixed
    if determinant == 0:
        return False
    alpha = (
        _dot(offset, first_vector) * second_norm - _dot(offset, second_vector) * mixed
    ) / determinant
    beta = (
        _dot(offset, second_vector) * first_norm - _dot(offset, first_vector) * mixed
    ) / determinant
    return alpha > 0 and beta > 0 and Fraction(1) - alpha - beta > 0


def _coplanar(
    point: RationalPoint, first: RationalPoint, second: RationalPoint, third: RationalPoint
) -> bool:
    return _dot(_sub(point, first), _cross(_sub(second, first), _sub(third, first))) == 0


def classify_tet_boundary_position(
    tetrahedron: Sequence[Sequence[float | int | Fraction]],
    point: Sequence[float | int | Fraction] | None,
) -> IntersectionKind | None:
    """Return the Table-2 NOD/EDG/FAC kind, ``DEG`` for no intersection."""
    if point is None:
        return "DEG"
    if len(tetrahedron) != 4:
        raise ValueError("a pipel requires one tetrahedron")
    tet = tuple(_point(vertex) for vertex in tetrahedron)
    if len(set(tet)) != 4:
        raise ValueError("a pipel tetrahedron needs four distinct vertices")
    query = _point(point)
    if query in tet:
        return "NOD"
    edges = ((0, 1), (0, 2), (0, 3), (1, 2), (1, 3), (2, 3))
    if any(_point_on_open_segment(query, tet[first], tet[second]) for first, second in edges):
        return "EDG"
    for omitted in range(4):
        face_values = [tet[index] for index in range(4) if index != omitted]
        face: tuple[RationalPoint, RationalPoint, RationalPoint] = (
            face_values[0],
            face_values[1],
            face_values[2],
        )
        if _coplanar(query, face[0], face[1], face[2]) and _strictly_inside_triangle(query, face):
            return "FAC"
    return None


def classify_pipel_type(
    tetrahedron: Sequence[Sequence[float | int | Fraction]],
    first_intersection: Sequence[float | int | Fraction] | None,
    second_intersection: Sequence[float | int | Fraction] | None,
) -> ChenPipelTypeResult:
    """Classify exactly the five Chen--Zheng Table-2 combinations."""
    first_kind = classify_tet_boundary_position(tetrahedron, first_intersection)
    second_kind = classify_tet_boundary_position(tetrahedron, second_intersection)
    if first_kind is None or second_kind is None:
        return ChenPipelTypeResult(False, "intersection_not_on_tet_boundary", "DEG", "DEG", None)
    mapping: dict[tuple[IntersectionKind, IntersectionKind], PipelCase] = {
        ("NOD", "EDG"): "CASE1",
        ("EDG", "NOD"): "CASE1",
        ("EDG", "DEG"): "CASE1",
        ("EDG", "EDG"): "CASE2",
        ("NOD", "FAC"): "CASE3",
        ("FAC", "NOD"): "CASE3",
        ("EDG", "FAC"): "CASE4",
        ("FAC", "EDG"): "CASE4",
        ("FAC", "FAC"): "CASE5",
    }
    pipel_case = mapping.get((first_kind, second_kind))
    return ChenPipelTypeResult(
        pipel_case is not None,
        "accepted" if pipel_case is not None else "unsupported_table2_intersection_pair",
        first_kind,
        second_kind,
        pipel_case,
    )
