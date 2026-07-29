"""Exact report-only source-triangle subdivision audit for Chen candidates."""

from __future__ import annotations

from collections import Counter
from collections.abc import Sequence
from dataclasses import dataclass
from fractions import Fraction

from core.generator.native_tet.chen_penetration_l0 import _cross, _dot, _point, _sub


@dataclass(frozen=True)
class ChenSourceSubdivisionAudit:
    accepted: bool
    reason: str
    candidate_source_owner: tuple[int, ...]
    per_source_area_vector_preserved: bool
    all_candidate_faces_have_one_source_owner: bool
    source_points_unchanged: bool
    production_mesh_changed: bool


@dataclass(frozen=True)
class ChenSourceSubdivisionCoverageAudit:
    """L1 topological coverage audit layered on the exact L0 support check.

    The L0 area-vector condition alone is intentionally insufficient: two
    copies of a half triangle can have the source's total oriented area while
    leaving the other half uncovered.  L1 therefore treats each source
    triangle as a planar complex and requires conforming edge incidence and
    an exact interval partition of all three source edges.
    """

    accepted: bool
    reason: str
    l0: ChenSourceSubdivisionAudit
    candidate_edges_conforming: bool
    interior_edge_incidence_preserved: bool
    source_boundary_edge_incidence_preserved: bool
    source_boundary_interval_partition_preserved: bool
    source_points_unchanged: bool
    production_mesh_changed: bool


Point = tuple[Fraction, Fraction, Fraction]
Edge = tuple[Point, Point]
Point2 = tuple[Fraction, Fraction]
IndexTet = tuple[int, int, int, int]
FaceIndex = tuple[int, int, int]


def oriented_boundary_faces_l1(
    points: Sequence[Point], tets: Sequence[Sequence[int]]
) -> tuple[FaceIndex, ...]:
    """Return exact outward-oriented faces with one-tet incidence only.

    This is a report primitive for the parallel subdivision certificate.  It
    does not mutate tet orientation or mesh connectivity.
    """
    typed: list[IndexTet] = []
    for tet in tets:
        vertex_values = tuple(int(value) for value in tet)
        if (
            len(vertex_values) != 4
            or len(set(vertex_values)) != 4
            or any(value < 0 or value >= len(points) for value in vertex_values)
        ):
            raise ValueError("tets must contain four distinct in-range vertices")
        typed.append((vertex_values[0], vertex_values[1], vertex_values[2], vertex_values[3]))
    owners: dict[FaceIndex, list[tuple[IndexTet, int]]] = {}
    for tet in typed:
        for omitted in range(4):
            labels = sorted(tet[index] for index in range(4) if index != omitted)
            key: FaceIndex = labels[0], labels[1], labels[2]
            owners.setdefault(key, []).append((tet, omitted))
    exterior: list[FaceIndex] = []
    for face_owners in owners.values():
        if len(face_owners) != 1:
            continue
        tet, omitted = face_owners[0]
        face_values = tuple(tet[index] for index in range(4) if index != omitted)
        face: FaceIndex = face_values[0], face_values[1], face_values[2]
        first, second, third = (points[index] for index in face)
        normal = _cross(_sub(second, first), _sub(third, first))
        if _dot(normal, _sub(points[tet[omitted]], first)) > 0:
            face = face[0], face[2], face[1]
        exterior.append(face)
    return tuple(exterior)


def _inside_or_on(
    point: tuple[Fraction, Fraction, Fraction],
    triangle: tuple[tuple[Fraction, Fraction, Fraction], ...],
) -> bool:
    origin, second, third = triangle
    first_vector, second_vector, offset = (
        _sub(second, origin),
        _sub(third, origin),
        _sub(point, origin),
    )
    aa, ab, bb = (
        _dot(first_vector, first_vector),
        _dot(first_vector, second_vector),
        _dot(second_vector, second_vector),
    )
    determinant = aa * bb - ab * ab
    if determinant == 0:
        return False
    first = (_dot(offset, first_vector) * bb - _dot(offset, second_vector) * ab) / determinant
    second_coefficient = (
        _dot(offset, second_vector) * aa - _dot(offset, first_vector) * ab
    ) / determinant
    return bool(first >= 0 and second_coefficient >= 0 and first + second_coefficient <= 1)


def audit_source_triangle_subdivision_l0(
    points: Sequence[Sequence[float | int | Fraction]],
    source_faces: Sequence[Sequence[int]],
    candidate_boundary_faces: Sequence[Sequence[int]],
) -> ChenSourceSubdivisionAudit:
    """Require exact single-source support and per-source area-vector equality."""
    rational = tuple(_point(point) for point in points)
    before = rational
    try:
        sources = tuple(tuple(int(vertex) for vertex in face) for face in source_faces)
        candidates = tuple(
            tuple(int(vertex) for vertex in face) for face in candidate_boundary_faces
        )
        if (
            not sources
            or not candidates
            or any(len(set(face)) != 3 for face in (*sources, *candidates))
        ):
            raise ValueError
        if any(
            vertex < 0 or vertex >= len(rational)
            for face in (*sources, *candidates)
            for vertex in face
        ):
            raise ValueError
    except ValueError:
        return ChenSourceSubdivisionAudit(
            False, "invalid_face_input", (), False, False, True, False
        )
    source_triangles = tuple(tuple(rational[index] for index in face) for face in sources)
    normals = tuple(
        _cross(_sub(face[1], face[0]), _sub(face[2], face[0])) for face in source_triangles
    )
    if any(_dot(normal, normal) == 0 for normal in normals):
        return ChenSourceSubdivisionAudit(
            False, "degenerate_source_face", (), False, False, True, False
        )
    owners: list[int] = []
    sums = [(Fraction(0), Fraction(0), Fraction(0)) for _ in sources]
    for candidate in candidates:
        triangle = tuple(rational[index] for index in candidate)
        vector = _cross(_sub(triangle[1], triangle[0]), _sub(triangle[2], triangle[0]))
        matching = [
            index
            for index, source in enumerate(source_triangles)
            if all(
                _dot(normals[index], _sub(point, source[0])) == 0 and _inside_or_on(point, source)
                for point in triangle
            )
        ]
        if len(matching) != 1:
            return ChenSourceSubdivisionAudit(
                False,
                "candidate_not_on_exactly_one_source_face",
                (),
                False,
                False,
                rational == before,
                False,
            )
        owner = matching[0]
        if _dot(vector, normals[owner]) <= 0:
            return ChenSourceSubdivisionAudit(
                False,
                "candidate_orientation_not_source_aligned",
                (),
                False,
                False,
                rational == before,
                False,
            )
        owners.append(owner)
        sums[owner] = tuple(left + right for left, right in zip(sums[owner], vector, strict=True))
    area_preserved = all(total == normal for total, normal in zip(sums, normals, strict=True))
    unchanged = rational == before
    return ChenSourceSubdivisionAudit(
        area_preserved and unchanged,
        "accepted" if area_preserved and unchanged else "source_area_partition_failed",
        tuple(owners),
        area_preserved,
        True,
        unchanged,
        False,
    )


def _canonical_edge(first: Point, second: Point) -> Edge:
    return (first, second) if first <= second else (second, first)


def _project_to_source_plane(point: Point, normal: Point) -> Point2:
    """Drop the dominant normal axis; this is injective on the source plane."""
    axis = max(range(3), key=lambda index: abs(normal[index]))
    return tuple(value for index, value in enumerate(point) if index != axis)  # type: ignore[return-value]


def _orientation_2d(first: Point2, second: Point2, third: Point2) -> Fraction:
    return (second[0] - first[0]) * (third[1] - first[1]) - (second[1] - first[1]) * (
        third[0] - first[0]
    )


def _point_on_segment_2d(point: Point2, first: Point2, second: Point2) -> bool:
    return (
        _orientation_2d(first, second, point) == 0
        and min(first[0], second[0]) <= point[0] <= max(first[0], second[0])
        and min(first[1], second[1]) <= point[1] <= max(first[1], second[1])
    )


def _edges_cross_or_overlap(first: Edge, second: Edge, normal: Point) -> bool:
    """Reject crossings, T-junctions, and positive-length partial overlaps."""
    if first == second:
        return False
    a, b = (_project_to_source_plane(point, normal) for point in first)
    c, d = (_project_to_source_plane(point, normal) for point in second)
    orientations = (
        _orientation_2d(a, b, c),
        _orientation_2d(a, b, d),
        _orientation_2d(c, d, a),
        _orientation_2d(c, d, b),
    )
    if all(value == 0 for value in orientations):
        first_axis = 0 if a[0] != b[0] else 1
        overlap_lower = max(min(a[first_axis], b[first_axis]), min(c[first_axis], d[first_axis]))
        overlap_upper = min(max(a[first_axis], b[first_axis]), max(c[first_axis], d[first_axis]))
        return overlap_lower < overlap_upper
    if orientations[0] * orientations[1] < 0 and orientations[2] * orientations[3] < 0:
        return True
    for point, own_first, own_second, other_first, other_second in (
        (a, a, b, c, d),
        (b, a, b, c, d),
        (c, c, d, a, b),
        (d, c, d, a, b),
    ):
        if _point_on_segment_2d(point, other_first, other_second) and point not in (
            other_first,
            other_second,
        ):
            return True
    return False


def _edge_on_source_side(edge: Edge, side: Edge, normal: Point) -> tuple[Fraction, Fraction] | None:
    """Return the exact side interval when ``edge`` lies wholly on ``side``."""
    source_first, source_second = side
    direction = _sub(source_second, source_first)
    denominator = _dot(direction, direction)
    if denominator == 0:
        return None
    parameters: list[Fraction] = []
    for point in edge:
        if _cross(direction, _sub(point, source_first)) != (Fraction(0),) * 3:
            return None
        parameter = _dot(_sub(point, source_first), direction) / denominator
        if not 0 <= parameter <= 1:
            return None
        parameters.append(parameter)
    lower, upper = sorted(parameters)
    return (lower, upper) if lower < upper else None


def _intervals_partition_source_side(intervals: Sequence[tuple[Fraction, Fraction]]) -> bool:
    """Require a gap-free, non-overlapping exact partition of [0, 1]."""
    ordered = sorted(intervals)
    if not ordered or ordered[0][0] != 0 or ordered[-1][1] != 1:
        return False
    return all(left[1] == right[0] for left, right in zip(ordered, ordered[1:], strict=False))


def audit_source_triangle_subdivision_l1(
    points: Sequence[Sequence[float | int | Fraction]],
    source_faces: Sequence[Sequence[int]],
    candidate_boundary_faces: Sequence[Sequence[int]],
) -> ChenSourceSubdivisionCoverageAudit:
    """Certify a conforming, exactly covering source-triangle subdivision.

    This is report-only.  It deliberately does not relax the permanent raw
    boundary-face identity gate or mutate any production mesh state.
    """
    l0 = audit_source_triangle_subdivision_l0(points, source_faces, candidate_boundary_faces)
    if not l0.accepted:
        return ChenSourceSubdivisionCoverageAudit(
            False, l0.reason, l0, False, False, False, False, l0.source_points_unchanged, False
        )
    rational = tuple(_point(point) for point in points)
    sources = tuple(tuple(int(vertex) for vertex in face) for face in source_faces)
    candidates = tuple(tuple(int(vertex) for vertex in face) for face in candidate_boundary_faces)
    source_triangles = tuple(tuple(rational[index] for index in face) for face in sources)
    normals = tuple(
        _cross(_sub(face[1], face[0]), _sub(face[2], face[0])) for face in source_triangles
    )
    owner_edges: list[list[Edge]] = [[] for _ in sources]
    for candidate, owner in zip(candidates, l0.candidate_source_owner, strict=True):
        triangle = tuple(rational[index] for index in candidate)
        owner_edges[owner].extend(
            _canonical_edge(triangle[index], triangle[(index + 1) % 3]) for index in range(3)
        )
    for owner, edges in enumerate(owner_edges):
        for index, first in enumerate(edges):
            if any(
                _edges_cross_or_overlap(first, second, normals[owner])
                for second in edges[index + 1 :]
            ):
                return ChenSourceSubdivisionCoverageAudit(
                    False,
                    "candidate_edges_cross_or_overlap",
                    l0,
                    False,
                    False,
                    False,
                    False,
                    True,
                    False,
                )
    interior_incidence = True
    boundary_incidence = True
    interval_partition = True
    for owner, edges in enumerate(owner_edges):
        triangle = source_triangles[owner]
        sides = tuple(
            _canonical_edge(triangle[index], triangle[(index + 1) % 3]) for index in range(3)
        )
        counts = Counter(edges)
        intervals: list[list[tuple[Fraction, Fraction]]] = [[], [], []]
        for edge, count in counts.items():
            matching_sides = [
                (side_index, _edge_on_source_side(edge, side, normals[owner]))
                for side_index, side in enumerate(sides)
            ]
            matching_sides = [item for item in matching_sides if item[1] is not None]
            if matching_sides:
                if len(matching_sides) != 1 or count != 1:
                    boundary_incidence = False
                    continue
                side_index, interval = matching_sides[0]
                assert interval is not None
                intervals[side_index].append(interval)
            elif count != 2:
                interior_incidence = False
        interval_partition = interval_partition and all(
            _intervals_partition_source_side(side_intervals) for side_intervals in intervals
        )
    accepted = interior_incidence and boundary_incidence and interval_partition
    reason = "accepted"
    if not interior_incidence:
        reason = "interior_edge_incidence_failed"
    elif not boundary_incidence:
        reason = "source_boundary_edge_incidence_failed"
    elif not interval_partition:
        reason = "source_boundary_interval_partition_failed"
    return ChenSourceSubdivisionCoverageAudit(
        accepted,
        reason,
        l0,
        True,
        interior_incidence,
        boundary_incidence,
        interval_partition,
        l0.source_points_unchanged,
        False,
    )
