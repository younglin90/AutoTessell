"""Exact five-way Chen--Zheng clusterel-node predicate, test-only.

Chen's facet state distinguishes a missing intersection from a point on the
extension, beginning, end, or interior of a local tetrahedron edge.  The
earlier strict-only ledger deliberately could not describe a recovered source
edge because its endpoint contacts were rejected.  This L0 oracle records the
five documented states without choosing a decomposition or mutating a mesh.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from fractions import Fraction
from typing import Literal

from core.generator.native_tet.chen_penetration_l0 import RationalPoint, _cross, _dot, _point, _sub
from core.generator.native_tet.chen_pipe_cluster_l0 import _orient6

ChenNodeType = Literal["NOD_NUL", "NOD_EXT", "NOD_BEG", "NOD_END", "NOD_MID"]
LocalEdge = tuple[int, int]
_LOCAL_EDGES: tuple[LocalEdge, ...] = ((0, 1), (0, 2), (0, 3), (1, 2), (1, 3), (2, 3))


@dataclass(frozen=True)
class ChenClusterelEdgeNode:
    """One local-edge intersection state, with an exact point when present."""

    local_edge: LocalEdge
    node_type: ChenNodeType
    point: RationalPoint | None
    line_parameter: Fraction | None


@dataclass(frozen=True)
class ChenClusterelNodeStateResult:
    """Fail-closed node ledger; ambiguity exposes no partial node records."""

    accepted: bool
    reason: str
    nodes: tuple[ChenClusterelEdgeNode, ...]
    source_points_unchanged: bool
    production_mesh_changed: bool


def _add(first: RationalPoint, second: RationalPoint) -> RationalPoint:
    return first[0] + second[0], first[1] + second[1], first[2] + second[2]


def _scale(value: Fraction, vector: RationalPoint) -> RationalPoint:
    return value * vector[0], value * vector[1], value * vector[2]


def _inside_or_on_triangle(point: RationalPoint, triangle: tuple[RationalPoint, ...]) -> bool:
    origin, second, third = triangle
    first_vector, second_vector, offset = _sub(second, origin), _sub(third, origin), _sub(point, origin)
    first_norm = _dot(first_vector, first_vector)
    mixed = _dot(first_vector, second_vector)
    second_norm = _dot(second_vector, second_vector)
    determinant = first_norm * second_norm - mixed * mixed
    if determinant == 0:
        return False
    first_parameter = (
        _dot(offset, first_vector) * second_norm - _dot(offset, second_vector) * mixed
    ) / determinant
    second_parameter = (
        _dot(offset, second_vector) * first_norm - _dot(offset, first_vector) * mixed
    ) / determinant
    return bool(
        first_parameter >= 0
        and second_parameter >= 0
        and first_parameter + second_parameter <= 1
        and _dot(_sub(point, origin), _cross(first_vector, second_vector)) == 0
    )


def _point_on_segment(point: RationalPoint, start: RationalPoint, end: RationalPoint) -> bool:
    direction, offset = _sub(end, start), _sub(point, start)
    coordinate = next((index for index, value in enumerate(direction) if value != 0), None)
    if coordinate is None:
        return bool(point == start)
    parameter = offset[coordinate] / direction[coordinate]
    return Fraction(0) <= parameter <= Fraction(1) and all(
        offset[index] == parameter * direction[index] for index in range(3)
    )


def _is_source_boundary_segment(
    start: RationalPoint, end: RationalPoint, triangle: tuple[RationalPoint, ...]
) -> bool:
    return any(
        _point_on_segment(start, triangle[index], triangle[(index + 1) % 3])
        and _point_on_segment(end, triangle[index], triangle[(index + 1) % 3])
        for index in range(3)
    )


def classify_clusterel_node_states_l0(
    tetrahedron: Sequence[Sequence[float | int | Fraction]],
    source_triangle: Sequence[Sequence[float | int | Fraction]],
) -> ChenClusterelNodeStateResult:
    """Classify all six local-edge states against one finite source triangle."""
    if len(tetrahedron) != 4 or len(source_triangle) != 3:
        raise ValueError("one tetrahedron and one source triangle are required")
    tet = tuple(_point(point) for point in tetrahedron)
    source = tuple(_point(point) for point in source_triangle)
    unchanged = tet == tuple(_point(point) for point in tetrahedron) and source == tuple(
        _point(point) for point in source_triangle
    )
    if len(set(tet)) != 4 or _orient6(tet, (0, 1, 2, 3)) == 0:
        return ChenClusterelNodeStateResult(False, "degenerate_clusterel_tetrahedron", (), unchanged, False)
    normal = _cross(_sub(source[1], source[0]), _sub(source[2], source[0]))
    if _dot(normal, normal) == 0:
        return ChenClusterelNodeStateResult(False, "degenerate_source_triangle", (), unchanged, False)
    nodes: list[ChenClusterelEdgeNode] = []
    for edge in _LOCAL_EDGES:
        start, end = tet[edge[0]], tet[edge[1]]
        direction = _sub(end, start)
        numerator = -_dot(normal, _sub(start, source[0]))
        denominator = _dot(normal, direction)
        if denominator == 0:
            if numerator == 0 and not _is_source_boundary_segment(start, end, source):
                if _inside_or_on_triangle(start, source) or _inside_or_on_triangle(end, source):
                    return ChenClusterelNodeStateResult(
                        False, "coplanar_interior_edge_overlap", (), unchanged, False
                    )
            nodes.append(ChenClusterelEdgeNode(edge, "NOD_NUL", None, None))
            continue
        parameter = numerator / denominator
        point = _add(start, _scale(parameter, direction))
        if not _inside_or_on_triangle(point, source):
            nodes.append(ChenClusterelEdgeNode(edge, "NOD_NUL", None, None))
        elif parameter < 0 or parameter > 1:
            nodes.append(ChenClusterelEdgeNode(edge, "NOD_EXT", point, parameter))
        elif parameter == 0:
            nodes.append(ChenClusterelEdgeNode(edge, "NOD_BEG", point, parameter))
        elif parameter == 1:
            nodes.append(ChenClusterelEdgeNode(edge, "NOD_END", point, parameter))
        else:
            nodes.append(ChenClusterelEdgeNode(edge, "NOD_MID", point, parameter))
    return ChenClusterelNodeStateResult(True, "accepted", tuple(nodes), unchanged, False)
