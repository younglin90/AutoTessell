"""Controlled, non-promoting Gate-4 surface-distance observations.

The distances in this module are exact point-to-triangle distances at a
deterministic, area-weighted sample set.  They are deliberately *not* claimed
to be an exact continuous Hausdorff distance, a signed distance, or an
authoritative source-to-output mapping.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from numpy.typing import NDArray

from core.utils.aabb import TriangleBVH

_UNVERIFIED_FIELDS = (
    "distance.signed_mean",
    "topology.self_intersections",
    "integral.volume_error_pct",
    "integral.centroid_shift_rel",
    "features.authoritative_ids",
    "features.critical_missing",
    "patches.compared",
    "physical_groups.authoritative_mapping",
    "provenance.source_to_output",
)


@dataclass(frozen=True, slots=True)
class DirectedSurfaceDistance:
    """Deterministic sampled distance statistics in one source direction."""

    rms: float
    p95: float
    p99: float
    maximum: float


@dataclass(frozen=True, slots=True)
class ExactSurfaceMetricRecord:
    """Fail-closed actual-surface observations; never a Gate-4 verdict."""

    status: str
    sample_count: int
    method: str
    source_to_output: DirectedSurfaceDistance | None
    output_to_source: DirectedSurfaceDistance | None
    symmetric_sampled_max: float | None
    normal_status: str
    normal_p95_deg: float | None
    normal_p99_deg: float | None
    normal_flipped: int | None
    available_fields: tuple[str, ...]
    unverified_fields: tuple[str, ...]
    gate4_pass: bool = False


def _invalid_record(status: str, sample_count: int) -> ExactSurfaceMetricRecord:
    return ExactSurfaceMetricRecord(
        status=status,
        sample_count=sample_count,
        method="deterministic_area_samples+exact_point_to_triangle_bvh",
        source_to_output=None,
        output_to_source=None,
        symmetric_sampled_max=None,
        normal_status="unverified_not_measured",
        normal_p95_deg=None,
        normal_p99_deg=None,
        normal_flipped=None,
        available_fields=(),
        unverified_fields=_UNVERIFIED_FIELDS,
        gate4_pass=False,
    )


def _as_finite_triangles(
    vertices: object,
    faces: object,
) -> tuple[NDArray[np.float64], NDArray[np.int64]] | None:
    """Return a strict finite triangle surface, otherwise ``None``."""
    try:
        points = np.asarray(vertices, dtype=np.float64)
        triangles = np.asarray(faces, dtype=np.int64)
    except (TypeError, ValueError, OverflowError):
        return None
    if (
        points.ndim != 2
        or points.shape[1:] != (3,)
        or len(points) == 0
        or not np.isfinite(points).all()
        or triangles.ndim != 2
        or triangles.shape[1:] != (3,)
        or len(triangles) == 0
        or int(triangles.min()) < 0
        or int(triangles.max()) >= len(points)
    ):
        return None
    tri_points = points[triangles]
    twice_area = np.linalg.norm(
        np.cross(tri_points[:, 1] - tri_points[:, 0], tri_points[:, 2] - tri_points[:, 0]),
        axis=1,
    )
    if not np.isfinite(twice_area).all() or np.any(twice_area <= 0.0):
        return None
    return points, triangles


def _sample_surface(
    points: NDArray[np.float64],
    triangles: NDArray[np.int64],
    *,
    count: int,
    seed: int,
) -> tuple[NDArray[np.float64], NDArray[np.int64]]:
    tri_points = points[triangles]
    twice_area = np.linalg.norm(
        np.cross(tri_points[:, 1] - tri_points[:, 0], tri_points[:, 2] - tri_points[:, 0]),
        axis=1,
    )
    weights = twice_area / float(twice_area.sum())
    rng = np.random.default_rng(seed)
    indices = rng.choice(len(triangles), size=count, p=weights)
    r1 = rng.random(count)
    r2 = rng.random(count)
    root_r1 = np.sqrt(r1)
    sampled = (
        (1.0 - root_r1)[:, None] * tri_points[indices, 0]
        + (root_r1 * (1.0 - r2))[:, None] * tri_points[indices, 1]
        + (root_r1 * r2)[:, None] * tri_points[indices, 2]
    )
    return sampled.astype(np.float64), indices.astype(np.int64)


def _distance_stats(distances: NDArray[np.float64]) -> DirectedSurfaceDistance:
    return DirectedSurfaceDistance(
        rms=float(np.sqrt(np.mean(distances * distances))),
        p95=float(np.percentile(distances, 95)),
        p99=float(np.percentile(distances, 99)),
        maximum=float(np.max(distances)),
    )


def _closed_and_orientation_consistent(faces: NDArray[np.int64]) -> bool:
    """Require exactly two oppositely-directed triangle uses of each edge."""
    edge_directions: dict[tuple[int, int], list[bool]] = {}
    for triangle in faces:
        for first, second in (
            (int(triangle[0]), int(triangle[1])),
            (int(triangle[1]), int(triangle[2])),
            (int(triangle[2]), int(triangle[0])),
        ):
            key = (min(first, second), max(first, second))
            edge_directions.setdefault(key, []).append((first, second) == key)
    return all(
        len(directions) == 2 and directions[0] != directions[1]
        for directions in edge_directions.values()
    )


def _face_normals(points: NDArray[np.float64], triangles: NDArray[np.int64]) -> NDArray[np.float64]:
    tri_points = points[triangles]
    normals = np.cross(tri_points[:, 1] - tri_points[:, 0], tri_points[:, 2] - tri_points[:, 0])
    return normals / np.linalg.norm(normals, axis=1)[:, None]


def measure_gate4_exact_surface_metrics(
    source_vertices: object,
    source_faces: object,
    output_vertices: object,
    output_faces: object,
    *,
    sample_count: int = 4096,
) -> ExactSurfaceMetricRecord:
    """Measure controlled bidirectional surface distances without promotion.

    The function is intentionally geometry-only.  Callers must separately bind
    immutable source and output artifacts, and must not infer patch, physical
    group, provenance, signed-distance, or self-intersection authority here.
    """
    if (
        isinstance(sample_count, bool)
        or not isinstance(sample_count, int)
        or not 1 <= sample_count <= 20_000
    ):
        return _invalid_record("unverified_invalid_sample_count", 0)
    source = _as_finite_triangles(source_vertices, source_faces)
    output = _as_finite_triangles(output_vertices, output_faces)
    if source is None or output is None:
        return _invalid_record("unverified_invalid_finite_triangle_surface", sample_count)
    source_points, source_triangles = source
    output_points, output_triangles = output

    source_samples, source_sample_triangles = _sample_surface(
        source_points, source_triangles, count=sample_count, seed=0
    )
    output_samples, output_sample_triangles = _sample_surface(
        output_points, output_triangles, count=sample_count, seed=1
    )
    try:
        output_bvh = TriangleBVH.build(output_points, output_triangles)
        source_bvh = TriangleBVH.build(source_points, source_triangles)
        _, source_distances, nearest_output = output_bvh.closest_points_all_shared(source_samples)
        _, output_distances, nearest_source = source_bvh.closest_points_all_shared(output_samples)
    except Exception:
        return _invalid_record("unverified_exact_distance_query_failed", sample_count)
    if (
        not np.isfinite(source_distances).all()
        or not np.isfinite(output_distances).all()
        or np.any(nearest_output < 0)
        or np.any(nearest_source < 0)
    ):
        return _invalid_record("unverified_exact_distance_query_invalid", sample_count)

    source_to_output = _distance_stats(source_distances)
    output_to_source = _distance_stats(output_distances)
    available = [
        "distance.d_0_to_h.rms",
        "distance.d_0_to_h.p95",
        "distance.d_0_to_h.p99",
        "distance.d_0_to_h.max",
        "distance.d_h_to_0.rms",
        "distance.d_h_to_0.p95",
        "distance.d_h_to_0.p99",
        "distance.d_h_to_0.max",
        "distance.hausdorff_symmetric_sampled",
    ]
    normal_status = "unverified_surface_not_closed_or_orientation_consistent"
    normal_p95: float | None = None
    normal_p99: float | None = None
    normal_flipped: int | None = None
    if _closed_and_orientation_consistent(source_triangles) and _closed_and_orientation_consistent(
        output_triangles
    ):
        source_normals = _face_normals(source_points, source_triangles)
        output_normals = _face_normals(output_points, output_triangles)
        dots_a = np.einsum(
            "ij,ij->i", source_normals[source_sample_triangles], output_normals[nearest_output]
        )
        dots_b = np.einsum(
            "ij,ij->i", output_normals[output_sample_triangles], source_normals[nearest_source]
        )
        dots = np.clip(np.concatenate((dots_a, dots_b)), -1.0, 1.0)
        angles = np.degrees(np.arccos(dots))
        normal_p95 = float(np.percentile(angles, 95))
        normal_p99 = float(np.percentile(angles, 99))
        normal_flipped = int(np.count_nonzero(dots < 0.0))
        normal_status = "measured_closed_orientation_consistent"
        available.extend(("normals.p95_deg", "normals.p99_deg", "normals.flipped"))

    return ExactSurfaceMetricRecord(
        status="unverified_authority_incomplete",
        sample_count=sample_count,
        method="deterministic_area_samples+exact_point_to_triangle_bvh",
        source_to_output=source_to_output,
        output_to_source=output_to_source,
        symmetric_sampled_max=max(source_to_output.maximum, output_to_source.maximum),
        normal_status=normal_status,
        normal_p95_deg=normal_p95,
        normal_p99_deg=normal_p99,
        normal_flipped=normal_flipped,
        available_fields=tuple(available),
        unverified_fields=_UNVERIFIED_FIELDS,
        gate4_pass=False,
    )
