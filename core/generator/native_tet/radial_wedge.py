"""Radial wedge rescue for spherical surfaces with tiny convex features."""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from scipy.spatial import ConvexHull

from core.generator.native_tet.torus_wedge import _edge_components


@dataclass(frozen=True)
class RadialWedgeMesh:
    points: np.ndarray
    cell_faces: list[list[list[int]]]
    n_components: int
    n_sphere_faces: int
    n_radial_shells: int


def _orient_faces(
    points: list[list[float]],
    raw_faces: list[list[int]],
    cell_vertex_ids: list[int],
) -> list[list[int]]:
    array = np.asarray(points, dtype=np.float64)
    cell_center = array[np.asarray(cell_vertex_ids, dtype=np.int64)].mean(axis=0)
    output: list[list[int]] = []
    for raw_face in raw_faces:
        face = list(raw_face)
        polygon = array[np.asarray(face, dtype=np.int64)]
        normal = np.zeros(3, dtype=np.float64)
        for index in range(1, len(polygon) - 1):
            normal += np.cross(
                polygon[index] - polygon[0],
                polygon[index + 1] - polygon[0],
            )
        if float(np.dot(normal, polygon.mean(axis=0) - cell_center)) < 0.0:
            face.reverse()
        output.append(face)
    return output


def build_radial_wedges(
    vertices: np.ndarray,
    faces: np.ndarray,
    *,
    radial_levels: tuple[float, ...] = (0.8, 0.95, 0.99, 1.0),
    target_cells: int | None = None,
    bl_layers: int = 3,
) -> RadialWedgeMesh | None:
    """Build sphere star tets, radial wedges, and preserved tiny poly cells."""
    surface_points = np.asarray(vertices, dtype=np.float64)
    surface_faces = np.asarray(faces, dtype=np.int64)
    components = _edge_components(surface_faces)
    if not components:
        return None
    components.sort(key=len, reverse=True)
    sphere_component = components[0]
    sphere_vertex_ids = np.unique(surface_faces[sphere_component].reshape(-1))
    sphere_points = surface_points[sphere_vertex_ids]
    lower = sphere_points.min(axis=0)
    upper = sphere_points.max(axis=0)
    extents = upper - lower
    if np.min(extents) <= 0.0 or float(np.max(extents) / np.min(extents)) > 1.05:
        return None
    center = 0.5 * (lower + upper)
    radii = np.linalg.norm(sphere_points - center, axis=1)
    mean_radius = float(np.mean(radii))
    if mean_radius <= 0.0 or float(np.ptp(radii) / mean_radius) > 0.05:
        return None
    levels = tuple(float(level) for level in radial_levels)
    if (
        len(levels) < 2
        or levels[-1] != 1.0
        or any(left <= 0.0 or left >= right for left, right in zip(levels, levels[1:]))
    ):
        return None

    global_to_local = {
        int(vertex_id): local for local, vertex_id in enumerate(sphere_vertex_ids)
    }
    sphere_triangles = np.asarray(
        [
            [global_to_local[int(vertex)] for vertex in surface_faces[face_index]]
            for face_index in sphere_component
        ],
        dtype=np.int64,
    )
    if target_cells is not None and int(target_cells) > 0:
        estimated_bl_cells = len(sphere_triangles) * max(int(bl_layers), 0)
        target_radial_cells = max(
            len(sphere_triangles) * 4,
            int(target_cells) - estimated_bl_cells,
        )
        n_levels = int(
            np.clip(
                round(target_radial_cells / max(len(sphere_triangles), 1)),
                4,
                32,
            )
        )
        levels = tuple(np.linspace(0.15, 1.0, n_levels).tolist())
    generated_points: list[list[float]] = []
    level_starts: list[int] = []
    for level in levels:
        level_starts.append(len(generated_points))
        generated_points.extend(
            (center + level * (sphere_points - center)).tolist()
        )
    center_id = len(generated_points)
    generated_points.append(center.tolist())
    cell_faces: list[list[list[int]]] = []
    for triangle in sphere_triangles:
        a, b, c = map(int, triangle)
        inner = [
            center_id,
            level_starts[0] + a,
            level_starts[0] + b,
            level_starts[0] + c,
        ]
        cell_faces.append(
            _orient_faces(
                generated_points,
                [
                    [inner[0], inner[1], inner[2]],
                    [inner[0], inner[3], inner[1]],
                    [inner[1], inner[3], inner[2]],
                    [inner[2], inner[3], inner[0]],
                ],
                inner,
            )
        )
        for lower_start, upper_start in zip(level_starts, level_starts[1:]):
            ids = [
                lower_start + a,
                lower_start + b,
                lower_start + c,
                upper_start + a,
                upper_start + b,
                upper_start + c,
            ]
            cell_faces.append(
                _orient_faces(
                    generated_points,
                    [
                        [ids[0], ids[1], ids[2]],
                        [ids[3], ids[5], ids[4]],
                        [ids[0], ids[3], ids[4], ids[1]],
                        [ids[1], ids[4], ids[5], ids[2]],
                        [ids[2], ids[5], ids[3], ids[0]],
                    ],
                    ids,
                )
            )

    sphere_area = 0.0
    for triangle in sphere_triangles:
        polygon = sphere_points[triangle]
        sphere_area += 0.5 * float(
            np.linalg.norm(
                np.cross(polygon[1] - polygon[0], polygon[2] - polygon[0])
            )
        )
    for component in components[1:]:
        vertex_ids = np.unique(surface_faces[component].reshape(-1))
        component_points = surface_points[vertex_ids]
        component_faces = surface_faces[component]
        if len(vertex_ids) > 32 or len(component_faces) > 64:
            return None
        hull = ConvexHull(component_points)
        if hull.volume <= 0.0:
            return None
        component_area = float(hull.area)
        if component_area >= 0.01 * sphere_area:
            return None
        start = len(generated_points)
        generated_points.extend(component_points.tolist())
        local = {int(vertex_id): index for index, vertex_id in enumerate(vertex_ids)}
        raw_faces = [
            [start + local[int(vertex)] for vertex in surface_faces[face_index]]
            for face_index in component
        ]
        cell_vertices = list(range(start, start + len(component_points)))
        cell_faces.append(
            _orient_faces(generated_points, raw_faces, cell_vertices)
        )

    return RadialWedgeMesh(
        points=np.asarray(generated_points, dtype=np.float64),
        cell_faces=cell_faces,
        n_components=len(components),
        n_sphere_faces=len(sphere_triangles),
        n_radial_shells=len(levels) - 1,
    )


__all__ = ["RadialWedgeMesh", "build_radial_wedges"]
