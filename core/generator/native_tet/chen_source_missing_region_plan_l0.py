"""Read-only missing-source-subface plan for constrained facet recovery.

Si--Gärtner facet recovery operates on a connected region of missing 2-D CDT
subfaces, never on an unconstrained whole source triangle.  This L0 module
proves only that immutable precondition.  It deliberately neither removes a
tetrahedron nor chooses a cavity tetrahedralization.
"""

from __future__ import annotations

from collections import Counter
from collections.abc import Sequence
from dataclasses import dataclass
from fractions import Fraction

from core.generator.native_tet.chen_penetration_l0 import _cross, _dot, _point, _sub
from core.generator.native_tet.chen_source_subdivision_l0 import (
    audit_source_triangle_subdivision_l1,
)

Point = tuple[Fraction, Fraction, Fraction]
Edge = tuple[int, int]
Face = tuple[int, int, int]
Tet = tuple[int, int, int, int]


@dataclass(frozen=True)
class ChenSourceMissingRegionPlan:
    """Fail-closed, immutable plan for one source-facet missing region."""

    accepted: bool
    reason: str
    source_boundary_edges: tuple[Edge, ...]
    missing_interior_edges: tuple[Edge, ...]
    positive_shell_owner_ids: tuple[int, ...]
    negative_shell_owner_ids: tuple[int, ...]
    selected_side: int | None
    source_points_unchanged: bool
    production_mesh_changed: bool


def _edge(first: int, second: int) -> Edge:
    return (first, second) if first < second else (second, first)


def _tet(value: Sequence[int]) -> Tet | None:
    result = tuple(int(index) for index in value)
    if len(result) != 4 or len(set(result)) != 4:
        return None
    return result[0], result[1], result[2], result[3]


def _face(value: Sequence[int]) -> Face | None:
    result = tuple(int(index) for index in value)
    if len(result) != 3 or len(set(result)) != 3:
        return None
    return result[0], result[1], result[2]


def _tet_edges(tets: Sequence[Tet]) -> set[Edge]:
    return {
        _edge(tet[first], tet[second])
        for tet in tets
        for first in range(4)
        for second in range(first + 1, 4)
    }


def _point_on_segment(point: Point, first: Point, second: Point) -> bool:
    direction = _sub(second, first)
    offset = _sub(point, first)
    return bool(
        _cross(direction, offset) == (Fraction(0), Fraction(0), Fraction(0))
        and Fraction(0) <= _dot(offset, direction) <= _dot(direction, direction)
    )


def _is_source_boundary_edge(edge: Edge, points: Sequence[Point], source: Face) -> bool:
    first, second = (points[index] for index in edge)
    return any(
        _point_on_segment(first, points[source[index]], points[source[(index + 1) % 3]])
        and _point_on_segment(second, points[source[index]], points[source[(index + 1) % 3]])
        for index in range(3)
    )


def _owner_is_one_sided(
    tet: Tet, points: Sequence[Point], source_points: tuple[Point, Point, Point], sign: int
) -> bool:
    normal = _cross(
        _sub(source_points[1], source_points[0]),
        _sub(source_points[2], source_points[0]),
    )
    signed = tuple(_dot(normal, _sub(points[index], source_points[0])) for index in tet)
    if sign > 0:
        return bool(all(value >= 0 for value in signed) and any(value > 0 for value in signed))
    return bool(all(value <= 0 for value in signed) and any(value < 0 for value in signed))


def plan_source_missing_region_l0(
    points: Sequence[Sequence[float | int | Fraction]],
    source_face: Sequence[int],
    missing_subfaces: Sequence[Sequence[int]],
    current_tets: Sequence[Sequence[int]],
    *,
    positive_shell_owner_ids: Sequence[int],
    negative_shell_owner_ids: Sequence[int],
) -> ChenSourceMissingRegionPlan:
    """Certify the non-mutating precondition for one constrained facet region.

    The supplied owner IDs describe existing one-sided source-plane shells.
    A closed input surface must retain exactly one side: owners on both sides
    are an internal sheet, not a valid output boundary. This strict requirement
    is intentional: an intersecting tet requires a later exact region/cavity
    extraction, not a guessed L0 ownership label.
    """
    rational = tuple(_point(point) for point in points)
    before = rational
    source = _face(source_face)
    faces = tuple(_face(face) for face in missing_subfaces)
    tets = tuple(_tet(tet) for tet in current_tets)
    face_indices = tuple(index for face in (source, *faces) if face is not None for index in face)
    tet_indices = tuple(index for tet in tets if tet is not None for index in tet)
    if (
        source is None
        or not faces
        or not tets
        or any(face is None for face in faces)
        or any(tet is None for tet in tets)
        or any(index < 0 or index >= len(rational) for index in face_indices)
        or any(index < 0 or index >= len(rational) for index in tet_indices)
    ):
        return ChenSourceMissingRegionPlan(
            False, "invalid_index_input", (), (), (), (), None, True, False
        )
    typed_faces = tuple(face for face in faces if face is not None)
    typed_tets = tuple(tet for tet in tets if tet is not None)
    source_points = tuple(rational[index] for index in source)
    normal = _cross(
        _sub(source_points[1], source_points[0]),
        _sub(source_points[2], source_points[0]),
    )
    if _dot(normal, normal) == 0:
        return ChenSourceMissingRegionPlan(
            False, "degenerate_source_face", (), (), (), (), None, True, False
        )
    coverage = audit_source_triangle_subdivision_l1(rational, (source,), typed_faces)
    if not coverage.accepted:
        return ChenSourceMissingRegionPlan(
            False,
            f"subface_coverage_failed:{coverage.reason}",
            (),
            (),
            (),
            (),
            None,
            rational == before,
            False,
        )
    incidence: Counter[Edge] = Counter(
        _edge(face[index], face[(index + 1) % 3]) for face in typed_faces for index in range(3)
    )
    if any(count not in {1, 2} for count in incidence.values()):
        return ChenSourceMissingRegionPlan(
            False, "nonmanifold_subface_edge", (), (), (), (), None, rational == before, False
        )
    boundary = tuple(sorted(edge for edge, count in incidence.items() if count == 1))
    interior = tuple(sorted(edge for edge, count in incidence.items() if count == 2))
    if not boundary or any(
        not _is_source_boundary_edge(edge, rational, source) for edge in boundary
    ):
        return ChenSourceMissingRegionPlan(
            False,
            "invalid_missing_region_boundary",
            boundary,
            interior,
            (),
            (),
            None,
            rational == before,
            False,
        )
    current_edges = _tet_edges(typed_tets)
    if any(edge not in current_edges for edge in boundary):
        return ChenSourceMissingRegionPlan(
            False,
            "source_boundary_edge_missing_from_tets",
            boundary,
            interior,
            (),
            (),
            None,
            rational == before,
            False,
        )
    if any(edge in current_edges for edge in interior):
        return ChenSourceMissingRegionPlan(
            False,
            "interior_subface_edge_already_present",
            boundary,
            interior,
            (),
            (),
            None,
            rational == before,
            False,
        )
    positive = tuple(sorted({int(index) for index in positive_shell_owner_ids}))
    negative = tuple(sorted({int(index) for index in negative_shell_owner_ids}))
    if (
        (not positive and not negative)
        or set(positive) & set(negative)
        or any(index < 0 or index >= len(typed_tets) for index in (*positive, *negative))
    ):
        return ChenSourceMissingRegionPlan(
            False,
            "invalid_or_overlapping_cavity_owners",
            boundary,
            interior,
            positive,
            negative,
            None,
            rational == before,
            False,
        )
    positive_one_sided = all(
        _owner_is_one_sided(typed_tets[index], rational, source_points, 1) for index in positive
    )
    negative_one_sided = all(
        _owner_is_one_sided(typed_tets[index], rational, source_points, -1) for index in negative
    )
    if not positive_one_sided or not negative_one_sided:
        return ChenSourceMissingRegionPlan(
            False,
            "cavity_owner_not_strictly_one_sided",
            boundary,
            interior,
            positive,
            negative,
            None,
            rational == before,
            False,
        )
    if positive and negative:
        return ChenSourceMissingRegionPlan(
            False,
            "two_sided_source_shell",
            boundary,
            interior,
            positive,
            negative,
            None,
            rational == before,
            False,
        )
    unchanged = rational == before
    return ChenSourceMissingRegionPlan(
        unchanged,
        "accepted" if unchanged else "source_points_changed",
        boundary,
        interior,
        positive,
        negative,
        1 if positive else -1,
        unchanged,
        False,
    )
