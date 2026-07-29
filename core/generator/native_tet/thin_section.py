"""Report-only local thickness census for native-tet diagnostics.

This module never changes points or connectivity and is deliberately not wired into
the production mesher. It casts deterministic inward rays from boundary triangle
centroids to estimate an opposing boundary distance. Unknown rays are retained
instead of being converted into a guessed thickness. The result is a screening
measurement for thin-section work, not a geometry guarantee.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import numpy as np
from numpy.typing import NDArray

_FACE_SLOTS = ((0, 1, 2, 3), (0, 1, 3, 2), (0, 2, 3, 1), (1, 2, 3, 0))


@dataclass(frozen=True)
class ThinSectionReport:
    n_points: int
    n_tets: int
    n_boundary_faces: int
    n_degenerate_boundary_faces: int
    n_ray_hits: int
    n_unknown_rays: int
    hit_fraction: float
    min_thickness: float | None
    p10_thickness: float | None
    median_thickness: float | None
    max_thickness: float | None
    thickness_values: tuple[float, ...]
    min_through_thickness_cells: int | None
    p10_through_thickness_cells: float | None
    median_through_thickness_cells: float | None
    max_through_thickness_cells: int | None
    through_thickness_cell_counts: tuple[int, ...]

    def as_dict(self) -> dict[str, Any]:
        return {
            "n_points": self.n_points,
            "n_tets": self.n_tets,
            "n_boundary_faces": self.n_boundary_faces,
            "n_degenerate_boundary_faces": self.n_degenerate_boundary_faces,
            "n_ray_hits": self.n_ray_hits,
            "n_unknown_rays": self.n_unknown_rays,
            "hit_fraction": self.hit_fraction,
            "min_thickness": self.min_thickness,
            "p10_thickness": self.p10_thickness,
            "median_thickness": self.median_thickness,
            "max_thickness": self.max_thickness,
            "thickness_values": list(self.thickness_values),
            "min_through_thickness_cells": self.min_through_thickness_cells,
            "p10_through_thickness_cells": self.p10_through_thickness_cells,
            "median_through_thickness_cells": self.median_through_thickness_cells,
            "max_through_thickness_cells": self.max_through_thickness_cells,
            "through_thickness_cell_counts": list(self.through_thickness_cell_counts),
        }


def _boundary_faces(
    points: NDArray[Any], tets: NDArray[Any]
) -> tuple[list[tuple[int, int, int]], list[tuple[int, tuple[int, int, int]]]]:
    del points
    tet_arr = np.asarray(tets, dtype=np.int64).reshape((-1, 4))
    candidates: list[tuple[tuple[int, int, int], tuple[int, int, int], int]] = []
    for tet_id, tet in enumerate(tet_arr):
        for ia, ib, ic, opposite in _FACE_SLOTS:
            face = (int(tet[ia]), int(tet[ib]), int(tet[ic]))
            key = tuple(sorted(face))
            candidates.append((key, face, tet_id))

    by_key: dict[tuple[int, int, int], list[tuple[tuple[int, int, int], int]]] = {}
    for key, face, tet_id in candidates:
        by_key.setdefault(key, []).append((face, tet_id))

    boundary: list[tuple[int, tuple[int, int, int]]] = []
    for key in sorted(by_key):
        owners = by_key[key]
        if len(owners) == 1:
            face, tet_id = owners[0]
            boundary.append((tet_id, face))
    return [face for _, face in boundary], boundary


def _oriented_boundary_data(
    points: NDArray[Any], tets: NDArray[Any]
) -> list[tuple[tuple[int, int, int], int, NDArray[np.float64], NDArray[np.float64], float]]:
    pts = np.asarray(points, dtype=np.float64)
    tet_arr = np.asarray(tets, dtype=np.int64).reshape((-1, 4))
    _, boundary = _boundary_faces(pts, tet_arr)
    out: list[tuple[tuple[int, int, int], int, NDArray[np.float64], NDArray[np.float64], float]] = (
        []
    )
    for tet_id, face in boundary:
        a, b, c = pts[list(face)]
        opposite_id = next(int(v) for v in tet_arr[tet_id] if int(v) not in face)
        opposite = pts[opposite_id]
        raw = np.cross(b - a, c - a)
        norm = float(np.linalg.norm(raw))
        if not np.isfinite(norm) or norm <= 1e-30:
            out.append((tuple(sorted(face)), tet_id, (a + b + c) / 3.0, raw, 0.0))
            continue
        normal = raw / norm
        if float(np.dot(normal, opposite - a)) > 0.0:
            normal = -normal
        out.append((tuple(sorted(face)), tet_id, (a + b + c) / 3.0, normal, 0.5 * norm))
    return out


def _ray_triangle_distance(
    origin: NDArray[np.float64],
    direction: NDArray[np.float64],
    triangle: NDArray[np.float64],
    epsilon: float,
) -> float | None:
    edge1 = triangle[1] - triangle[0]
    edge2 = triangle[2] - triangle[0]
    h = np.cross(direction, edge2)
    determinant = float(np.dot(edge1, h))
    if abs(determinant) <= epsilon:
        return None
    inv_det = 1.0 / determinant
    s = origin - triangle[0]
    u = inv_det * float(np.dot(s, h))
    if u < -epsilon or u > 1.0 + epsilon:
        return None
    q = np.cross(s, edge1)
    v = inv_det * float(np.dot(direction, q))
    if v < -epsilon or u + v > 1.0 + epsilon:
        return None
    distance = inv_det * float(np.dot(edge2, q))
    if distance <= epsilon:
        return None
    return distance


def _ray_tet_interval(
    origin: NDArray[np.float64],
    direction: NDArray[np.float64],
    tet: NDArray[np.float64],
    epsilon: float,
) -> tuple[float, float] | None:
    """Return the positive ray interval contained in one convex tetrahedron.

    A tetrahedron is represented by its four inward half spaces.  This avoids
    sampling along the ray and makes the reported cell count independent of a
    chosen step size.  A zero-length touch at a face, edge, or vertex is not a
    traversed cell.
    """
    lower = 0.0
    upper = float("inf")
    for face_slots in _FACE_SLOTS:
        ia, ib, ic, opposite_slot = face_slots
        a, b, c = tet[[ia, ib, ic]]
        opposite = tet[opposite_slot]
        normal = np.cross(b - a, c - a)
        orient = float(np.dot(normal, opposite - a))
        if not np.isfinite(orient) or abs(orient) <= epsilon:
            return None
        offset = float(np.dot(normal, origin - a))
        slope = float(np.dot(normal, direction))
        # The interior is the side containing the omitted tet vertex.
        if orient < 0.0:
            offset = -offset
            slope = -slope
        if abs(slope) <= epsilon:
            if offset < -epsilon:
                return None
            continue
        crossing = (-epsilon - offset) / slope
        if slope > 0.0:
            lower = max(lower, crossing)
        else:
            upper = min(upper, crossing)
        if upper <= lower + epsilon:
            return None
    if upper <= epsilon:
        return None
    return max(lower, 0.0), upper


def _count_traversed_tets(
    points: NDArray[np.float64],
    tets: NDArray[np.int64],
    tet_bounds_min: NDArray[np.float64],
    tet_bounds_max: NDArray[np.float64],
    origin: NDArray[np.float64],
    direction: NDArray[np.float64],
    hit_distance: float,
    epsilon: float,
) -> int:
    """Count tetrahedra with non-zero ray overlap before the opposing hit."""
    lower = np.zeros(tets.shape[0], dtype=np.float64)
    upper = np.full(tets.shape[0], hit_distance, dtype=np.float64)
    valid = np.ones(tets.shape[0], dtype=bool)
    for axis in range(3):
        component = float(direction[axis])
        if abs(component) <= epsilon:
            valid &= (origin[axis] >= tet_bounds_min[:, axis] - epsilon) & (
                origin[axis] <= tet_bounds_max[:, axis] + epsilon
            )
            continue
        enter = (tet_bounds_min[:, axis] - origin[axis]) / component
        leave = (tet_bounds_max[:, axis] - origin[axis]) / component
        lower = np.maximum(lower, np.minimum(enter, leave))
        upper = np.minimum(upper, np.maximum(enter, leave))
    candidate_ids = np.flatnonzero(valid & (upper > lower + epsilon))
    count = 0
    for tet_index in candidate_ids:
        tet_ids = tets[int(tet_index)]
        interval = _ray_tet_interval(origin, direction, points[tet_ids], epsilon)
        if interval is None:
            continue
        start, end = interval
        if min(end, hit_distance) > start + epsilon:
            count += 1
    return count


def estimate_boundary_thickness(
    points: NDArray[Any],
    tets: NDArray[Any],
    *,
    skip_shared_vertex_faces: bool = True,
    candidate_faces: int = 64,
) -> ThinSectionReport:
    """Estimate opposing-boundary distances using deterministic inward rays.

    The ray starts just inside each non-degenerate boundary triangle and travels
    opposite to its outward normal. A ray that has no reliable opposing hit is
    counted as unknown. This is intentionally conservative and report-only.
    """
    pts = np.asarray(points, dtype=np.float64)
    tet_arr = np.asarray(tets, dtype=np.int64).reshape((-1, 4))
    if pts.ndim != 2 or pts.shape[1] != 3:
        raise ValueError("points must have shape (N, 3)")
    if tet_arr.size and (tet_arr.min() < 0 or tet_arr.max() >= pts.shape[0]):
        raise ValueError("tets contain an out-of-range point index")
    boundary = _oriented_boundary_data(pts, tet_arr)
    if candidate_faces <= 0:
        raise ValueError("candidate_faces must be positive")
    if not boundary:
        return ThinSectionReport(
            n_points=int(pts.shape[0]),
            n_tets=int(tet_arr.shape[0]),
            n_boundary_faces=0,
            n_degenerate_boundary_faces=0,
            n_ray_hits=0,
            n_unknown_rays=0,
            hit_fraction=0.0,
            min_thickness=None,
            p10_thickness=None,
            median_thickness=None,
            max_thickness=None,
            thickness_values=(),
            min_through_thickness_cells=None,
            p10_through_thickness_cells=None,
            median_through_thickness_cells=None,
            max_through_thickness_cells=None,
            through_thickness_cell_counts=(),
        )

    scale = float(np.ptp(pts, axis=0).max()) if pts.size else 1.0
    scale = max(scale, 1.0)
    epsilon = max(1e-12 * scale, 1e-14)
    values: list[float] = []
    cell_counts: list[int] = []
    tet_vertices = pts[tet_arr]
    tet_bounds_min = tet_vertices.min(axis=1)
    tet_bounds_max = tet_vertices.max(axis=1)
    degenerate = 0

    centers = np.asarray([row[2] for row in boundary], dtype=np.float64)
    try:
        from scipy.spatial import cKDTree

        center_tree = cKDTree(centers)
    except Exception:  # pragma: no cover - scipy is optional in library use.
        center_tree = None

    for face_index, (key, _, center, normal, twice_area) in enumerate(boundary):
        if twice_area <= 1e-30 or not np.all(np.isfinite(normal)):
            degenerate += 1
            continue
        face_vertices = set(key)
        face_size = max(
            float(np.linalg.norm(pts[key[1]] - pts[key[0]])),
            float(np.linalg.norm(pts[key[2]] - pts[key[0]])),
            float(np.linalg.norm(pts[key[2]] - pts[key[1]])),
        )
        origin = center - normal * max(epsilon, 1e-9 * max(face_size, scale))
        best: float | None = None
        if center_tree is not None:
            k = min(int(candidate_faces), len(boundary))
            _, candidate_indices = center_tree.query(center, k=k)
            candidate_indices = np.atleast_1d(candidate_indices).astype(np.int64)
            candidate_indices = np.asarray(
                sorted(set(int(index) for index in candidate_indices)), dtype=np.int64
            )
        else:
            # Without scipy, use a deterministic bounded candidate set rather
            # than silently returning to the O(F^2) implementation.
            k = min(int(candidate_faces), len(boundary))
            candidate_indices = np.linspace(0, len(boundary) - 1, num=k, dtype=np.int64)
        for target_index in candidate_indices:
            if int(target_index) == face_index:
                continue
            target_key, _, _target_center, _, target_area = boundary[int(target_index)]
            if target_key == key or target_area <= 1e-30:
                continue
            if skip_shared_vertex_faces and face_vertices.intersection(target_key):
                continue
            target_triangle = pts[list(target_key)]
            distance = _ray_triangle_distance(origin, -normal, target_triangle, epsilon)
            if distance is not None and (best is None or distance < best):
                best = distance
        if best is not None and np.isfinite(best):
            values.append(float(best))
            cell_counts.append(
                _count_traversed_tets(
                    pts,
                    tet_arr,
                    tet_bounds_min,
                    tet_bounds_max,
                    origin,
                    -normal,
                    float(best),
                    epsilon,
                )
            )

    values.sort()
    hit_count = len(values)
    total = len(boundary)
    stats = np.asarray(values, dtype=np.float64)
    count_stats = np.asarray(cell_counts, dtype=np.float64)
    return ThinSectionReport(
        n_points=int(pts.shape[0]),
        n_tets=int(tet_arr.shape[0]),
        n_boundary_faces=total,
        n_degenerate_boundary_faces=degenerate,
        n_ray_hits=hit_count,
        n_unknown_rays=max(0, total - degenerate - hit_count),
        hit_fraction=float(hit_count / total) if total else 0.0,
        min_thickness=float(stats[0]) if hit_count else None,
        p10_thickness=float(np.quantile(stats, 0.10, method="linear")) if hit_count else None,
        median_thickness=float(np.median(stats)) if hit_count else None,
        max_thickness=float(stats[-1]) if hit_count else None,
        thickness_values=tuple(float(value) for value in stats),
        min_through_thickness_cells=int(count_stats.min()) if hit_count else None,
        p10_through_thickness_cells=(
            float(np.quantile(count_stats, 0.10, method="linear")) if hit_count else None
        ),
        median_through_thickness_cells=float(np.median(count_stats)) if hit_count else None,
        max_through_thickness_cells=int(count_stats.max()) if hit_count else None,
        through_thickness_cell_counts=tuple(int(count) for count in cell_counts),
    )
