"""Test-only exact classifier for Chen-2011 penetration templates.

This module deliberately does not alter a tetrahedral mesh.  It establishes
the intersection-classification prerequisite for a future constrained boundary
rebuild: all arithmetic is rational from the supplied IEEE-754 coordinates,
and coplanar or boundary-touching cases are rejected as non-unique rather than
being assigned an invented Chen template.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from fractions import Fraction
from itertools import combinations
from typing import Literal

RationalPoint = tuple[Fraction, Fraction, Fraction]
PenetrationStatus = Literal[
    "subface",
    "unique",
    "degenerate_source_triangle",
    "coplanar_or_vertex_touch",
    "constraint_boundary_touch",
]


@dataclass(frozen=True)
class ChenPenetrationClassification:
    """Read-only result for one constraint triangle and one tetrahedron."""

    status: PenetrationStatus
    penetrating_edges: tuple[tuple[int, int], ...]
    intersection_points: tuple[RationalPoint, ...]

    @property
    def n_penetrating_edges(self) -> int:
        return len(self.penetrating_edges)


def _fraction(value: float | int | Fraction) -> Fraction:
    if isinstance(value, Fraction):
        return value
    if isinstance(value, int):
        return Fraction(value)
    return Fraction.from_float(value)


def _point(values: Sequence[float | int | Fraction]) -> RationalPoint:
    if len(values) != 3:
        raise ValueError("each point must have three coordinates")
    return (_fraction(values[0]), _fraction(values[1]), _fraction(values[2]))


def _sub(a: RationalPoint, b: RationalPoint) -> RationalPoint:
    return tuple(x - y for x, y in zip(a, b, strict=True))  # type: ignore[return-value]


def _add(a: RationalPoint, b: RationalPoint) -> RationalPoint:
    return tuple(x + y for x, y in zip(a, b, strict=True))  # type: ignore[return-value]


def _scale(factor: Fraction, vector: RationalPoint) -> RationalPoint:
    return tuple(factor * value for value in vector)  # type: ignore[return-value]


def _dot(a: RationalPoint, b: RationalPoint) -> Fraction:
    return sum((x * y for x, y in zip(a, b, strict=True)), Fraction(0))


def _cross(a: RationalPoint, b: RationalPoint) -> RationalPoint:
    return (
        a[1] * b[2] - a[2] * b[1],
        a[2] * b[0] - a[0] * b[2],
        a[0] * b[1] - a[1] * b[0],
    )


def _strictly_inside_triangle(
    point: RationalPoint,
    triangle: tuple[RationalPoint, RationalPoint, RationalPoint],
) -> bool:
    origin, second, third = triangle
    u = _sub(second, origin)
    v = _sub(third, origin)
    offset = _sub(point, origin)
    uu = _dot(u, u)
    uv = _dot(u, v)
    vv = _dot(v, v)
    determinant = uu * vv - uv * uv
    if determinant == 0:
        return False
    alpha = (_dot(offset, u) * vv - _dot(offset, v) * uv) / determinant
    beta = (_dot(offset, v) * uu - _dot(offset, u) * uv) / determinant
    gamma = Fraction(1) - alpha - beta
    return alpha > 0 and beta > 0 and gamma > 0


def _inside_or_on_triangle(
    point: RationalPoint,
    triangle: tuple[RationalPoint, RationalPoint, RationalPoint],
) -> bool:
    origin, second, third = triangle
    u = _sub(second, origin)
    v = _sub(third, origin)
    offset = _sub(point, origin)
    uu = _dot(u, u)
    uv = _dot(u, v)
    vv = _dot(v, v)
    determinant = uu * vv - uv * uv
    if determinant == 0:
        return False
    alpha = (_dot(offset, u) * vv - _dot(offset, v) * uv) / determinant
    beta = (_dot(offset, v) * uu - _dot(offset, u) * uv) / determinant
    gamma = Fraction(1) - alpha - beta
    return alpha >= 0 and beta >= 0 and gamma >= 0


def strict_segment_triangle_intersection(
    first: Sequence[float | int | Fraction],
    second: Sequence[float | int | Fraction],
    triangle: Sequence[Sequence[float | int | Fraction]],
) -> RationalPoint | None:
    """Return a unique strict segment/triangle intersection, otherwise ``None``."""
    if len(triangle) != 3:
        raise ValueError("a constraint triangle requires three points")
    start = _point(first)
    end = _point(second)
    tri: tuple[RationalPoint, RationalPoint, RationalPoint] = (
        _point(triangle[0]),
        _point(triangle[1]),
        _point(triangle[2]),
    )
    normal = _cross(_sub(tri[1], tri[0]), _sub(tri[2], tri[0]))
    if _dot(normal, normal) == 0:
        return None
    start_sign = _dot(normal, _sub(start, tri[0]))
    end_sign = _dot(normal, _sub(end, tri[0]))
    if start_sign == 0 or end_sign == 0 or (start_sign > 0) == (end_sign > 0):
        return None
    fraction = start_sign / (start_sign - end_sign)
    intersection = _add(start, _scale(fraction, _sub(end, start)))
    return intersection if _strictly_inside_triangle(intersection, tri) else None


def classify_constraint_triangle_penetration(
    tetrahedron: Sequence[Sequence[float | int | Fraction]],
    constraint_triangle: Sequence[Sequence[float | int | Fraction]],
) -> ChenPenetrationClassification:
    """Classify strict edge penetrations without mutating mesh connectivity.

    The result matches Chen et al.'s *number of penetrating edges* taxonomy
    only for a unique intersection.  Contact with a constraint edge/vertex or
    a coplanar tetrahedron edge is ambiguous and must be handled by a separate
    exact-degeneracy card, never a template guess.
    """
    if len(tetrahedron) != 4:
        raise ValueError("a tetrahedron requires four points")
    if len(constraint_triangle) != 3:
        raise ValueError("a constraint triangle requires three points")
    tet = tuple(_point(point) for point in tetrahedron)
    tri: tuple[RationalPoint, RationalPoint, RationalPoint] = (
        _point(constraint_triangle[0]),
        _point(constraint_triangle[1]),
        _point(constraint_triangle[2]),
    )
    normal = _cross(_sub(tri[1], tri[0]), _sub(tri[2], tri[0]))
    if _dot(normal, normal) == 0:
        return ChenPenetrationClassification("degenerate_source_triangle", (), ())
    signed = tuple(_dot(normal, _sub(point, tri[0])) for point in tet)

    for indices in combinations(range(4), 3):
        if all(signed[index] == 0 for index in indices) and all(
            _inside_or_on_triangle(tet[index], tri) for index in indices
        ):
            return ChenPenetrationClassification("subface", (), ())

    penetrating_edges: list[tuple[int, int]] = []
    intersections: list[RationalPoint] = []
    for first, second in combinations(range(4), 2):
        first_sign, second_sign = signed[first], signed[second]
        if first_sign == 0 or second_sign == 0:
            return ChenPenetrationClassification("coplanar_or_vertex_touch", (), ())
        if (first_sign > 0) == (second_sign > 0):
            continue
        fraction = first_sign / (first_sign - second_sign)
        intersection = _add(tet[first], _scale(fraction, _sub(tet[second], tet[first])))
        if not _strictly_inside_triangle(intersection, tri):
            if _inside_or_on_triangle(intersection, tri):
                return ChenPenetrationClassification("constraint_boundary_touch", (), ())
            continue
        penetrating_edges.append((first, second))
        intersections.append(intersection)

    return ChenPenetrationClassification("unique", tuple(penetrating_edges), tuple(intersections))
