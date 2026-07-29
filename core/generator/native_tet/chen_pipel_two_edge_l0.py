"""Literal, test-only Chen--Zheng-2006 Table-6 Case-2 certificates.

Table 6 decomposes one ordered pipel ``ABCD`` crossed at two open edge
points.  This module records only the three documented local child lists:
opposite edges ``AD``/``BC`` and neighbouring edges ``AD``/``BD`` in S or Z
form.  It deliberately has no global pipel traversal, Phi-neighbour update,
or automatic S/Z selection.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from fractions import Fraction
from typing import Literal

from core.generator.native_tet.chen_pipe_cluster_l0 import (
    IndexTet,
    _orient6,
    _point,
    _positive_orientation,
    _sub,
)
from core.generator.native_tet.chen_source_subdivision_l0 import (
    audit_source_triangle_subdivision_l1,
    oriented_boundary_faces_l1,
)

Case2Scheme = Literal["OPPOSITE", "NEIGHBOR_S", "NEIGHBOR_Z"]


@dataclass(frozen=True)
class ChenTwoEdgePipelResult:
    """A local Table-6 certificate; rejected inputs expose no children."""

    accepted: bool
    reason: str
    replacement_tets: tuple[IndexTet, ...]
    parent_volume6: Fraction
    replacement_volume6: Fraction
    external_boundary_preserved: bool


def _open_edge_parameter(
    points: Sequence[tuple[Fraction, Fraction, Fraction]], edge: tuple[int, int], point: int
) -> Fraction | None:
    start, end, candidate = points[edge[0]], points[edge[1]], points[point]
    direction = _sub(end, start)
    offset = _sub(candidate, start)
    coordinate = next((index for index, value in enumerate(direction) if value != 0), None)
    if coordinate is None:
        return None
    parameter = offset[coordinate] / direction[coordinate]
    if any(offset[index] != parameter * direction[index] for index in range(3)):
        return None
    return parameter if Fraction(0) < parameter < Fraction(1) else None


def certify_two_edge_pipel_template(
    points: Sequence[Sequence[float | int | Fraction]],
    ordered_parent: Sequence[int],
    first_intersection: int,
    second_intersection: int,
    scheme: Case2Scheme,
) -> ChenTwoEdgePipelResult:
    """Certify one literal Table-6 Case-2 split in its documented A/B/C/D order.

    For ``OPPOSITE`` P1 is on AD and P2 is on BC.  For either neighbouring
    form P1 is on AD and P2 is on BD.  Reordering a tetrahedron is an explicit
    caller duty: accepting an arbitrary permutation would fabricate the table
    labels that later Phi/S-Z work must preserve.
    """
    rational_points = tuple(_point(point) for point in points)
    raw_parent = tuple(int(vertex) for vertex in ordered_parent)
    empty = ChenTwoEdgePipelResult(False, "invalid_input", (), Fraction(0), Fraction(0), False)
    if len(raw_parent) != 4 or len(set(raw_parent)) != 4:
        return empty
    if any(vertex < 0 or vertex >= len(rational_points) for vertex in raw_parent):
        return ChenTwoEdgePipelResult(
            False, "parent_index_out_of_range", (), Fraction(0), Fraction(0), False
        )
    if not 0 <= int(first_intersection) < len(rational_points) or not 0 <= int(second_intersection) < len(rational_points):
        return ChenTwoEdgePipelResult(
            False, "intersection_index_out_of_range", (), Fraction(0), Fraction(0), False
        )
    if first_intersection == second_intersection or first_intersection in raw_parent or second_intersection in raw_parent:
        return ChenTwoEdgePipelResult(
            False, "intersections_must_be_distinct_new_points", (), Fraction(0), Fraction(0), False
        )
    parent: IndexTet = (raw_parent[0], raw_parent[1], raw_parent[2], raw_parent[3])
    if _orient6(rational_points, parent) == 0:
        return ChenTwoEdgePipelResult(
            False, "degenerate_parent_tetrahedron", (), Fraction(0), Fraction(0), False
        )
    a, b, c, d = parent
    raw_children: tuple[IndexTet, ...]
    if scheme == "OPPOSITE":
        first_edge, second_edge = (a, d), (b, c)
        raw_children = (
            (a, b, second_intersection, first_intersection),
            (first_intersection, b, second_intersection, d),
            (first_intersection, second_intersection, c, d),
            (a, second_intersection, c, first_intersection),
        )
    elif scheme == "NEIGHBOR_S":
        first_edge, second_edge = (a, d), (b, d)
        raw_children = (
            (a, b, c, first_intersection),
            (first_intersection, b, c, second_intersection),
            (first_intersection, second_intersection, c, d),
        )
    elif scheme == "NEIGHBOR_Z":
        first_edge, second_edge = (a, d), (b, d)
        raw_children = (
            (a, b, c, second_intersection),
            (a, second_intersection, c, first_intersection),
            (first_intersection, second_intersection, c, d),
        )
    else:
        return ChenTwoEdgePipelResult(
            False, "unknown_table6_scheme", (), Fraction(0), Fraction(0), False
        )
    if (
        _open_edge_parameter(rational_points, first_edge, int(first_intersection)) is None
        or _open_edge_parameter(rational_points, second_edge, int(second_intersection)) is None
    ):
        return ChenTwoEdgePipelResult(
            False, "intersections_do_not_match_literal_table6_edges", (), Fraction(0), Fraction(0), False
        )
    oriented = tuple(_positive_orientation(rational_points, child) for child in raw_children)
    if any(child is None for child in oriented):
        return ChenTwoEdgePipelResult(
            False, "replacement_has_zero_volume", (), Fraction(0), Fraction(0), False
        )
    replacement = tuple(sorted(child for child in oriented if child is not None))
    parent_volume = abs(_orient6(rational_points, parent))
    replacement_volume = sum((abs(_orient6(rational_points, child)) for child in replacement), Fraction(0))
    # A Table-6 point lies on a parent edge, so raw boundary-face keys must
    # change.  The relevant local surface invariant is instead an exact,
    # conforming subdivision of every immutable parent face.
    source_faces = oriented_boundary_faces_l1(rational_points, (parent,))
    candidate_faces = oriented_boundary_faces_l1(rational_points, replacement)
    boundary_audit = audit_source_triangle_subdivision_l1(
        rational_points, source_faces, candidate_faces
    )
    boundary_preserved = boundary_audit.accepted
    accepted = parent_volume == replacement_volume and boundary_preserved
    return ChenTwoEdgePipelResult(
        accepted,
        "accepted" if accepted else "table6_geometric_contract_failed",
        replacement if accepted else (),
        parent_volume,
        replacement_volume,
        boundary_preserved,
    )
