"""Test-only normal-front shell candidate with complete inner-front pair audit.

This is a controlled geometry experiment, not a feature-aware boundary-layer
implementation.  It requires an authoritative manifest, fixes the exact outer
source quads byte-for-byte, offsets shared quad vertices by averaged source
normals, and rejects on any raw negative hex or non-adjacent inner-front
triangle contact.  No candidate is connected to native_hex output.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path

import numpy as np

from .source_feature_sidecar_l1 import (
    AuthoritativeSourceFeatureManifest,
    SourceFeatureSidecarAudit,
    audit_authoritative_source_feature_sidecar_l1,
)
from .source_quad_shell_concavity_l2 import _raw_negative_hex_indices
from .source_triangle_quadization_l1 import audit_exact_source_quadization_l1


@dataclass(frozen=True)
class NormalFrontShellAudit:
    """Report-only normal-offset front result; outer source geometry is fixed."""

    status: str
    sidecar: SourceFeatureSidecarAudit
    hex_count: int
    raw_negative_hex_count: int
    inner_front_triangle_count: int
    inner_front_intersection_pair_count: int
    inner_front_coplanar_pair_count: int
    outer_quad_set_preserved: bool
    source_vertex_prefix_identical: bool
    source_geometry_unchanged: bool
    production_mesh_changed: bool


def _oriented_triangle_edge_closed(faces: np.ndarray) -> bool:
    directed: dict[tuple[int, int], int] = {}
    for face in np.asarray(faces, dtype=np.int64):
        if len({int(vertex) for vertex in face}) != 3:
            return False
        for first, second in zip(face, np.roll(face, -1), strict=True):
            edge = int(first), int(second)
            directed[edge] = directed.get(edge, 0) + 1
    return bool(directed) and all(
        count == 1 and directed.get((second, first), 0) == 1
        for (first, second), count in directed.items()
    )


def _segment_triangle_hit(
    start: np.ndarray, end: np.ndarray, triangle: np.ndarray
) -> bool:
    """Conservative finite segment/triangle hit, including boundary contact."""
    direction = end - start
    first, second, third = triangle
    first_edge = second - first
    second_edge = third - first
    cross_direction = np.cross(direction, second_edge)
    determinant = float(np.dot(first_edge, cross_direction))
    if abs(determinant) <= 1.0e-12:
        return False
    reciprocal = 1.0 / determinant
    offset = start - first
    first_parameter = float(np.dot(offset, cross_direction) * reciprocal)
    if not -1.0e-12 <= first_parameter <= 1.0 + 1.0e-12:
        return False
    cross_offset = np.cross(offset, first_edge)
    second_parameter = float(np.dot(direction, cross_offset) * reciprocal)
    if second_parameter < -1.0e-12 or first_parameter + second_parameter > 1.0 + 1.0e-12:
        return False
    parameter = float(np.dot(second_edge, cross_offset) * reciprocal)
    return -1.0e-12 <= parameter <= 1.0 + 1.0e-12


def _triangle_pair_relation(first: np.ndarray, second: np.ndarray) -> str:
    """Return ``none``, ``intersection``, or conservative ``coplanar``."""
    first_normal = np.cross(first[1] - first[0], first[2] - first[0])
    second_normal = np.cross(second[1] - second[0], second[2] - second[0])
    normal_cross = np.cross(first_normal, second_normal)
    if (
        np.linalg.norm(normal_cross) <= 1.0e-12 * np.linalg.norm(first_normal) * np.linalg.norm(second_normal)
        and np.all(np.abs((second - first[0]) @ first_normal) <= 1.0e-12 * np.linalg.norm(first_normal))
    ):
        return "coplanar"
    for start, end in zip(first, np.roll(first, -1, axis=0), strict=True):
        if _segment_triangle_hit(start, end, second):
            return "intersection"
    for start, end in zip(second, np.roll(second, -1, axis=0), strict=True):
        if _segment_triangle_hit(start, end, first):
            return "intersection"
    return "none"


def _inner_front_pair_counts(points: np.ndarray, quads: np.ndarray) -> tuple[int, int]:
    """Count non-adjacent inner-front contacts using triangle AABB broad phase."""
    triangles = np.vstack((quads[:, (0, 1, 2)], quads[:, (0, 2, 3)])).astype(np.int64)
    coordinates = points[triangles]
    lower = np.min(coordinates, axis=1)
    upper = np.max(coordinates, axis=1)
    intersections = 0
    coplanar = 0
    vertex_sets = tuple(frozenset(int(vertex) for vertex in triangle) for triangle in triangles)
    for first_index in range(len(triangles)):
        possible: np.ndarray = np.flatnonzero(
            np.all(upper[first_index] >= lower[first_index + 1 :], axis=1)
            & np.all(upper[first_index + 1 :] >= lower[first_index], axis=1)
        ) + first_index + 1
        for second_index in possible:
            if vertex_sets[first_index] & vertex_sets[int(second_index)]:
                continue
            relation = _triangle_pair_relation(coordinates[first_index], coordinates[int(second_index)])
            if relation == "intersection":
                intersections += 1
            elif relation == "coplanar":
                coplanar += 1
    return intersections, coplanar


def audit_normal_front_shell_l1(
    vertices: np.ndarray,
    faces: np.ndarray,
    *,
    source_path: str | Path,
    manifest: AuthoritativeSourceFeatureManifest | None,
    thickness: float,
) -> NormalFrontShellAudit:
    """Audit one manifest-gated normal-offset front without accepting a shell."""
    points = np.asarray(vertices, dtype=np.float64)
    triangles = np.asarray(faces, dtype=np.int64)
    points_before, faces_before = points.copy(), triangles.copy()
    unchanged = bool(np.array_equal(points, points_before) and np.array_equal(triangles, faces_before))
    sidecar = audit_authoritative_source_feature_sidecar_l1(
        points, triangles, source_path=source_path, manifest=manifest
    )
    if sidecar.status != "pass_authoritative_feature_sidecar":
        return NormalFrontShellAudit(
            "reject_authoritative_feature_sidecar", sidecar, 0, 0, 0, 0, 0, False, False, unchanged, False
        )
    assert manifest is not None
    if not thickness > 0.0 or not _oriented_triangle_edge_closed(triangles):
        return NormalFrontShellAudit(
            "reject_thickness_or_source_orientation", sidecar, 0, 0, 0, 0, 0, False, False, unchanged, False
        )
    surface = audit_exact_source_quadization_l1(points, triangles, manifest.face_entities)
    if surface.status != "pass_exact_source_quadization":
        return NormalFrontShellAudit(
            "reject_source_quadization", sidecar, 0, 0, 0, 0, 0, False, False, unchanged, False
        )
    outer = surface.quadization.points
    outer_quads = surface.quadization.quads
    source_triangles = points[triangles]
    source_normals = np.cross(
        source_triangles[:, 1] - source_triangles[:, 0],
        source_triangles[:, 2] - source_triangles[:, 0],
    )
    normal_lengths = np.linalg.norm(source_normals, axis=1)
    if np.any(normal_lengths <= np.finfo(float).tiny):
        return NormalFrontShellAudit(
            "reject_degenerate_source_triangle", sidecar, 0, 0, 0, 0, 0, False, False, unchanged, False
        )
    source_normals = source_normals / normal_lengths[:, None]
    vertex_normals = np.zeros_like(outer)
    for quad, source_face in zip(outer_quads, surface.quadization.source_face_ids, strict=True):
        vertex_normals[quad] += source_normals[int(source_face)]
    vertex_lengths = np.linalg.norm(vertex_normals, axis=1)
    if np.any(vertex_lengths <= np.finfo(float).tiny):
        return NormalFrontShellAudit(
            "reject_zero_quad_vertex_normal", sidecar, 0, 0, 0, 0, 0, False, False, unchanged, False
        )
    inner = outer - thickness * vertex_normals / vertex_lengths[:, None]
    all_points = np.vstack((outer, inner))
    ordered_outer = outer_quads[:, ::-1]
    hexes = np.hstack((ordered_outer, ordered_outer + len(outer)))
    raw_negative = len(_raw_negative_hex_indices(all_points, hexes))
    intersections, coplanar = _inner_front_pair_counts(inner, outer_quads)
    outer_preserved = bool(np.array_equal(all_points[: len(outer)], outer))
    prefix = bool(np.array_equal(outer[: len(points)], points))
    accepted = raw_negative == 0 and intersections == 0 and coplanar == 0 and outer_preserved and prefix
    return NormalFrontShellAudit(
        "pass_normal_front_candidate" if accepted else "reject_normal_front_geometry",
        sidecar,
        len(hexes),
        raw_negative,
        2 * len(outer_quads),
        intersections,
        coplanar,
        outer_preserved,
        prefix,
        unchanged,
        False,
    )
