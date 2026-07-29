"""Test-only exact certificate for Chen-2011's local pipe precondition.

The 2-to-3 swap is the smallest multi-tet transaction that recovers a missing
source edge through a shared triangular face.  It is intentionally separate
from Chen's Steiner-point face-penetration templates: this module only proves
the local cluster's topology, orientation, volume, and exterior-boundary
identity before any production recovery path may use a template.
"""

from __future__ import annotations

from collections import Counter
from collections.abc import Sequence
from dataclasses import dataclass
from fractions import Fraction

from core.generator.native_tet.chen_penetration_l0 import strict_segment_triangle_intersection

IndexTet = tuple[int, int, int, int]


@dataclass(frozen=True)
class ChenPipeClusterResult:
    """Certificate result; a rejected result contains no replacement tets."""

    accepted: bool
    reason: str
    replacement_tets: tuple[IndexTet, ...]
    parent_volume6: Fraction
    replacement_volume6: Fraction
    external_boundary_preserved: bool
    recovered_source_edge: bool


def _point(point: Sequence[float | int | Fraction]) -> tuple[Fraction, Fraction, Fraction]:
    if len(point) != 3:
        raise ValueError("each point must have three coordinates")
    return tuple(
        (
            value
            if isinstance(value, Fraction)
            else Fraction(value) if isinstance(value, int) else Fraction.from_float(value)
        )
        for value in point
    )  # type: ignore[return-value]


def _sub(
    first: tuple[Fraction, Fraction, Fraction], second: tuple[Fraction, Fraction, Fraction]
) -> tuple[Fraction, Fraction, Fraction]:
    return tuple(a - b for a, b in zip(first, second, strict=True))  # type: ignore[return-value]


def _cross(
    first: tuple[Fraction, Fraction, Fraction], second: tuple[Fraction, Fraction, Fraction]
) -> tuple[Fraction, Fraction, Fraction]:
    return (
        first[1] * second[2] - first[2] * second[1],
        first[2] * second[0] - first[0] * second[2],
        first[0] * second[1] - first[1] * second[0],
    )


def _orient6(points: Sequence[tuple[Fraction, Fraction, Fraction]], tet: IndexTet) -> Fraction:
    first, second, third, fourth = (points[index] for index in tet)
    delta_second = _sub(second, first)
    delta_third = _sub(third, first)
    delta_fourth = _sub(fourth, first)
    return sum(
        (
            left * right
            for left, right in zip(delta_second, _cross(delta_third, delta_fourth), strict=True)
        ),
        Fraction(0),
    )


def _positive_orientation(
    points: Sequence[tuple[Fraction, Fraction, Fraction]], tet: IndexTet
) -> IndexTet | None:
    orientation = _orient6(points, tet)
    if orientation > 0:
        return tet
    if orientation < 0:
        flipped = (tet[1], tet[0], tet[2], tet[3])
        return flipped if _orient6(points, flipped) > 0 else None
    return None


def _boundary_keys(tets: Sequence[IndexTet]) -> frozenset[tuple[int, int, int]]:
    face_counts: Counter[tuple[int, int, int]] = Counter()
    for tet in tets:
        for omitted in range(4):
            face_values = sorted(tet[index] for index in range(4) if index != omitted)
            face = (face_values[0], face_values[1], face_values[2])
            face_counts[face] += 1
    return frozenset(face for face, count in face_counts.items() if count == 1)


def _contains_edge(tets: Sequence[IndexTet], edge: tuple[int, int]) -> bool:
    first, second = edge
    return any(first in tet and second in tet for tet in tets)


def certify_swap23_pipe_cluster(
    points: Sequence[Sequence[float | int | Fraction]],
    parent_tets: Sequence[Sequence[int]],
    source_edge: tuple[int, int],
) -> ChenPipeClusterResult:
    """Certify, but do not apply, the local 2-to-3 missing-edge transaction."""
    if len(parent_tets) != 2:
        raise ValueError("a 2-to-3 pipe cluster requires exactly two parent tetrahedra")
    rational_points = tuple(_point(point) for point in points)
    raw_parents = tuple(tuple(int(vertex) for vertex in tet) for tet in parent_tets)
    if any(len(tet) != 4 or len(set(tet)) != 4 for tet in raw_parents):
        return ChenPipeClusterResult(
            False, "invalid_parent_tetrahedron", (), Fraction(0), Fraction(0), False, False
        )
    parents: tuple[IndexTet, IndexTet] = (
        (raw_parents[0][0], raw_parents[0][1], raw_parents[0][2], raw_parents[0][3]),
        (raw_parents[1][0], raw_parents[1][1], raw_parents[1][2], raw_parents[1][3]),
    )
    if any(vertex < 0 or vertex >= len(rational_points) for tet in parents for vertex in tet):
        return ChenPipeClusterResult(
            False, "parent_index_out_of_range", (), Fraction(0), Fraction(0), False, False
        )
    source_first, source_second = int(source_edge[0]), int(source_edge[1])
    edge: tuple[int, int] = (
        min(source_first, source_second),
        max(source_first, source_second),
    )
    if edge[0] == edge[1] or any(vertex < 0 or vertex >= len(rational_points) for vertex in edge):
        return ChenPipeClusterResult(
            False, "invalid_source_edge", (), Fraction(0), Fraction(0), False, False
        )
    if _contains_edge(parents, edge):
        return ChenPipeClusterResult(
            False, "source_edge_already_present", (), Fraction(0), Fraction(0), False, True
        )

    shared = tuple(sorted(set(parents[0]).intersection(parents[1])))
    if len(shared) != 3:
        return ChenPipeClusterResult(
            False, "parents_do_not_share_one_face", (), Fraction(0), Fraction(0), False, False
        )
    opposite = tuple(next(vertex for vertex in tet if vertex not in shared) for tet in parents)
    if tuple(sorted(opposite)) != edge:
        return ChenPipeClusterResult(
            False,
            "source_edge_must_join_opposite_vertices",
            (),
            Fraction(0),
            Fraction(0),
            False,
            False,
        )
    shared_triangle = tuple(rational_points[index] for index in shared)
    if (
        strict_segment_triangle_intersection(
            rational_points[opposite[0]], rational_points[opposite[1]], shared_triangle
        )
        is None
    ):
        return ChenPipeClusterResult(
            False,
            "source_edge_must_cross_shared_face_strictly",
            (),
            Fraction(0),
            Fraction(0),
            False,
            False,
        )

    parent_volume6 = sum((abs(_orient6(rational_points, tet)) for tet in parents), Fraction(0))
    raw_children = (
        (shared[0], shared[1], opposite[0], opposite[1]),
        (shared[1], shared[2], opposite[0], opposite[1]),
        (shared[2], shared[0], opposite[0], opposite[1]),
    )
    children = tuple(_positive_orientation(rational_points, child) for child in raw_children)
    if any(child is None for child in children):
        return ChenPipeClusterResult(
            False, "replacement_has_zero_volume", (), parent_volume6, Fraction(0), False, False
        )
    replacement = tuple(sorted(child for child in children if child is not None))
    replacement_volume6 = sum(
        (abs(_orient6(rational_points, tet)) for tet in replacement), Fraction(0)
    )
    boundary_preserved = _boundary_keys(parents) == _boundary_keys(replacement)
    recovered = _contains_edge(replacement, edge)
    accepted = (
        parent_volume6 > 0
        and replacement_volume6 == parent_volume6
        and boundary_preserved
        and recovered
    )
    return ChenPipeClusterResult(
        accepted,
        "accepted" if accepted else "certificate_contract_failed",
        replacement if accepted else (),
        parent_volume6,
        replacement_volume6,
        boundary_preserved,
        recovered,
    )
