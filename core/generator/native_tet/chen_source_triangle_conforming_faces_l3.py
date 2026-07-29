"""Exact L3 audit for a recovered source triangle represented by internal faces.

Volumetric triangle clipping is a before-recovery coverage test.  Once a
source facet is recovered, each source subface has two tetrahedron owners and
must not be counted twice as a volume fragment.  This read-only verifier
extracts that internal two-owner face complex and certifies its exact
conforming subdivision of one immutable source triangle.
"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Sequence
from dataclasses import dataclass
from fractions import Fraction

from core.generator.native_tet.chen_penetration_l0 import _cross, _dot, _point, _sub
from core.generator.native_tet.chen_source_subdivision_l0 import (
    ChenSourceSubdivisionCoverageAudit,
    audit_source_triangle_subdivision_l1,
)

Face = tuple[int, int, int]


@dataclass(frozen=True)
class ChenConformingSourceFaceResult:
    """Exact recovered-face report; no mesh or source input is changed."""

    accepted: bool
    reason: str
    recovered_faces: tuple[Face, ...]
    subdivision: ChenSourceSubdivisionCoverageAudit | None
    source_points_unchanged: bool
    production_mesh_changed: bool


def _face_key(face: Sequence[int]) -> Face:
    ordered = tuple(sorted(int(vertex) for vertex in face))
    if len(ordered) != 3 or len(set(ordered)) != 3:
        raise ValueError("a tetrahedron face must contain three distinct vertices")
    return ordered[0], ordered[1], ordered[2]


def certify_conforming_source_triangle_faces_l3(
    points: Sequence[Sequence[float | int | Fraction]],
    tetrahedra: Sequence[Sequence[int]],
    source_vertex_indices: tuple[int, int, int],
) -> ChenConformingSourceFaceResult:
    """Require source subfaces to be exactly the two-owner internal face complex."""
    before = tuple(_point(point) for point in points)
    if len(set(source_vertex_indices)) != 3 or any(index < 0 or index >= len(before) for index in source_vertex_indices):
        return ChenConformingSourceFaceResult(False, "invalid_source_vertex_indices", (), None, True, False)
    typed = tuple(tuple(int(vertex) for vertex in tet) for tet in tetrahedra)
    if not typed or any(len(tet) != 4 or len(set(tet)) != 4 for tet in typed):
        return ChenConformingSourceFaceResult(False, "invalid_tetrahedron", (), None, True, False)
    if any(vertex < 0 or vertex >= len(before) for tet in typed for vertex in tet):
        return ChenConformingSourceFaceResult(False, "tetrahedron_index_out_of_range", (), None, True, False)
    source = tuple(before[index] for index in source_vertex_indices)
    normal = _cross(_sub(source[1], source[0]), _sub(source[2], source[0]))
    if _dot(normal, normal) == 0:
        return ChenConformingSourceFaceResult(False, "degenerate_source_triangle", (), None, True, False)
    owners: dict[Face, list[Face]] = defaultdict(list)
    for tet in typed:
        for omitted in range(4):
            face = tuple(tet[index] for index in range(4) if index != omitted)
            owners[_face_key(face)].append((face[0], face[1], face[2]))
    recovered: list[Face] = []
    for key, face_owners in owners.items():
        if len(face_owners) != 2:
            continue
        face = face_owners[0]
        face_points = tuple(before[index] for index in face)
        if all(_dot(normal, _sub(point, source[0])) == 0 for point in face_points):
            face_normal = _cross(_sub(face_points[1], face_points[0]), _sub(face_points[2], face_points[0]))
            if _dot(face_normal, normal) < 0:
                face = face[0], face[2], face[1]
            recovered.append(face)
    if not recovered:
        return ChenConformingSourceFaceResult(False, "no_two_owner_source_coplanar_faces", (), None, True, False)
    subdivision = audit_source_triangle_subdivision_l1(
        before, (source_vertex_indices,), tuple(recovered)
    )
    unchanged = before == tuple(_point(point) for point in points)
    return ChenConformingSourceFaceResult(
        subdivision.accepted and unchanged,
        "accepted" if subdivision.accepted and unchanged else f"source_face_subdivision_failed:{subdivision.reason}",
        tuple(recovered) if subdivision.accepted and unchanged else (),
        subdivision,
        unchanged,
        False,
    )
