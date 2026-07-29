"""Exact, immutable coordinate canonicalization for STL triangle soups.

STL commonly repeats a geometric corner once per incident triangle.  Recovery
algorithms need a shared edge complex, while the source-surface contract still
needs every original triangle represented exactly.  This adapter derives the
former from the latter using exact coordinate identity; it never edits either
input arrays or production mesh state.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from fractions import Fraction

from core.generator.native_tet.chen_penetration_l0 import _point

Point = tuple[Fraction, Fraction, Fraction]
Face = tuple[int, int, int]


@dataclass(frozen=True)
class CanonicalSourceComplexL0:
    """One-to-one raw-triangle mapping onto an exact shared-vertex complex."""

    accepted: bool
    reason: str
    canonical_points: tuple[Point, ...]
    canonical_faces: tuple[Face, ...]
    raw_to_canonical_vertex: tuple[int, ...]
    raw_triangle_count_preserved: bool
    source_points_unchanged: bool
    production_mesh_changed: bool


def canonicalize_source_complex_l0(
    source_points: Sequence[Sequence[float | int | Fraction]],
    source_faces: Sequence[Sequence[int]],
) -> CanonicalSourceComplexL0:
    """Map duplicate coordinates to first canonical IDs without dropping faces."""
    before = tuple(_point(point) for point in source_points)
    try:
        raw_faces = tuple(tuple(int(index) for index in face) for face in source_faces)
        if (
            not before
            or not raw_faces
            or any(len(face) != 3 for face in raw_faces)
            or any(index < 0 or index >= len(before) for face in raw_faces for index in face)
        ):
            raise ValueError
    except (TypeError, ValueError):
        return CanonicalSourceComplexL0(
            False, "invalid_source_complex", (), (), (), False, True, False
        )
    lookup: dict[Point, int] = {}
    canonical_points: list[Point] = []
    raw_to_canonical: list[int] = []
    for point in before:
        canonical_id = lookup.get(point)
        if canonical_id is None:
            canonical_id = len(canonical_points)
            lookup[point] = canonical_id
            canonical_points.append(point)
        raw_to_canonical.append(canonical_id)
    canonical_faces: tuple[Face, ...] = tuple(
        (
            raw_to_canonical[face[0]],
            raw_to_canonical[face[1]],
            raw_to_canonical[face[2]],
        )
        for face in raw_faces
    )
    if any(len(set(face)) != 3 for face in canonical_faces):
        return CanonicalSourceComplexL0(
            False,
            "coordinate_weld_would_degenerate_source_triangle",
            tuple(canonical_points),
            canonical_faces,
            tuple(raw_to_canonical),
            len(canonical_faces) == len(raw_faces),
            before == tuple(_point(point) for point in source_points),
            False,
        )
    unchanged = before == tuple(_point(point) for point in source_points)
    return CanonicalSourceComplexL0(
        unchanged,
        "accepted" if unchanged else "source_points_changed",
        tuple(canonical_points),
        canonical_faces,
        tuple(raw_to_canonical),
        len(canonical_faces) == len(raw_faces),
        unchanged,
        False,
    )
