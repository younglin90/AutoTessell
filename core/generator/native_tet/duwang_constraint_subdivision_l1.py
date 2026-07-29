"""Read-only exact source-face subdivision protection for local candidates.

L0 detects deletion of an already direct source face.  Point insertion may
legitimately replace that raw key with a conforming complex, so L1 additionally
requires every replacement subface to retain the original face's owner count
(one for a domain boundary, two for an internal constraint) and to exactly
partition the immutable source triangle.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from fractions import Fraction

from core.generator.native_tet.chen_penetration_l0 import _cross, _dot, _point, _sub
from core.generator.native_tet.chen_source_subdivision_l0 import (
    ChenSourceSubdivisionCoverageAudit,
    _inside_or_on,
    audit_source_triangle_subdivision_l1,
)
from core.generator.native_tet.duwang_constraint_protection_l0 import (
    FaceKey,
    _as_tet,
    _face_census,
    _face_key,
)


@dataclass(frozen=True)
class DuWangConstraintSubdivisionFaceResult:
    """One immutable direct face and its exact candidate replacement complex."""

    source_face: FaceKey
    owner_count_before: int
    candidate_subfaces: tuple[FaceKey, ...]
    subdivision: ChenSourceSubdivisionCoverageAudit | None
    accepted: bool
    reason: str


@dataclass(frozen=True)
class DuWangConstraintSubdivisionResult:
    """Exact L1 report; it never applies candidate connectivity."""

    accepted: bool
    reason: str
    faces: tuple[DuWangConstraintSubdivisionFaceResult, ...]
    source_points_unchanged: bool
    production_mesh_changed: bool


def _oriented_like_source(
    points: Sequence[tuple[Fraction, Fraction, Fraction]], source: FaceKey, face: FaceKey
) -> FaceKey:
    source_points = tuple(points[index] for index in source)
    face_points = tuple(points[index] for index in face)
    normal = _cross(_sub(source_points[1], source_points[0]), _sub(source_points[2], source_points[0]))
    candidate_normal = _cross(
        _sub(face_points[1], face_points[0]), _sub(face_points[2], face_points[0])
    )
    return face if _dot(normal, candidate_normal) > 0 else (face[0], face[2], face[1])


def audit_constraint_face_subdivision_l1(
    points: Sequence[Sequence[float | int | Fraction]],
    before_tets: Sequence[Sequence[int]],
    after_tets: Sequence[Sequence[int]],
    protected_faces: Sequence[Sequence[int]],
) -> DuWangConstraintSubdivisionResult:
    """Require direct constraints to survive as exact owner-consistent faces.

    This is deliberately a candidate audit, not a tolerance-based geometric
    comparison.  Coplanarity, support, orientation, edge incidence, and exact
    source-edge intervals are delegated to the existing rational L1 audit.
    """
    before_points = tuple(_point(point) for point in points)
    try:
        before = tuple(_as_tet(tet) for tet in before_tets)
        after = tuple(_as_tet(tet) for tet in after_tets)
        protected = tuple(sorted({_face_key(face) for face in protected_faces}))
        if not protected:
            raise ValueError
        if any(vertex < 0 or vertex >= len(before_points) for face in protected for vertex in face):
            raise ValueError
    except ValueError:
        return DuWangConstraintSubdivisionResult(
            False, "invalid_input", (), before_points == tuple(_point(point) for point in points), False
        )
    before_census = _face_census(before)
    after_census = _face_census(after)
    reports: list[DuWangConstraintSubdivisionFaceResult] = []
    for source in protected:
        owner_count = before_census[source]
        if owner_count not in {1, 2}:
            reports.append(
                DuWangConstraintSubdivisionFaceResult(
                    source, owner_count, (), None, False, "missing_or_nonmanifold_before"
                )
            )
            continue
        source_points = tuple(before_points[index] for index in source)
        normal = _cross(
            _sub(source_points[1], source_points[0]), _sub(source_points[2], source_points[0])
        )
        if _dot(normal, normal) == 0:
            reports.append(
                DuWangConstraintSubdivisionFaceResult(
                    source, owner_count, (), None, False, "degenerate_source_face"
                )
            )
            continue
        candidates: list[FaceKey] = []
        for face, count in after_census.items():
            if count != owner_count:
                continue
            face_points = tuple(before_points[index] for index in face)
            if all(
                _dot(normal, _sub(point, source_points[0])) == 0
                and _inside_or_on(point, source_points)
                for point in face_points
            ):
                candidates.append(_oriented_like_source(before_points, source, face))
        if not candidates:
            reports.append(
                DuWangConstraintSubdivisionFaceResult(
                    source, owner_count, (), None, False, "no_owner_consistent_after_subfaces"
                )
            )
            continue
        subdivision = audit_source_triangle_subdivision_l1(
            before_points, (source,), tuple(candidates)
        )
        reports.append(
            DuWangConstraintSubdivisionFaceResult(
                source,
                owner_count,
                tuple(sorted(_face_key(face) for face in candidates)),
                subdivision,
                subdivision.accepted,
                "preserved" if subdivision.accepted else f"subdivision_failed:{subdivision.reason}",
            )
        )
    unchanged = before_points == tuple(_point(point) for point in points)
    accepted = bool(reports) and all(report.accepted for report in reports) and unchanged
    reason = "preserved" if accepted else "constraint_subdivision_failed"
    return DuWangConstraintSubdivisionResult(
        accepted, reason, tuple(reports), unchanged, False
    )
