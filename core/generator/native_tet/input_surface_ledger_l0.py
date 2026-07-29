"""Read-only exact source-surface certificate for a tetrahedral output.

This is a global audit primitive, not a recovery mechanism.  It reconstructs
the immutable source-vertex map by exact coordinate identity, extracts the
one-owner tet boundary, then delegates exact source-triangle coverage and
conforming-incidence checks to the existing Chen L1 ledger.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

from core.generator.native_tet.chen_source_subdivision_l0 import (
    ChenSourceSubdivisionCoverageAudit,
    _cross,
    _dot,
    _inside_or_on,
    _point,
    _sub,
    audit_source_triangle_subdivision_l1,
    oriented_boundary_faces_l1,
)


@dataclass(frozen=True)
class InputSurfaceLedgerResult:
    """Global source-surface audit result; neither input nor mesh is mutated."""

    accepted: bool
    reason: str
    source_vertex_ids: tuple[int, ...]
    missing_source_vertices: int
    boundary_face_count: int
    subdivision: ChenSourceSubdivisionCoverageAudit | None
    production_mesh_changed: bool


def _point_key(point: Sequence[float | int]) -> tuple[float, float, float]:
    if len(point) != 3:
        raise ValueError("points must be three-dimensional")
    return float(point[0]), float(point[1]), float(point[2])


def _align_boundary_faces_to_source_orientation(
    points: Sequence[Sequence[float | int]],
    source_faces: Sequence[Sequence[int]],
    boundary_faces: Sequence[Sequence[int]],
) -> tuple[tuple[int, int, int], ...]:
    """Normalize only face winding before the orientation-independent L0 audit."""
    rational = tuple(_point(point) for point in points)
    sources = tuple(tuple(int(vertex) for vertex in face) for face in source_faces)
    source_triangles = tuple(tuple(rational[index] for index in face) for face in sources)
    normals = tuple(
        _cross(_sub(triangle[1], triangle[0]), _sub(triangle[2], triangle[0]))
        for triangle in source_triangles
    )
    aligned: list[tuple[int, int, int]] = []
    for face in boundary_faces:
        if len(face) != 3:
            raise ValueError("boundary faces must be triangles")
        candidate: tuple[int, int, int] = int(face[0]), int(face[1]), int(face[2])
        triangle = tuple(rational[index] for index in candidate)
        matches = [
            index
            for index, source in enumerate(source_triangles)
            if all(
                _dot(normals[index], _sub(point, source[0])) == 0
                and _inside_or_on(point, source)
                for point in triangle
            )
        ]
        if len(matches) == 1:
            vector = _cross(_sub(triangle[1], triangle[0]), _sub(triangle[2], triangle[0]))
            if _dot(vector, normals[matches[0]]) < 0:
                candidate = candidate[0], candidate[2], candidate[1]
        aligned.append(candidate)
    return tuple(aligned)


def audit_input_surface_ledger_l0(
    source_points: Sequence[Sequence[float | int]],
    source_faces: Sequence[Sequence[int]],
    output_points: Sequence[Sequence[float | int]],
    output_tets: Sequence[Sequence[int]],
) -> InputSurfaceLedgerResult:
    """Require the final tet boundary to exactly subdivide all source faces.

    Exact coordinate identity is intentional. Approximate nearest-neighbour
    matching would turn a displaced sharp input corner into a false preserved
    source entity. Duplicate candidate coordinates map deterministically to
    their first occurrence; the later face-coverage audit still rejects any
    geometric or topological use that cannot exactly cover the source.
    """
    try:
        source_keys = tuple(_point_key(point) for point in source_points)
        output_keys = tuple(_point_key(point) for point in output_points)
        if not source_keys or not output_keys:
            raise ValueError
        lookup: dict[tuple[float, float, float], list[int]] = {}
        for index, key in enumerate(output_keys):
            lookup.setdefault(key, []).append(index)
        source_vertex_ids: list[int] = []
        missing = 0
        for key in source_keys:
            matches = lookup.get(key, [])
            if not matches:
                missing += 1
                source_vertex_ids.append(-1)
            else:
                source_vertex_ids.append(matches[0])
        if missing:
            return InputSurfaceLedgerResult(
                False,
                "missing_exact_source_vertex",
                tuple(source_vertex_ids),
                missing,
                0,
                None,
                False,
            )
        mapped_faces = tuple(
            tuple(source_vertex_ids[int(vertex)] for vertex in face)
            for face in source_faces
        )
        boundary_faces = oriented_boundary_faces_l1(output_points, output_tets)
        boundary_faces = _align_boundary_faces_to_source_orientation(
            output_points, mapped_faces, boundary_faces
        )
    except (IndexError, TypeError, ValueError):
        return InputSurfaceLedgerResult(
            False, "invalid_source_or_output_mesh", (), 0, 0, None, False
        )
    subdivision = audit_source_triangle_subdivision_l1(
        output_points, mapped_faces, boundary_faces
    )
    return InputSurfaceLedgerResult(
        subdivision.accepted,
        "accepted" if subdivision.accepted else f"source_surface_failed:{subdivision.reason}",
        tuple(source_vertex_ids),
        0,
        len(boundary_faces),
        subdivision,
        False,
    )
