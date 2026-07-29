"""Manifest-gated sampled inward-clearance prefilter for exact source quads.

This is intentionally only a centre-ray prefilter, not a certificate that an
entire displaced quad front is collision-free.  It requires the authoritative
sidecar contract and a consistently oriented closed source before measuring the
first non-adjacent triangle intersected by each inward source-normal ray.
Failure exposes no shell candidate and never moves an outer source point.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from pathlib import Path

import numpy as np

from .source_feature_sidecar_l1 import (
    AuthoritativeSourceFeatureManifest,
    SourceFeatureSidecarAudit,
    audit_authoritative_source_feature_sidecar_l1,
)


@dataclass(frozen=True)
class SampledInwardClearanceAudit:
    """Read-only local-front prefilter result; no shell topology is selected."""

    status: str
    sidecar: SourceFeatureSidecarAudit
    source_face_count: int
    ray_hit_face_count: int
    minimum_clearance: float | None
    fifth_percentile_clearance: float | None
    faces_below_required_clearance: int
    source_geometry_unchanged: bool
    production_mesh_changed: bool


def _oriented_triangle_edge_closed(faces: np.ndarray) -> bool:
    directed: Counter[tuple[int, int]] = Counter()
    for face in np.asarray(faces, dtype=np.int64):
        if len({int(vertex) for vertex in face}) != 3:
            return False
        for first, second in zip(face, np.roll(face, -1), strict=True):
            directed[(int(first), int(second))] += 1
    return bool(directed) and all(
        count == 1 and directed.get((second, first), 0) == 1
        for (first, second), count in directed.items()
    )


def _ray_triangle_distance(
    origin: np.ndarray,
    direction: np.ndarray,
    first: np.ndarray,
    second: np.ndarray,
    third: np.ndarray,
) -> float | None:
    """Return a strict Moller--Trumbore ray distance or ``None``."""
    first_edge = second - first
    second_edge = third - first
    cross_direction = np.cross(direction, second_edge)
    determinant = float(np.dot(first_edge, cross_direction))
    if abs(determinant) <= 1.0e-12:
        return None
    reciprocal = 1.0 / determinant
    offset = origin - first
    barycentric_first = float(np.dot(offset, cross_direction) * reciprocal)
    if not 0.0 <= barycentric_first <= 1.0:
        return None
    cross_offset = np.cross(offset, first_edge)
    barycentric_second = float(np.dot(direction, cross_offset) * reciprocal)
    if barycentric_second < 0.0 or barycentric_first + barycentric_second > 1.0:
        return None
    distance = float(np.dot(second_edge, cross_offset) * reciprocal)
    return distance if distance > 1.0e-9 else None


def audit_sampled_inward_clearance_l0(
    vertices: np.ndarray,
    faces: np.ndarray,
    *,
    source_path: str | Path,
    manifest: AuthoritativeSourceFeatureManifest | None,
    required_clearance: float,
) -> SampledInwardClearanceAudit:
    """Measure first opposite-front ray hits after manifest/normal validation."""
    points = np.asarray(vertices, dtype=np.float64)
    triangles = np.asarray(faces, dtype=np.int64)
    points_before, faces_before = points.copy(), triangles.copy()
    unchanged = bool(np.array_equal(points, points_before) and np.array_equal(triangles, faces_before))
    sidecar = audit_authoritative_source_feature_sidecar_l1(
        points, triangles, source_path=source_path, manifest=manifest
    )
    if sidecar.status != "pass_authoritative_feature_sidecar":
        return SampledInwardClearanceAudit(
            "reject_authoritative_feature_sidecar", sidecar, 0, 0, None, None, 0, unchanged, False
        )
    if not required_clearance > 0.0 or not _oriented_triangle_edge_closed(triangles):
        return SampledInwardClearanceAudit(
            "reject_clearance_or_source_orientation", sidecar, len(triangles), 0, None, None, 0, unchanged, False
        )
    source_triangles = points[triangles]
    normals = np.cross(
        source_triangles[:, 1] - source_triangles[:, 0],
        source_triangles[:, 2] - source_triangles[:, 0],
    )
    lengths = np.linalg.norm(normals, axis=1)
    if np.any(lengths <= np.finfo(float).tiny):
        return SampledInwardClearanceAudit(
            "reject_degenerate_source_triangle", sidecar, len(triangles), 0, None, None, 0, unchanged, False
        )
    normals = normals / lengths[:, None]
    centers = np.mean(source_triangles, axis=1)
    clearances: list[float] = []
    for face_index, triangle in enumerate(triangles):
        blocked = {int(vertex) for vertex in triangle}
        nearest: float | None = None
        for other_index, other in enumerate(source_triangles):
            if face_index == other_index or blocked.intersection(int(vertex) for vertex in triangles[other_index]):
                continue
            distance = _ray_triangle_distance(centers[face_index], -normals[face_index], *other)
            if distance is not None and (nearest is None or distance < nearest):
                nearest = distance
        if nearest is not None:
            clearances.append(nearest)
    hit_count = len(clearances)
    minimum = float(min(clearances)) if clearances else None
    fifth = float(np.quantile(np.asarray(clearances), 0.05)) if clearances else None
    below = sum(clearance < required_clearance for clearance in clearances)
    accepted = hit_count == len(triangles) and below == 0
    return SampledInwardClearanceAudit(
        "pass_sampled_inward_clearance" if accepted else "reject_sampled_inward_clearance",
        sidecar,
        len(triangles),
        hit_count,
        minimum,
        fifth,
        below,
        unchanged,
        False,
    )
