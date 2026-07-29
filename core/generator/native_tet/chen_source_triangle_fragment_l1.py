"""Exact, read-only finite source-triangle fragment audit for one tetrahedron.

Chen--Zheng records both the number of cut edges and the type of every
intersection node.  Counting strict edge crossings alone cannot identify the
actual portion of a source facet inside a clusterel.  This L1 prerequisite
clips the immutable source triangle against the four exact tet barycentric
half-spaces and exposes that convex fragment without selecting or applying a
Chen decomposition.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from fractions import Fraction

from core.generator.native_tet.chen_penetration_l0 import RationalPoint, _cross, _dot, _point, _sub
from core.generator.native_tet.chen_pipe_cluster_l0 import _orient6

ParameterPoint = tuple[Fraction, Fraction]


@dataclass(frozen=True)
class ChenSourceTriangleFragmentResult:
    """Exact positive-area source fragment, represented in source order."""

    accepted: bool
    reason: str
    parameter_vertices: tuple[ParameterPoint, ...]
    vertices: tuple[RationalPoint, ...]
    parameter_double_area: Fraction
    source_points_unchanged: bool
    production_mesh_changed: bool


def _add(first: RationalPoint, second: RationalPoint) -> RationalPoint:
    return (
        first[0] + second[0],
        first[1] + second[1],
        first[2] + second[2],
    )


def _scale(value: Fraction, vector: RationalPoint) -> RationalPoint:
    return value * vector[0], value * vector[1], value * vector[2]


def _parameter_point(
    origin: RationalPoint,
    first: RationalPoint,
    second: RationalPoint,
    parameter: ParameterPoint,
) -> RationalPoint:
    return _add(origin, _add(_scale(parameter[0], first), _scale(parameter[1], second)))


def _barycentric_coordinates(
    point: RationalPoint, tetrahedron: tuple[RationalPoint, ...]
) -> tuple[Fraction, Fraction, Fraction, Fraction] | None:
    denominator = _orient6(tetrahedron, (0, 1, 2, 3))
    if denominator == 0:
        return None
    first, second, third, fourth = tetrahedron
    return (
        _orient6((point, second, third, fourth), (0, 1, 2, 3)) / denominator,
        _orient6((first, point, third, fourth), (0, 1, 2, 3)) / denominator,
        _orient6((first, second, point, fourth), (0, 1, 2, 3)) / denominator,
        _orient6((first, second, third, point), (0, 1, 2, 3)) / denominator,
    )


def _clip_half_plane(
    polygon: Sequence[ParameterPoint], coefficients: tuple[Fraction, Fraction, Fraction]
) -> tuple[ParameterPoint, ...]:
    """Clip a convex polygon by ``constant + first*u + second*v >= 0``."""
    if not polygon:
        return ()
    constant, first, second = coefficients

    def value(point: ParameterPoint) -> Fraction:
        return constant + first * point[0] + second * point[1]

    clipped: list[ParameterPoint] = []
    previous = polygon[-1]
    previous_value = value(previous)
    for current in polygon:
        current_value = value(current)
        previous_inside = previous_value >= 0
        current_inside = current_value >= 0
        if previous_inside != current_inside:
            fraction = previous_value / (previous_value - current_value)
            clipped.append(
                (
                    previous[0] + fraction * (current[0] - previous[0]),
                    previous[1] + fraction * (current[1] - previous[1]),
                )
            )
        if current_inside:
            clipped.append(current)
        previous, previous_value = current, current_value
    deduplicated: list[ParameterPoint] = []
    for point in clipped:
        if not deduplicated or point != deduplicated[-1]:
            deduplicated.append(point)
    if len(deduplicated) > 1 and deduplicated[0] == deduplicated[-1]:
        deduplicated.pop()
    return tuple(deduplicated)


def _double_area(parameters: Sequence[ParameterPoint]) -> Fraction:
    return sum(
        (
            first[0] * second[1] - first[1] * second[0]
            for first, second in zip(parameters, (*parameters[1:], parameters[0]), strict=True)
        ),
        Fraction(0),
    )


def audit_source_triangle_fragment_l1(
    tetrahedron: Sequence[Sequence[float | int | Fraction]],
    source_triangle: Sequence[Sequence[float | int | Fraction]],
) -> ChenSourceTriangleFragmentResult:
    """Return the exact positive-area part of one source triangle inside one tet."""
    if len(tetrahedron) != 4 or len(source_triangle) != 3:
        raise ValueError("one tetrahedron and one source triangle are required")
    before_tet = tuple(_point(point) for point in tetrahedron)
    before_source = tuple(_point(point) for point in source_triangle)
    if len(set(before_tet)) != 4 or _orient6(before_tet, (0, 1, 2, 3)) == 0:
        return ChenSourceTriangleFragmentResult(False, "degenerate_parent_tetrahedron", (), (), Fraction(0), True, False)
    origin, source_second, source_third = before_source
    first_vector = _sub(source_second, origin)
    second_vector = _sub(source_third, origin)
    normal = _cross(first_vector, second_vector)
    if _dot(normal, normal) == 0:
        return ChenSourceTriangleFragmentResult(False, "degenerate_source_triangle", (), (), Fraction(0), True, False)
    barycentric_at_origin = _barycentric_coordinates(origin, before_tet)
    barycentric_at_first = _barycentric_coordinates(_add(origin, first_vector), before_tet)
    barycentric_at_second = _barycentric_coordinates(_add(origin, second_vector), before_tet)
    if (
        barycentric_at_origin is None
        or barycentric_at_first is None
        or barycentric_at_second is None
    ):
        return ChenSourceTriangleFragmentResult(False, "barycentric_setup_failed", (), (), Fraction(0), True, False)
    polygon: tuple[ParameterPoint, ...] = (
        (Fraction(0), Fraction(0)),
        (Fraction(1), Fraction(0)),
        (Fraction(0), Fraction(1)),
    )
    for index in range(4):
        polygon = _clip_half_plane(
            polygon,
            (
                barycentric_at_origin[index],
                barycentric_at_first[index] - barycentric_at_origin[index],
                barycentric_at_second[index] - barycentric_at_origin[index],
            ),
        )
        if len(polygon) < 3:
            return ChenSourceTriangleFragmentResult(
                False, "source_triangle_has_no_positive_area_inside_parent", (), (), Fraction(0), True, False
            )
    area = _double_area(polygon)
    if area <= 0:
        return ChenSourceTriangleFragmentResult(
            False, "source_triangle_has_no_positive_area_inside_parent", (), (), area, True, False
        )
    vertices = tuple(_parameter_point(origin, first_vector, second_vector, parameter) for parameter in polygon)
    unchanged = (
        before_tet == tuple(_point(point) for point in tetrahedron)
        and before_source == tuple(_point(point) for point in source_triangle)
    )
    return ChenSourceTriangleFragmentResult(
        unchanged,
        "accepted" if unchanged else "source_input_changed",
        polygon if unchanged else (),
        vertices if unchanged else (),
        area,
        unchanged,
        False,
    )
