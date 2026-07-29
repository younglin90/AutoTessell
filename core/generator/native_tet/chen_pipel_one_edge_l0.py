"""Test-only Chen--Zheng-2006 one-edge pipel template certificate.

Table 5 of Chen--Zheng 2006 replaces a pipel ``ABCD`` cut at an open
intersection point ``P`` on edge ``BD`` by ``ABCP`` and ``APCD``.  This module
applies that exact local list only to a closed interior-edge pipe and certifies
volume, exterior boundary, and internal face conformity.  It does not recover
an entire source segment, a source facet, or mutate production CDT state.
"""

from __future__ import annotations

from collections import Counter
from collections.abc import Sequence
from dataclasses import dataclass
from fractions import Fraction

from core.generator.native_tet.chen_pipe_cluster_l0 import (
    IndexTet,
    _boundary_keys,
    _orient6,
    _point,
    _positive_orientation,
    _sub,
)


@dataclass(frozen=True)
class ChenOneEdgePipelResult:
    """Certificate result; rejected cases contain no proposed child tets."""

    accepted: bool
    reason: str
    replacement_tets: tuple[IndexTet, ...]
    parent_volume6: Fraction
    replacement_volume6: Fraction
    external_boundary_preserved: bool
    internal_faces_conforming: bool


def _fractional_edge_parameter(
    points: Sequence[tuple[Fraction, Fraction, Fraction]],
    edge: tuple[int, int],
    point_index: int,
) -> Fraction | None:
    start = points[edge[0]]
    end = points[edge[1]]
    point = points[point_index]
    direction = _sub(end, start)
    offset = _sub(point, start)
    nonzero = next((index for index, value in enumerate(direction) if value != 0), None)
    if nonzero is None:
        return None
    parameter = offset[nonzero] / direction[nonzero]
    if any(offset[index] != parameter * direction[index] for index in range(3)):
        return None
    return parameter


def _face_incidence(tets: Sequence[IndexTet]) -> Counter[tuple[int, int, int]]:
    counts: Counter[tuple[int, int, int]] = Counter()
    for tet in tets:
        for omitted in range(4):
            face_values = sorted(tet[index] for index in range(4) if index != omitted)
            counts[(face_values[0], face_values[1], face_values[2])] += 1
    return counts


def certify_one_edge_pipel_template(
    points: Sequence[Sequence[float | int | Fraction]],
    parent_tets: Sequence[Sequence[int]],
    cut_edge: tuple[int, int],
    intersection_point: int,
) -> ChenOneEdgePipelResult:
    """Certify Table-5 one-edge decomposition on a closed interior-edge pipe."""
    if len(parent_tets) < 3:
        raise ValueError("a closed interior-edge pipe requires at least three parent tetrahedra")
    rational_points = tuple(_point(point) for point in points)
    if not 0 <= int(intersection_point) < len(rational_points):
        return ChenOneEdgePipelResult(
            False, "intersection_index_out_of_range", (), Fraction(0), Fraction(0), False, False
        )
    edge_start, edge_end = int(cut_edge[0]), int(cut_edge[1])
    edge: tuple[int, int] = (min(edge_start, edge_end), max(edge_start, edge_end))
    if edge[0] == edge[1] or any(index < 0 or index >= len(rational_points) for index in edge):
        return ChenOneEdgePipelResult(
            False, "invalid_cut_edge", (), Fraction(0), Fraction(0), False, False
        )
    parameter = _fractional_edge_parameter(rational_points, edge, int(intersection_point))
    if parameter is None or not Fraction(0) < parameter < Fraction(1):
        return ChenOneEdgePipelResult(
            False,
            "intersection_must_be_open_edge_point",
            (),
            Fraction(0),
            Fraction(0),
            False,
            False,
        )

    raw_parents = tuple(tuple(int(vertex) for vertex in tet) for tet in parent_tets)
    if any(len(tet) != 4 or len(set(tet)) != 4 for tet in raw_parents):
        return ChenOneEdgePipelResult(
            False, "invalid_parent_tetrahedron", (), Fraction(0), Fraction(0), False, False
        )
    if any(vertex < 0 or vertex >= len(rational_points) for tet in raw_parents for vertex in tet):
        return ChenOneEdgePipelResult(
            False, "parent_index_out_of_range", (), Fraction(0), Fraction(0), False, False
        )
    if any(
        intersection_point in tet or edge[0] not in tet or edge[1] not in tet for tet in raw_parents
    ):
        return ChenOneEdgePipelResult(
            False,
            "parents_must_share_cut_edge_without_intersection_vertex",
            (),
            Fraction(0),
            Fraction(0),
            False,
            False,
        )
    parents: tuple[IndexTet, ...] = tuple((tet[0], tet[1], tet[2], tet[3]) for tet in raw_parents)
    parent_faces = _face_incidence(parents)
    cut_edge_faces = [face for face in parent_faces if edge[0] in face and edge[1] in face]
    if not cut_edge_faces or any(parent_faces[face] != 2 for face in cut_edge_faces):
        return ChenOneEdgePipelResult(
            False,
            "cut_edge_is_not_interior_closed_pipe",
            (),
            Fraction(0),
            Fraction(0),
            False,
            False,
        )

    children: list[IndexTet] = []
    for tet in parents:
        opposite = sorted(vertex for vertex in tet if vertex not in edge)
        # Table 5 uses ABCP and APCD with the cut edge named B-D.
        raw_children = (
            (opposite[0], edge[0], opposite[1], int(intersection_point)),
            (opposite[0], int(intersection_point), opposite[1], edge[1]),
        )
        oriented = tuple(_positive_orientation(rational_points, child) for child in raw_children)
        if any(child is None for child in oriented):
            return ChenOneEdgePipelResult(
                False,
                "replacement_has_zero_volume",
                (),
                Fraction(0),
                Fraction(0),
                False,
                False,
            )
        children.extend(child for child in oriented if child is not None)
    replacement = tuple(sorted(children))
    parent_volume6 = sum((abs(_orient6(rational_points, tet)) for tet in parents), Fraction(0))
    replacement_volume6 = sum(
        (abs(_orient6(rational_points, tet)) for tet in replacement), Fraction(0)
    )
    external_boundary_preserved = _boundary_keys(parents) == _boundary_keys(replacement)
    replacement_faces = _face_incidence(replacement)
    internal_faces_conforming = all(
        count in {1, 2} for count in replacement_faces.values()
    ) and all(
        count == 2 for face, count in replacement_faces.items() if int(intersection_point) in face
    )
    accepted = (
        parent_volume6 > 0
        and parent_volume6 == replacement_volume6
        and external_boundary_preserved
        and internal_faces_conforming
    )
    return ChenOneEdgePipelResult(
        accepted,
        "accepted" if accepted else "certificate_contract_failed",
        replacement if accepted else (),
        parent_volume6,
        replacement_volume6,
        external_boundary_preserved,
        internal_faces_conforming,
    )
