"""Literal, test-only Chen--Zheng 2006 no-H THR_EDG certificates.

This is intentionally one documented subcase, not a selection rule or a mesh
mutation. The child connectivity below is transcribed from Table 11 of Chen
and Zheng (2006), DOI 10.1631/jzus.2006.A2031. It is accepted only if the
three named intersection points lie strictly on AD, BD, and CD and the literal
children preserve the expected subdivided parent boundary and exact volume.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from fractions import Fraction

from core.generator.native_tet.chen_pipe_cluster_l0 import _orient6, _point, _positive_orientation

LabelTet = tuple[str, str, str, str]
FaceKey = tuple[str, str, str]

_LABELS: tuple[str, ...] = ("A", "B", "C", "D", "P1", "P2", "P3")
_S2_Z1_CHILDREN: tuple[LabelTet, ...] = (
    ("A", "B", "C", "P1"),
    ("P1", "B", "C", "P2"),
    ("P1", "P2", "C", "P3"),
    ("P1", "P2", "P3", "D"),
)
_S2_Z1_BOUNDARY: frozenset[FaceKey] = frozenset(
    {
        ("A", "B", "C"),
        ("A", "B", "P1"),
        ("A", "C", "P1"),
        ("B", "P1", "P2"),
        ("B", "C", "P2"),
        ("C", "P1", "P3"),
        ("C", "P2", "P3"),
        ("D", "P1", "P2"),
        ("D", "P1", "P3"),
        ("D", "P2", "P3"),
    }
)
_S1_Z2_CHILDREN: tuple[LabelTet, ...] = (
    ("A", "B", "C", "P3"),
    ("A", "B", "P3", "P2"),
    ("A", "P2", "P3", "P1"),
    ("P1", "P2", "P3", "D"),
)
_S1_Z2_BOUNDARY: frozenset[FaceKey] = frozenset(
    {
        ("A", "B", "C"),
        ("A", "B", "P2"),
        ("A", "C", "P3"),
        ("A", "P1", "P2"),
        ("A", "P1", "P3"),
        ("B", "C", "P3"),
        ("B", "P2", "P3"),
        ("D", "P1", "P2"),
        ("D", "P1", "P3"),
        ("D", "P2", "P3"),
    }
)


@dataclass(frozen=True)
class ChenThrEdgS2Z1Result:
    """Immutable certification result; rejected input exposes no replacement."""

    accepted: bool
    reason: str
    literal_children: tuple[LabelTet, ...]
    oriented_children: tuple[LabelTet, ...]
    boundary_face_keys: frozenset[FaceKey]
    parent_volume6: Fraction
    replacement_volume6: Fraction
    intersection_points_on_documented_edges: bool
    external_boundary_preserved: bool
    source_points_unchanged: bool
    production_mesh_changed: bool


def _strict_segment_parameter(
    start: tuple[Fraction, Fraction, Fraction],
    end: tuple[Fraction, Fraction, Fraction],
    point: tuple[Fraction, Fraction, Fraction],
) -> Fraction | None:
    delta = tuple(right - left for left, right in zip(start, end, strict=True))
    coordinate = next((index for index, value in enumerate(delta) if value != 0), None)
    if coordinate is None:
        return None
    parameter = (point[coordinate] - start[coordinate]) / delta[coordinate]
    if not Fraction(0) < parameter < Fraction(1):
        return None
    return (
        parameter
        if all(
            value == left + parameter * change
            for value, left, change in zip(point, start, delta, strict=True)
        )
        else None
    )


def _boundary_faces(tets: Sequence[tuple[int, int, int, int]]) -> frozenset[FaceKey]:
    counts: dict[FaceKey, int] = {}
    for tet in tets:
        for omitted in range(4):
            labels = sorted(_LABELS[tet[index]] for index in range(4) if index != omitted)
            face: FaceKey = labels[0], labels[1], labels[2]
            counts[face] = counts.get(face, 0) + 1
    return frozenset(face for face, count in counts.items() if count == 1)


def _certify_thr_edg_no_h_table11_l0(
    points_by_label: Mapping[str, Sequence[float | int | Fraction]],
    *,
    literal_children: tuple[LabelTet, ...],
    expected_boundary: frozenset[FaceKey],
) -> ChenThrEdgS2Z1Result:
    """Certify one literal no-H Table-11 row without selecting or applying it."""
    if any(label not in points_by_label for label in _LABELS):
        return ChenThrEdgS2Z1Result(
            False,
            "missing_table11_point",
            (),
            (),
            frozenset(),
            Fraction(0),
            Fraction(0),
            False,
            False,
            True,
            False,
        )
    points_before = tuple(_point(points_by_label[label]) for label in _LABELS)
    label_to_index = {label: index for index, label in enumerate(_LABELS)}
    parent = (label_to_index["A"], label_to_index["B"], label_to_index["C"], label_to_index["D"])
    parent_orientation = _orient6(points_before, parent)
    if parent_orientation == 0:
        return ChenThrEdgS2Z1Result(
            False,
            "degenerate_parent_tetrahedron",
            (),
            (),
            frozenset(),
            Fraction(0),
            Fraction(0),
            False,
            False,
            True,
            False,
        )
    edge_parameters = (
        _strict_segment_parameter(points_before[0], points_before[3], points_before[4]),
        _strict_segment_parameter(points_before[1], points_before[3], points_before[5]),
        _strict_segment_parameter(points_before[2], points_before[3], points_before[6]),
    )
    if any(parameter is None for parameter in edge_parameters):
        return ChenThrEdgS2Z1Result(
            False,
            "intersection_not_on_documented_parent_edge",
            (),
            (),
            frozenset(),
            abs(parent_orientation),
            Fraction(0),
            False,
            False,
            tuple(_point(points_by_label[label]) for label in _LABELS) == points_before,
            False,
        )

    literal_indices = tuple(
        tuple(label_to_index[label] for label in child) for child in literal_children
    )
    oriented_indices = tuple(
        _positive_orientation(points_before, child) for child in literal_indices
    )
    if any(child is None for child in oriented_indices):
        return ChenThrEdgS2Z1Result(
            False,
            "degenerate_literal_table11_child",
            (),
            (),
            frozenset(),
            abs(parent_orientation),
            Fraction(0),
            True,
            False,
            tuple(_point(points_by_label[label]) for label in _LABELS) == points_before,
            False,
        )
    oriented = tuple(child for child in oriented_indices if child is not None)
    replacement_volume = sum((_orient6(points_before, child) for child in oriented), Fraction(0))
    boundary = _boundary_faces(oriented)
    unchanged = tuple(_point(points_by_label[label]) for label in _LABELS) == points_before
    boundary_preserved = boundary == expected_boundary
    accepted = replacement_volume == abs(parent_orientation) and boundary_preserved and unchanged
    return ChenThrEdgS2Z1Result(
        accepted,
        "accepted" if accepted else "literal_table11_invariant_failed",
        literal_children if accepted else (),
        tuple(tuple(_LABELS[index] for index in child) for child in oriented) if accepted else (),
        boundary if accepted else frozenset(),
        abs(parent_orientation),
        replacement_volume,
        True,
        boundary_preserved,
        unchanged,
        False,
    )


def certify_thr_edg_s2_z1_table11_l0(
    points_by_label: Mapping[str, Sequence[float | int | Fraction]],
) -> ChenThrEdgS2Z1Result:
    """Certify literal Table-11 S2/Z1 children without selection or mutation."""
    return _certify_thr_edg_no_h_table11_l0(
        points_by_label,
        literal_children=_S2_Z1_CHILDREN,
        expected_boundary=_S2_Z1_BOUNDARY,
    )


def certify_thr_edg_s1_z2_table11_l0(
    points_by_label: Mapping[str, Sequence[float | int | Fraction]],
) -> ChenThrEdgS2Z1Result:
    """Certify literal Table-11 S1/Z2 children without selection or mutation."""
    return _certify_thr_edg_no_h_table11_l0(
        points_by_label,
        literal_children=_S1_Z2_CHILDREN,
        expected_boundary=_S1_Z2_BOUNDARY,
    )
