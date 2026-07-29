"""Exact read-only ownership ledger for Chen boundary-aligned source segments.

An NOD_EDG source segment can lie in a tetrahedron facet rather than traverse a
tetrahedron interior.  It must then be owned by the *facet* and its one or two
incident tetrahedra, never arbitrarily assigned to one interior pipel.  This
module identifies that incidence exactly and classifies the endpoint pair for
each owner without changing mesh connectivity.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from fractions import Fraction

from core.generator.native_tet.chen_penetration_l0 import RationalPoint, _point
from core.generator.native_tet.chen_pipel_type_l0 import ChenPipelTypeResult, classify_pipel_type

IndexTet = tuple[int, int, int, int]
FaceKey = tuple[int, int, int]


@dataclass(frozen=True)
class ChenBoundaryAlignedIncidence:
    """One source segment contained in one unique tetrahedral facet."""

    face: FaceKey
    owner_tets: tuple[int, ...]
    owner_pipel_types: tuple[ChenPipelTypeResult, ...]


@dataclass(frozen=True)
class ChenBoundaryAlignedResult:
    """Fail-closed boundary-aligned result; rejection exposes no incidence."""

    accepted: bool
    reason: str
    incidence: ChenBoundaryAlignedIncidence | None


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


def _face_key(vertices: Sequence[int]) -> FaceKey:
    ordered = sorted(int(vertex) for vertex in vertices)
    if len(ordered) != 3 or len(set(ordered)) != 3:
        raise ValueError("a face must contain three distinct vertices")
    return ordered[0], ordered[1], ordered[2]


def _as_tet(tet: Sequence[int]) -> IndexTet | None:
    values = tuple(int(vertex) for vertex in tet)
    if len(values) != 4 or len(set(values)) != 4:
        return None
    return values[0], values[1], values[2], values[3]


def _tet_faces(tet: IndexTet) -> tuple[FaceKey, FaceKey, FaceKey, FaceKey]:
    faces = [
        _face_key(tuple(tet[index] for index in range(4) if index != omitted))
        for omitted in range(4)
    ]
    return faces[0], faces[1], faces[2], faces[3]


def _in_or_on_triangle(
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
    gamma = Fraction(1) - alpha - beta
    return alpha >= 0 and beta >= 0 and gamma >= 0


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
    gamma = Fraction(1) - alpha - beta
    return alpha > 0 and beta > 0 and gamma > 0


def _segment_is_in_face(
    start: RationalPoint,
    end: RationalPoint,
    triangle: tuple[RationalPoint, RationalPoint, RationalPoint],
) -> bool:
    normal = _cross(_sub(triangle[1], triangle[0]), _sub(triangle[2], triangle[0]))
    if _dot(normal, normal) == 0:
        return False
    return (
        _dot(normal, _sub(start, triangle[0])) == 0
        and _dot(normal, _sub(end, triangle[0])) == 0
        and _in_or_on_triangle(start, triangle)
        and _in_or_on_triangle(end, triangle)
    )


def _segment_is_strictly_in_face_interior(
    start: RationalPoint,
    end: RationalPoint,
    triangle: tuple[RationalPoint, RationalPoint, RationalPoint],
) -> bool:
    """Require a unique facet segment to avoid the lower-dimensional edge case."""
    midpoint = (
        (start[0] + end[0]) / 2,
        (start[1] + end[1]) / 2,
        (start[2] + end[2]) / 2,
    )
    return _strictly_inside_triangle(midpoint, triangle)


def classify_boundary_aligned_source_segment(
    points: Sequence[Sequence[float | int | Fraction]],
    parent_tets: Sequence[Sequence[int]],
    source_start: Sequence[float | int | Fraction],
    source_end: Sequence[float | int | Fraction],
) -> ChenBoundaryAlignedResult:
    """Return the unique facet ownership of a boundary-aligned source segment."""
    rational_points = tuple(_point(point) for point in points)
    start, end = _point(source_start), _point(source_end)
    if start == end:
        return ChenBoundaryAlignedResult(False, "zero_length_source_segment", None)
    raw_tets = tuple(_as_tet(tet) for tet in parent_tets)
    if not raw_tets or any(tet is None for tet in raw_tets):
        return ChenBoundaryAlignedResult(False, "invalid_parent_tetrahedron", None)
    tets = tuple(tet for tet in raw_tets if tet is not None)
    if any(vertex < 0 or vertex >= len(rational_points) for tet in tets for vertex in tet):
        return ChenBoundaryAlignedResult(False, "parent_index_out_of_range", None)
    owners: dict[FaceKey, list[int]] = {}
    matching_faces: set[FaceKey] = set()
    for tet_index, tet in enumerate(tets):
        for face in _tet_faces(tet):
            owners.setdefault(face, []).append(tet_index)
            triangle = (
                rational_points[face[0]],
                rational_points[face[1]],
                rational_points[face[2]],
            )
            if _segment_is_in_face(start, end, triangle):
                matching_faces.add(face)
    if not matching_faces:
        return ChenBoundaryAlignedResult(False, "source_segment_not_boundary_aligned", None)
    if len(matching_faces) != 1:
        return ChenBoundaryAlignedResult(False, "segment_is_not_on_one_unique_face", None)
    face = next(iter(matching_faces))
    triangle = (
        rational_points[face[0]],
        rational_points[face[1]],
        rational_points[face[2]],
    )
    if not _segment_is_strictly_in_face_interior(start, end, triangle):
        return ChenBoundaryAlignedResult(False, "segment_is_not_in_facet_interior", None)
    face_owners = tuple(owners[face])
    if len(face_owners) not in {1, 2}:
        return ChenBoundaryAlignedResult(False, "boundary_face_is_nonmanifold", None)
    pipel_types = tuple(
        classify_pipel_type(tuple(rational_points[vertex] for vertex in tets[owner]), start, end)
        for owner in face_owners
    )
    if not all(result.accepted for result in pipel_types):
        return ChenBoundaryAlignedResult(False, "boundary_aligned_type_is_unsupported", None)
    return ChenBoundaryAlignedResult(
        True,
        "accepted",
        ChenBoundaryAlignedIncidence(face, face_owners, pipel_types),
    )
