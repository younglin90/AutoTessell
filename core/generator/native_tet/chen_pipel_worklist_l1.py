"""Read-only exact traversal of one Chen--Zheng missing-edge pipel.

This L1 prerequisite deliberately stops before any recovery template is
applied.  It proves that a constraint-edge segment has one deterministic,
non-degenerate walk through adjacent tetrahedra: every crossing is through one
interior shared face, belongs to one ordered pair of tetrahedra, and the
unchanged input connectivity retains its exterior boundary.  A later card may
combine this worklist with the Table-5/Phi transactions; it must not treat this
read-only traversal as source-edge recovery.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from fractions import Fraction

from core.generator.native_tet.chen_penetration_l0 import (
    RationalPoint,
    strict_segment_triangle_intersection,
)
from core.generator.native_tet.chen_pipe_cluster_l0 import IndexTet, _point

FaceKey = tuple[int, int, int]


@dataclass(frozen=True)
class ChenPipelTraversalResult:
    """Exact, read-only source-segment traversal certificate."""

    accepted: bool
    reason: str
    visited_tets: tuple[int, ...]
    crossed_faces: tuple[FaceKey, ...]
    crossing_parameters: tuple[Fraction, ...]
    input_boundary_unchanged: bool


def _face_key(vertices: Sequence[int]) -> FaceKey:
    ordered = sorted(int(vertex) for vertex in vertices)
    if len(ordered) != 3 or len(set(ordered)) != 3:
        raise ValueError("a face must contain three distinct vertices")
    return ordered[0], ordered[1], ordered[2]


def _face_owners(tets: Sequence[IndexTet]) -> dict[FaceKey, tuple[int, ...]]:
    owners: dict[FaceKey, list[int]] = {}
    for tet_index, tet in enumerate(tets):
        for omitted in range(4):
            face = _face_key(tuple(tet[index] for index in range(4) if index != omitted))
            owners.setdefault(face, []).append(tet_index)
    return {face: tuple(indices) for face, indices in owners.items()}


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


def _strictly_inside_tet(
    point: RationalPoint, tet: IndexTet, points: Sequence[RationalPoint]
) -> bool:
    first, second, third, fourth = (points[index] for index in tet)
    denominator = _orient6_points(first, second, third, fourth)
    if denominator == 0:
        return False
    numerators = (
        _orient6_points(point, second, third, fourth),
        _orient6_points(first, point, third, fourth),
        _orient6_points(first, second, point, fourth),
        _orient6_points(first, second, third, point),
    )
    return all(numerator / denominator > 0 for numerator in numerators)


def _segment_parameter(
    start: RationalPoint, end: RationalPoint, point: RationalPoint
) -> Fraction | None:
    direction = _sub(end, start)
    offset = _sub(point, start)
    coordinate = next((index for index, value in enumerate(direction) if value != 0), None)
    if coordinate is None:
        return None
    parameter = offset[coordinate] / direction[coordinate]
    return (
        parameter
        if all(offset[index] == parameter * direction[index] for index in range(3))
        else None
    )


def certify_source_edge_pipel_traversal(
    points: Sequence[Sequence[float | int | Fraction]],
    parent_tets: Sequence[Sequence[int]],
    source_start: Sequence[float | int | Fraction],
    source_end: Sequence[float | int | Fraction],
) -> ChenPipelTraversalResult:
    """Certify a unique ordered interior-face walk, without changing a mesh."""
    rational_points = tuple(_point(point) for point in points)
    start, end = _point(source_start), _point(source_end)
    if start == end:
        return ChenPipelTraversalResult(False, "zero_length_source_edge", (), (), (), True)
    raw_tets = tuple(tuple(int(vertex) for vertex in tet) for tet in parent_tets)
    if not raw_tets or any(len(tet) != 4 or len(set(tet)) != 4 for tet in raw_tets):
        return ChenPipelTraversalResult(False, "invalid_parent_tetrahedron", (), (), (), True)
    if any(vertex < 0 or vertex >= len(rational_points) for tet in raw_tets for vertex in tet):
        return ChenPipelTraversalResult(False, "parent_index_out_of_range", (), (), (), True)
    tets: tuple[IndexTet, ...] = tuple((tet[0], tet[1], tet[2], tet[3]) for tet in raw_tets)
    start_owners = tuple(
        index for index, tet in enumerate(tets) if _strictly_inside_tet(start, tet, rational_points)
    )
    end_owners = tuple(
        index for index, tet in enumerate(tets) if _strictly_inside_tet(end, tet, rational_points)
    )
    if len(start_owners) != 1 or len(end_owners) != 1:
        return ChenPipelTraversalResult(
            False, "source_endpoints_must_have_unique_interior_owner", (), (), (), True
        )

    face_owners = _face_owners(tets)
    crossings: list[tuple[Fraction, FaceKey]] = []
    for face, owners in face_owners.items():
        if len(owners) != 2:
            continue
        triangle = tuple(rational_points[index] for index in face)
        intersection = strict_segment_triangle_intersection(start, end, triangle)
        if intersection is None:
            continue
        parameter = _segment_parameter(start, end, intersection)
        if parameter is None or not Fraction(0) < parameter < Fraction(1):
            return ChenPipelTraversalResult(False, "non_open_crossing_parameter", (), (), (), True)
        crossings.append((parameter, face))
    crossings.sort()
    if len({parameter for parameter, _face in crossings}) != len(crossings):
        return ChenPipelTraversalResult(False, "ambiguous_multi_face_crossing", (), (), (), True)

    current = start_owners[0]
    visited = [current]
    crossed_faces: list[FaceKey] = []
    parameters: list[Fraction] = []
    for parameter, face in crossings:
        owners = face_owners[face]
        if current not in owners:
            return ChenPipelTraversalResult(
                False, "crossing_not_adjacent_to_current_pipel", (), (), (), True
            )
        next_owner = owners[0] if owners[1] == current else owners[1]
        current = next_owner
        visited.append(current)
        crossed_faces.append(face)
        parameters.append(parameter)
    if current != end_owners[0]:
        return ChenPipelTraversalResult(
            False, "traversal_does_not_reach_end_owner", (), (), (), True
        )

    # The module only observes immutable inputs.  Count faces to make that
    # statement explicit and protect future refactors from returning a mutated
    # worklist object in place of the original tetrahedra.
    before_boundary = frozenset(face for face, owners in face_owners.items() if len(owners) == 1)
    after_boundary = frozenset(
        face for face, owners in _face_owners(tets).items() if len(owners) == 1
    )
    return ChenPipelTraversalResult(
        True,
        "accepted",
        tuple(visited),
        tuple(crossed_faces),
        tuple(parameters),
        before_boundary == after_boundary,
    )
