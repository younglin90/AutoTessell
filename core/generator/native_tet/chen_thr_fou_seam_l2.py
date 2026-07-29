"""Test-only L2 seam certificate for one Chen THR_EDG/FOU_EDG cavity pair.

It joins the literal no-H THR S2/Z1 and FOU SSSS rows only after each has
passed its finite-source L1 match.  The sole claim is that their common parent
face receives one conforming exact subdivision.  It does not choose schemes,
cover a whole input source triangle, update neighbours, or mutate CDT state.
"""

from __future__ import annotations

from collections import Counter
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from fractions import Fraction

from core.generator.native_tet.chen_clusterel_type_l0 import classify_clusterel_type
from core.generator.native_tet.chen_fou_edg_source_match_l1 import (
    certify_fou_edg_source_match_l1,
)
from core.generator.native_tet.chen_penetration_l0 import _cross, _dot, _point, _sub
from core.generator.native_tet.chen_pipe_cluster_l0 import _orient6
from core.generator.native_tet.chen_source_subdivision_l0 import (
    _inside_or_on,
    audit_source_triangle_subdivision_l1,
    oriented_boundary_faces_l1,
)
from core.generator.native_tet.chen_thr_edg_source_match_l1 import (
    certify_thr_edg_source_match_l1,
)

Point = tuple[Fraction, Fraction, Fraction]
Face = tuple[int, int, int]
Tet = tuple[int, int, int, int]


@dataclass(frozen=True)
class ChenThrFouSeamResult:
    """Fail-closed two-parent seam report; rejection exposes no replacement."""

    accepted: bool
    reason: str
    shared_parent_face: tuple[int, int, int] | None
    shared_face_subfaces: int
    shared_face_l1_preserved: bool
    child_face_incidence_valid: bool
    source_points_unchanged: bool
    production_mesh_changed: bool
    cavity_boundary_l1_preserved: bool = False
    combined_volume_preserved: bool = False


def _as_tet(tet: Sequence[int]) -> Tet:
    values = tuple(int(value) for value in tet)
    if len(values) != 4 or len(set(values)) != 4:
        raise ValueError("each documented parent must be one four-distinct-vertex tetrahedron")
    return values[0], values[1], values[2], values[3]


def _face_counts(tets: Sequence[Tet]) -> Counter[Face]:
    counts: Counter[Face] = Counter()
    for tet in tets:
        for omitted in range(4):
            labels = sorted(tet[index] for index in range(4) if index != omitted)
            counts[(labels[0], labels[1], labels[2])] += 1
    return counts


def _edge_point_map(
    tetrahedron: Sequence[Point],
    source_triangle: Sequence[Sequence[float | int | Fraction]],
    expected_edges: tuple[tuple[int, int], ...],
) -> Mapping[tuple[int, int], Point] | None:
    classification = classify_clusterel_type(tetrahedron, source_triangle)
    if (
        not classification.accepted
        or classification.penetration is None
        or classification.penetration.penetrating_edges != expected_edges
    ):
        return None
    return dict(
        zip(
            classification.penetration.penetrating_edges,
            classification.penetration.intersection_points,
            strict=True,
        )
    )


def _oriented_source_face(
    face: Face, points: Sequence[Point], normal: Point
) -> tuple[int, int, int] | None:
    first, second, third = (points[index] for index in face)
    vector = _cross(_sub(second, first), _sub(third, first))
    sign = _dot(vector, normal)
    if sign == 0:
        return None
    return face if sign > 0 else (face[0], face[2], face[1])


def certify_thr_fou_shared_face_l2(
    points: Sequence[Sequence[float | int | Fraction]],
    thr_parent: Sequence[int],
    fou_parent: Sequence[int],
    source_triangle: Sequence[Sequence[float | int | Fraction]],
) -> ChenThrFouSeamResult:
    """Certify one documented THR/FOU pair's shared-face subdivision exactly."""
    before_points = tuple(_point(point) for point in points)
    try:
        thr = _as_tet(thr_parent)
        fou = _as_tet(fou_parent)
        if any(index < 0 or index >= len(before_points) for index in (*thr, *fou)):
            raise ValueError
    except ValueError:
        return ChenThrFouSeamResult(
            False, "invalid_parent_input", None, 0, False, False, True, False
        )
    shared = tuple(sorted(set(thr).intersection(fou)))
    if len(shared) != 3:
        return ChenThrFouSeamResult(
            False, "parents_do_not_share_one_face", None, 0, False, False, True, False
        )
    shared_face = (shared[0], shared[1], shared[2])
    thr_other = next(index for index in thr if index not in shared)
    fou_other = next(index for index in fou if index not in shared)
    shared_points = tuple(before_points[index] for index in shared_face)
    normal = _cross(
        _sub(shared_points[1], shared_points[0]), _sub(shared_points[2], shared_points[0])
    )
    if (
        _dot(normal, normal) == 0
        or _dot(normal, _sub(before_points[thr_other], shared_points[0]))
        * _dot(normal, _sub(before_points[fou_other], shared_points[0]))
        >= 0
    ):
        return ChenThrFouSeamResult(
            False,
            "parents_not_opposite_across_shared_face",
            shared_face,
            0,
            False,
            False,
            True,
            False,
        )
    thr_points = tuple(before_points[index] for index in thr)
    fou_points = tuple(before_points[index] for index in fou)
    thr_match = certify_thr_edg_source_match_l1(thr_points, source_triangle, subcase="S2/Z1")
    fou_match = certify_fou_edg_source_match_l1(fou_points, source_triangle)
    if (
        not thr_match.accepted
        or thr_match.candidate is None
        or not fou_match.accepted
        or fou_match.candidate is None
    ):
        return ChenThrFouSeamResult(
            False,
            "parents_do_not_match_documented_thr_s2z1_fou_ssss",
            shared_face,
            0,
            False,
            False,
            True,
            False,
        )
    thr_intersections = _edge_point_map(thr_points, source_triangle, ((0, 3), (1, 3), (2, 3)))
    fou_intersections = _edge_point_map(
        fou_points, source_triangle, ((0, 2), (0, 3), (1, 2), (1, 3))
    )
    if thr_intersections is None or fou_intersections is None:
        return ChenThrFouSeamResult(
            False, "documented_intersection_ledger_lost", shared_face, 0, False, False, True, False
        )
    thr_labels = {
        "A": thr_points[0],
        "B": thr_points[1],
        "C": thr_points[2],
        "D": thr_points[3],
        "P1": thr_intersections[(0, 3)],
        "P2": thr_intersections[(1, 3)],
        "P3": thr_intersections[(2, 3)],
    }
    fou_labels = {
        "A": fou_points[0],
        "B": fou_points[1],
        "C": fou_points[2],
        "D": fou_points[3],
        "P1": fou_intersections[(0, 3)],
        "P2": fou_intersections[(1, 3)],
        "P3": fou_intersections[(1, 2)],
        "P4": fou_intersections[(0, 2)],
    }
    global_points: list[Point] = []
    global_ids: dict[Point, int] = {}

    def point_id(point: Point) -> int:
        if point not in global_ids:
            global_ids[point] = len(global_points)
            global_points.append(point)
        return global_ids[point]

    def mapped_parent(tet: Tet) -> Tet:
        return (
            point_id(before_points[tet[0]]),
            point_id(before_points[tet[1]]),
            point_id(before_points[tet[2]]),
            point_id(before_points[tet[3]]),
        )

    child_tets: list[Tet] = []
    for labels, children in (
        (thr_labels, thr_match.candidate.oriented_children),
        (fou_labels, fou_match.candidate.oriented_children),
    ):
        for child in children:
            child_tets.append(tuple(point_id(labels[label]) for label in child))  # type: ignore[arg-type]
    counts = _face_counts(child_tets)
    incidence_valid = all(count in (1, 2) for count in counts.values())
    seam_faces = tuple(
        face
        for face, count in counts.items()
        if count == 2
        and all(
            _dot(normal, _sub(global_points[index], shared_points[0])) == 0
            and _inside_or_on(global_points[index], shared_points)
            for index in face
        )
    )
    oriented_seam = tuple(
        oriented
        for face in seam_faces
        if (oriented := _oriented_source_face(face, global_points, normal)) is not None
    )
    source_face = tuple(point_id(before_points[index]) for index in shared_face)
    l1 = audit_source_triangle_subdivision_l1(global_points, (source_face,), oriented_seam)
    mapped_thr = mapped_parent(thr)
    mapped_fou = mapped_parent(fou)
    parent_tets: tuple[Tet, Tet] = mapped_thr, mapped_fou
    parent_exterior = oriented_boundary_faces_l1(global_points, parent_tets)
    child_exterior = oriented_boundary_faces_l1(global_points, child_tets)
    shell_l1 = audit_source_triangle_subdivision_l1(global_points, parent_exterior, child_exterior)
    parent_volume = sum((abs(_orient6(global_points, tet)) for tet in parent_tets), Fraction(0))
    child_volume = sum((_orient6(global_points, tet) for tet in child_tets), Fraction(0))
    combined_volume = child_volume == parent_volume and all(
        _orient6(global_points, tet) > 0 for tet in child_tets
    )
    unchanged = tuple(_point(point) for point in points) == before_points
    accepted = bool(
        incidence_valid
        and len(oriented_seam) == len(seam_faces)
        and l1.accepted
        and shell_l1.accepted
        and combined_volume
        and unchanged
    )
    return ChenThrFouSeamResult(
        accepted,
        "accepted" if accepted else "thr_fou_shared_face_invariant_failed",
        shared_face,
        len(seam_faces),
        l1.accepted,
        incidence_valid,
        unchanged,
        False,
        shell_l1.accepted,
        combined_volume,
    )
