"""Exact, report-only triangle-to-three-quad source-surface subdivision.

This module is deliberately disconnected from native-hex routing and writers.
It accepts only a finite, consistently oriented closed triangular two-manifold,
then preserves each source vertex exactly and subdivides every triangle in its
own plane using its three edge midpoints and centroid.  No input array is
mutated and every returned quad carries its immutable source-face owner.
"""

from __future__ import annotations

from collections import Counter
from collections.abc import Sequence
from dataclasses import dataclass

import numpy as np


# Conventional hexahedron face cycles.  Consumers use these only as topology.
_HEX_FACES: tuple[tuple[int, int, int, int], ...] = (
    (0, 1, 2, 3),
    (4, 7, 6, 5),
    (0, 4, 5, 1),
    (1, 5, 6, 2),
    (2, 6, 7, 3),
    (3, 7, 4, 0),
)


@dataclass(frozen=True)
class SourceQuadization:
    """Immutable result of the report-only exact source quadization."""

    accepted: bool
    reason: str
    points: np.ndarray
    quads: np.ndarray
    source_face_ids: np.ndarray
    source_entities: tuple[tuple[str, str], ...]
    source_edge_midpoint_ids: tuple[tuple[int, int, int], ...]
    max_support_distance: float
    max_relative_area_error: float


def _rejected(
    reason: str, entities: tuple[tuple[str, str], ...] = ()
) -> SourceQuadization:
    return SourceQuadization(
        False,
        reason,
        np.empty((0, 3), dtype=np.float64),
        np.empty((0, 4), dtype=np.int64),
        np.empty(0, dtype=np.int64),
        entities,
        (),
        float("inf"),
        float("inf"),
    )


def _as_exact_inputs(
    vertices: np.ndarray, faces: np.ndarray, face_entities: Sequence[tuple[str, str]]
) -> tuple[np.ndarray, np.ndarray, tuple[tuple[str, str], ...]] | None:
    """Validate without coercing non-integral connectivity into a new mesh."""
    raw_points = np.asarray(vertices)
    raw_faces = np.asarray(faces)
    if raw_points.ndim != 2 or raw_points.shape[1:] != (3,) or not np.issubdtype(raw_points.dtype, np.number):
        return None
    if raw_faces.ndim != 2 or raw_faces.shape[1:] != (3,) or not np.issubdtype(raw_faces.dtype, np.integer):
        return None
    points = np.asarray(raw_points, dtype=np.float64)
    triangles = np.asarray(raw_faces, dtype=np.int64)
    entities = tuple(face_entities)
    if (
        not len(points)
        or not len(triangles)
        or not np.all(np.isfinite(points))
        or len(entities) != len(triangles)
        or any(len(entity) != 2 or not all(isinstance(value, str) for value in entity) for entity in entities)
        or np.any(triangles < 0)
        or np.any(triangles >= len(points))
    ):
        return None
    return points, triangles, entities


def _closed_oriented_manifold(triangles: np.ndarray) -> bool:
    """Require every source edge to have one oppositely directed neighbour."""
    directed: Counter[tuple[int, int]] = Counter()
    for face in triangles:
        if len({int(vertex) for vertex in face}) != 3:
            return False
        for first, second in zip(face, np.roll(face, -1), strict=True):
            directed[(int(first), int(second))] += 1
    return bool(directed) and all(
        count == 1 and directed.get((end, start), 0) == 1
        for (start, end), count in directed.items()
    )


def quadize_triangles_exact_l0(
    vertices: np.ndarray,
    faces: np.ndarray,
    face_entities: Sequence[tuple[str, str]],
    *,
    tolerance: float = 1.0e-12,
) -> SourceQuadization:
    """Return exactly three planar quads per source triangle, or reject safely."""
    if not np.isfinite(tolerance) or tolerance < 0.0:
        return _rejected("invalid_tolerance")
    parsed = _as_exact_inputs(vertices, faces, face_entities)
    if parsed is None:
        return _rejected("invalid_source_input")
    points, triangles, entities = parsed
    if not _closed_oriented_manifold(triangles):
        return _rejected("source_not_oriented_closed_manifold", entities)

    source_triangles = points[triangles]
    doubled_areas = np.linalg.norm(
        np.cross(source_triangles[:, 1] - source_triangles[:, 0], source_triangles[:, 2] - source_triangles[:, 0]),
        axis=1,
    )
    if np.any(doubled_areas <= tolerance):
        return _rejected("degenerate_source_triangle", entities)

    output_points: list[np.ndarray] = [point.copy() for point in points]
    midpoint_ids: dict[tuple[int, int], int] = {}
    midpoint_records: list[tuple[int, int, int]] = []
    centroid_ids: list[int] = []
    for face in triangles:
        centroid_ids.append(len(output_points))
        output_points.append(np.mean(points[face], axis=0))
        for first, second in zip(face, np.roll(face, -1), strict=True):
            edge = tuple(sorted((int(first), int(second))))
            if edge not in midpoint_ids:
                midpoint_ids[edge] = len(output_points)
                midpoint_records.append((edge[0], edge[1], len(output_points)))
                output_points.append((points[edge[0]] + points[edge[1]]) * 0.5)

    quads: list[tuple[int, int, int, int]] = []
    owners: list[int] = []
    for face_id, face in enumerate(triangles):
        first, second, third = (int(vertex) for vertex in face)
        first_second = midpoint_ids[tuple(sorted((first, second)))]
        second_third = midpoint_ids[tuple(sorted((second, third)))]
        third_first = midpoint_ids[tuple(sorted((third, first)))]
        centroid = centroid_ids[face_id]
        quads.extend(
            (
                (first, first_second, centroid, third_first),
                (first_second, second, second_third, centroid),
                (centroid, second_third, third, third_first),
            )
        )
        owners.extend((face_id, face_id, face_id))

    output = np.asarray(output_points, dtype=np.float64)
    quad_array = np.asarray(quads, dtype=np.int64)
    owner_array = np.asarray(owners, dtype=np.int64)
    # Construction is algebraically coplanar.  Compute rather than claim it.
    support_distance = 0.0
    relative_area_error = 0.0
    for face_id, face in enumerate(triangles):
        tri = points[face]
        normal = np.cross(tri[1] - tri[0], tri[2] - tri[0])
        normal_length = float(np.linalg.norm(normal))
        owned = quad_array[owner_array == face_id]
        support_distance = max(
            support_distance,
            float(np.max(np.abs((output[owned] - tri[0]) @ normal) / normal_length)),
        )
        quad_area = 0.0
        for quad in owned:
            coordinates = output[quad]
            quad_area += 0.5 * float(np.linalg.norm(np.cross(coordinates[1] - coordinates[0], coordinates[2] - coordinates[0])))
            quad_area += 0.5 * float(np.linalg.norm(np.cross(coordinates[2] - coordinates[0], coordinates[3] - coordinates[0])))
        triangle_area = 0.5 * normal_length
        relative_area_error = max(relative_area_error, abs(quad_area - triangle_area) / triangle_area)

    # Midpoints and centroids are constructed in the source plane.  Suppress
    # only round-off below the caller's declared exact-audit tolerance.
    if support_distance <= tolerance:
        support_distance = 0.0
    if relative_area_error <= tolerance:
        relative_area_error = 0.0

    return SourceQuadization(
        True,
        "accepted_exact_three_quad_subdivision",
        output,
        quad_array,
        owner_array,
        entities,
        tuple(midpoint_records),
        support_distance,
        relative_area_error,
    )


def all_quad_ball_precheck_l1(points: np.ndarray, quads: np.ndarray) -> tuple[bool, int]:
    """Return the closed all-quad genus-zero precheck and Euler characteristic."""
    coordinates = np.asarray(points, dtype=np.float64)
    cells = np.asarray(quads, dtype=np.int64)
    if (
        coordinates.ndim != 2
        or coordinates.shape[1:] != (3,)
        or not np.all(np.isfinite(coordinates))
        or cells.ndim != 2
        or cells.shape[1:] != (4,)
        or not len(cells)
        or np.any(cells < 0)
        or np.any(cells >= len(coordinates))
    ):
        return False, 0
    edges: Counter[tuple[int, int]] = Counter()
    used: set[int] = set()
    for quad in cells:
        if len({int(vertex) for vertex in quad}) != 4:
            return False, 0
        used.update(int(vertex) for vertex in quad)
        for first, second in zip(quad, np.roll(quad, -1), strict=True):
            edges[tuple(sorted((int(first), int(second))))] += 1
    characteristic = len(used) - len(edges) + len(cells)
    # A connected closed all-quad genus-zero surface is the required sphere precheck.
    adjacency: dict[int, set[int]] = {vertex: set() for vertex in used}
    for first, second in edges:
        adjacency[first].add(second)
        adjacency[second].add(first)
    pending = [next(iter(used))]
    visited: set[int] = set()
    while pending:
        vertex = pending.pop()
        if vertex not in visited:
            visited.add(vertex)
            pending.extend(adjacency[vertex] - visited)
    accepted = all(count == 2 for count in edges.values()) and visited == used and characteristic == 2
    return accepted, characteristic


def extrude_exact_quad_shell_l1(
    points: np.ndarray, quads: np.ndarray, *, scale: float = 0.8
) -> tuple[np.ndarray, np.ndarray]:
    """Build a report-only centroid shell; caller owns validity acceptance."""
    coordinates = np.asarray(points, dtype=np.float64)
    cells = np.asarray(quads, dtype=np.int64)
    if (
        not np.isfinite(scale)
        or not 0.0 < scale < 1.0
        or coordinates.ndim != 2
        or coordinates.shape[1:] != (3,)
        or cells.ndim != 2
        or cells.shape[1:] != (4,)
        or np.any(cells < 0)
        or np.any(cells >= len(coordinates))
    ):
        raise ValueError("invalid exact-quad shell input")
    center = np.mean(coordinates, axis=0)
    inner = center + scale * (coordinates - center)
    shell_points = np.vstack((coordinates.copy(), inner))
    # Source triangle orientation is outward.  Reversing the outer cycle yields
    # a positive local volume for the inward copy under the native hex convention.
    outer = cells[:, ::-1]
    shell_hexes = np.hstack((outer, outer + len(coordinates))).astype(np.int64, copy=False)
    return shell_points, shell_hexes
