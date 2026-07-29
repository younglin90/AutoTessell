"""Exact read-only owner/side audit for coplanar source-plane subfaces.

Chen S/Z templates apply to non-coplanar cut clusterels.  When a source plane
already coincides with tetrahedron faces, the necessary question is different:
does an exact source-triangle subdivision have owners on exactly one side of
the plane, or has it become a two-sided internal sheet?  This module only
answers that question; it never changes connectivity or infers which signed
side is the physical interior.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from fractions import Fraction

from core.generator.native_tet.chen_penetration_l0 import RationalPoint, _cross, _dot, _point, _sub
from core.generator.native_tet.chen_source_subdivision_l0 import (
    ChenSourceSubdivisionCoverageAudit,
    _inside_or_on,
    audit_source_triangle_subdivision_l1,
)

IndexTet = tuple[int, int, int, int]
FaceIndex = tuple[int, int, int]


@dataclass(frozen=True)
class ChenCoplanarSourceFaceOwner:
    """One source-contained coplanar tet face and its opposite-side sign."""

    parent_index: int
    local_omitted_vertex: int
    face: FaceIndex
    side: int


@dataclass(frozen=True)
class ChenCoplanarSourceShellOwnerResult:
    """Owner/side census for one immutable source triangle."""

    accepted: bool
    reason: str
    owners: tuple[ChenCoplanarSourceFaceOwner, ...]
    positive_coverage: ChenSourceSubdivisionCoverageAudit | None
    negative_coverage: ChenSourceSubdivisionCoverageAudit | None
    noncontained_coplanar_faces: int
    zero_side_faces: int
    selected_side: int | None
    source_points_unchanged: bool
    production_mesh_changed: bool


def _as_tet(tet: Sequence[int]) -> IndexTet | None:
    values = tuple(int(value) for value in tet)
    if len(values) != 4 or len(set(values)) != 4:
        return None
    return values[0], values[1], values[2], values[3]


def _source_ids(
    points: Sequence[RationalPoint], source: tuple[RationalPoint, ...]
) -> tuple[list[RationalPoint], FaceIndex]:
    assembled = list(points)
    point_ids: dict[RationalPoint, int] = {}
    for index, point in enumerate(assembled):
        point_ids.setdefault(point, index)
    ids: list[int] = []
    for point in source:
        if point not in point_ids:
            point_ids[point] = len(assembled)
            assembled.append(point)
        ids.append(point_ids[point])
    return assembled, (ids[0], ids[1], ids[2])


def _audit_side(
    points: Sequence[RationalPoint], source_face: FaceIndex, faces: Sequence[FaceIndex]
) -> ChenSourceSubdivisionCoverageAudit | None:
    if not faces:
        return None
    return audit_source_triangle_subdivision_l1(points, (source_face,), faces)


def audit_coplanar_source_shell_owner_l0(
    points: Sequence[Sequence[float | int | Fraction]],
    tetrahedra: Sequence[Sequence[int]],
    source_triangle: Sequence[Sequence[float | int | Fraction]],
) -> ChenCoplanarSourceShellOwnerResult:
    """Require exactly one exact coplanar owner-side subdivision, if any.

    The sign is measured relative to the supplied source-face winding.  It is
    intentionally not named "interior" or "exterior": that semantic mapping
    belongs to the later closed-surface orientation/provenance card.
    """
    before = tuple(_point(point) for point in points)
    source = tuple(_point(point) for point in source_triangle)
    if len(source) != 3:
        raise ValueError("a source triangle requires exactly three points")
    normal = _cross(_sub(source[1], source[0]), _sub(source[2], source[0]))
    if _dot(normal, normal) == 0:
        return ChenCoplanarSourceShellOwnerResult(
            False, "degenerate_source_triangle", (), None, None, 0, 0, None, True, False
        )
    typed = tuple(_as_tet(tet) for tet in tetrahedra)
    if not typed or any(tet is None for tet in typed):
        return ChenCoplanarSourceShellOwnerResult(
            False, "invalid_parent_tetrahedron", (), None, None, 0, 0, None, True, False
        )
    tets = tuple(tet for tet in typed if tet is not None)
    if any(vertex < 0 or vertex >= len(before) for tet in tets for vertex in tet):
        return ChenCoplanarSourceShellOwnerResult(
            False, "parent_index_out_of_range", (), None, None, 0, 0, None, True, False
        )
    assembled, source_face = _source_ids(before, source)
    positive_faces: list[FaceIndex] = []
    negative_faces: list[FaceIndex] = []
    owners: list[ChenCoplanarSourceFaceOwner] = []
    noncontained = 0
    zero_side = 0
    for parent_index, tet in enumerate(tets):
        for omitted in range(4):
            face = tuple(tet[index] for index in range(4) if index != omitted)
            triangle = tuple(before[index] for index in face)
            if not all(_dot(normal, _sub(point, source[0])) == 0 for point in triangle):
                continue
            if not all(_inside_or_on(point, source) for point in triangle):
                noncontained += 1
                continue
            face_normal = _cross(_sub(triangle[1], triangle[0]), _sub(triangle[2], triangle[0]))
            if _dot(face_normal, normal) == 0:
                continue
            opposite = before[tet[omitted]]
            side_value = _dot(normal, _sub(opposite, source[0]))
            if side_value == 0:
                zero_side += 1
                continue
            oriented_face: FaceIndex = face[0], face[1], face[2]
            if _dot(face_normal, normal) < 0:
                oriented_face = oriented_face[0], oriented_face[2], oriented_face[1]
            side = 1 if side_value > 0 else -1
            owners.append(ChenCoplanarSourceFaceOwner(parent_index, omitted, oriented_face, side))
            if side > 0:
                positive_faces.append(oriented_face)
            else:
                negative_faces.append(oriented_face)
    positive = _audit_side(assembled, source_face, positive_faces)
    negative = _audit_side(assembled, source_face, negative_faces)
    unchanged = before == tuple(_point(point) for point in points)
    positive_pass = bool(positive is not None and positive.accepted)
    negative_pass = bool(negative is not None and negative.accepted)
    if zero_side:
        reason, selected = "zero_side_coplanar_parent", None
    elif positive_pass and negative_pass:
        reason, selected = "two_sided_coplanar_shell", None
    elif positive_pass:
        reason, selected = "accepted_one_sided_positive", 1
    elif negative_pass:
        reason, selected = "accepted_one_sided_negative", -1
    else:
        reason, selected = "no_one_sided_conforming_source_shell", None
    accepted = selected is not None and unchanged
    return ChenCoplanarSourceShellOwnerResult(
        accepted,
        reason,
        tuple(owners),
        positive,
        negative,
        noncontained,
        zero_side,
        selected,
        unchanged,
        False,
    )
