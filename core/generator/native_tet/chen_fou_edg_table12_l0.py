"""Literal, test-only Chen--Zheng 2006 FOU_EDG SSSS certificate.

This module transcribes only the no-Steiner ``SSSS`` row of Table 12.  Figure
6 fixes its point order: P1, P2, P3, and P4 lie strictly on AD, BD, BC, and
AC, respectively.  It is a local exact certificate, not an S/Z selection
rule, cavity traversal, or CDT mutation.
"""

from __future__ import annotations

from collections import Counter
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from fractions import Fraction

from core.generator.native_tet.chen_pipe_cluster_l0 import _orient6, _point, _positive_orientation
from core.generator.native_tet.chen_source_subdivision_l0 import (
    audit_source_triangle_subdivision_l1,
)
from core.generator.native_tet.chen_thr_edg_table11_l0 import _strict_segment_parameter

LabelTet = tuple[str, str, str, str]
FaceKey = tuple[str, str, str]

_LABELS: tuple[str, ...] = ("A", "B", "C", "D", "P1", "P2", "P3", "P4")
_SSSS_CHILDREN: tuple[LabelTet, ...] = (
    ("P1", "P2", "P3", "D"),
    ("P1", "P3", "C", "D"),
    ("P1", "P3", "P4", "C"),
    ("P1", "P3", "P2", "B"),
    ("P1", "P4", "P3", "A"),
    ("A", "B", "P3", "P1"),
)
_SSSS_BOUNDARY: frozenset[FaceKey] = frozenset(
    {
        ("A", "B", "P1"),
        ("A", "B", "P3"),
        ("A", "P1", "P4"),
        ("A", "P3", "P4"),
        ("B", "P1", "P2"),
        ("B", "P2", "P3"),
        ("C", "D", "P1"),
        ("C", "D", "P3"),
        ("C", "P1", "P4"),
        ("C", "P3", "P4"),
        ("D", "P1", "P2"),
        ("D", "P2", "P3"),
    }
)
_RECOVERED_FRAGMENT: frozenset[FaceKey] = frozenset({("P1", "P2", "P3"), ("P1", "P3", "P4")})


@dataclass(frozen=True)
class ChenFouEdgSsssResult:
    """Immutable Table-12 certificate; rejection exposes no replacement."""

    accepted: bool
    reason: str
    literal_children: tuple[LabelTet, ...]
    oriented_children: tuple[LabelTet, ...]
    boundary_face_keys: frozenset[FaceKey]
    recovered_source_fragment_faces: frozenset[FaceKey]
    parent_volume6: Fraction
    replacement_volume6: Fraction
    intersection_points_on_documented_edges: bool
    source_fragment_l1_preserved: bool
    source_points_unchanged: bool
    production_mesh_changed: bool


def _face_counts(tets: Sequence[tuple[int, int, int, int]]) -> Counter[FaceKey]:
    counts: Counter[FaceKey] = Counter()
    for tet in tets:
        for omitted in range(4):
            labels = sorted(_LABELS[tet[index]] for index in range(4) if index != omitted)
            face: FaceKey = labels[0], labels[1], labels[2]
            counts[face] += 1
    return counts


def _reject(
    reason: str,
    *,
    parent_volume6: Fraction = Fraction(0),
    intersections: bool = False,
    unchanged: bool = True,
) -> ChenFouEdgSsssResult:
    return ChenFouEdgSsssResult(
        False,
        reason,
        (),
        (),
        frozenset(),
        frozenset(),
        parent_volume6,
        Fraction(0),
        intersections,
        False,
        unchanged,
        False,
    )


def certify_fou_edg_ssss_table12_l0(
    points_by_label: Mapping[str, Sequence[float | int | Fraction]],
) -> ChenFouEdgSsssResult:
    """Certify Table-12's literal no-H SSSS row without choosing or applying it."""
    if any(label not in points_by_label for label in _LABELS):
        return _reject("missing_table12_point")
    points_before = tuple(_point(points_by_label[label]) for label in _LABELS)
    label_to_index = {label: index for index, label in enumerate(_LABELS)}
    parent = (label_to_index["A"], label_to_index["B"], label_to_index["C"], label_to_index["D"])
    parent_orientation = _orient6(points_before, parent)
    if parent_orientation == 0:
        return _reject("degenerate_parent_tetrahedron")
    edge_parameters = (
        _strict_segment_parameter(points_before[0], points_before[3], points_before[4]),
        _strict_segment_parameter(points_before[1], points_before[3], points_before[5]),
        _strict_segment_parameter(points_before[1], points_before[2], points_before[6]),
        _strict_segment_parameter(points_before[0], points_before[2], points_before[7]),
    )
    unchanged = tuple(_point(points_by_label[label]) for label in _LABELS) == points_before
    if any(parameter is None for parameter in edge_parameters):
        return _reject(
            "intersection_not_on_documented_ad_bd_bc_ac_edges",
            parent_volume6=abs(parent_orientation),
            unchanged=unchanged,
        )
    if _orient6(points_before, (4, 5, 6, 7)) != 0:
        return _reject(
            "documented_intersections_not_coplanar",
            parent_volume6=abs(parent_orientation),
            intersections=True,
            unchanged=unchanged,
        )
    literal_indices = tuple(
        tuple(label_to_index[label] for label in child) for child in _SSSS_CHILDREN
    )
    oriented_indices = tuple(
        _positive_orientation(points_before, child) for child in literal_indices
    )
    if any(child is None for child in oriented_indices):
        return _reject(
            "degenerate_literal_table12_child",
            parent_volume6=abs(parent_orientation),
            intersections=True,
            unchanged=unchanged,
        )
    oriented = tuple(child for child in oriented_indices if child is not None)
    counts = _face_counts(oriented)
    boundary = frozenset(face for face, count in counts.items() if count == 1)
    recovered = frozenset(
        face for face, count in counts.items() if count == 2 and face in _RECOVERED_FRAGMENT
    )
    replacement_volume = sum((_orient6(points_before, child) for child in oriented), Fraction(0))
    source_fragment_l1 = audit_source_triangle_subdivision_l1(
        tuple(points_before[index] for index in (4, 5, 6, 7)),
        ((0, 1, 2), (0, 2, 3)),
        ((0, 1, 2), (0, 2, 3)),
    )
    accepted = bool(
        replacement_volume == abs(parent_orientation)
        and boundary == _SSSS_BOUNDARY
        and recovered == _RECOVERED_FRAGMENT
        and source_fragment_l1.accepted
        and unchanged
    )
    return ChenFouEdgSsssResult(
        accepted,
        "accepted" if accepted else "literal_table12_invariant_failed",
        _SSSS_CHILDREN if accepted else (),
        tuple(tuple(_LABELS[index] for index in child) for child in oriented) if accepted else (),
        boundary if accepted else frozenset(),
        recovered if accepted else frozenset(),
        abs(parent_orientation),
        replacement_volume,
        True,
        source_fragment_l1.accepted,
        unchanged,
        False,
    )
