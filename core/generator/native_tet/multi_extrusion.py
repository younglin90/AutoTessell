"""Component-preserving rescue for one convex body with many extrusions."""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from scipy.spatial import ConvexHull

from core.generator.native_tet.thin_extrusion import build_thin_extrusion_wedges
from core.generator.native_tet.torus_wedge import _edge_components


@dataclass(frozen=True)
class MultiExtrusionMesh:
    points: np.ndarray
    cell_faces: list[list[list[int]]]
    n_components: int
    n_extrusions: int


def _oriented_surface_cell(
    points: np.ndarray,
    faces: np.ndarray,
) -> list[list[int]]:
    center = points.mean(axis=0)
    output: list[list[int]] = []
    for raw_face in faces:
        face = list(map(int, raw_face))
        polygon = points[np.asarray(face, dtype=np.int64)]
        normal = np.cross(
            polygon[1] - polygon[0], polygon[2] - polygon[0]
        )
        if float(np.dot(normal, polygon.mean(axis=0) - center)) < 0.0:
            face.reverse()
        output.append(face)
    return output


def build_multi_extrusions(
    vertices: np.ndarray,
    faces: np.ndarray,
    *,
    target_cells: int,
) -> MultiExtrusionMesh | None:
    """Preserve a small convex main body and repeated slender components."""
    surface_points = np.asarray(vertices, dtype=np.float64)
    surface_faces = np.asarray(faces, dtype=np.int64)
    components = _edge_components(surface_faces)
    if len(components) < 8:
        return None
    main_index = -1
    main_volume = -1.0
    for index, component in enumerate(components):
        candidate_vertex_ids = np.unique(surface_faces[component].reshape(-1))
        if len(candidate_vertex_ids) > 32 or len(component) > 64:
            continue
        candidate_hull = ConvexHull(surface_points[candidate_vertex_ids])
        if float(candidate_hull.volume) > main_volume:
            main_index = index
            main_volume = float(candidate_hull.volume)
    if main_index < 0:
        return None
    main_component = components[main_index]
    main_vertex_ids = np.unique(surface_faces[main_component].reshape(-1))
    if len(main_vertex_ids) > 32 or len(main_component) > 64:
        return None
    main_points = surface_points[main_vertex_ids]
    main_hull = ConvexHull(main_points)
    if main_hull.volume <= 0.0:
        return None
    main_map = {
        int(global_id): local for local, global_id in enumerate(main_vertex_ids)
    }
    main_faces = np.asarray(
        [
            [main_map[int(vertex)] for vertex in surface_faces[face_index]]
            for face_index in main_component
        ],
        dtype=np.int64,
    )

    generated_points = main_points.tolist()
    cell_faces: list[list[list[int]]] = [
        _oriented_surface_cell(main_points, main_faces)
    ]
    extrusion_count = 0
    per_component_target = max(8, int(target_cells) // len(components))
    for component_index, component in enumerate(components):
        if component_index == main_index:
            continue
        vertex_ids = np.unique(surface_faces[component].reshape(-1))
        local_points = surface_points[vertex_ids]
        local_map = {
            int(global_id): local for local, global_id in enumerate(vertex_ids)
        }
        local_faces = np.asarray(
            [
                [local_map[int(vertex)] for vertex in surface_faces[face_index]]
                for face_index in component
            ],
            dtype=np.int64,
        )
        extrusion = build_thin_extrusion_wedges(
            local_points,
            local_faces,
            target_cells=per_component_target,
            bl_layers=1,
            min_bbox_aspect=5.0,
        )
        if extrusion is None:
            return None
        offset = len(generated_points)
        generated_points.extend(extrusion.points.tolist())
        cell_faces.extend(
            [
                [[offset + int(vertex) for vertex in face] for face in cell]
                for cell in extrusion.cell_faces
            ]
        )
        extrusion_count += 1
    return MultiExtrusionMesh(
        points=np.asarray(generated_points, dtype=np.float64),
        cell_faces=cell_faces,
        n_components=len(components),
        n_extrusions=extrusion_count,
    )


__all__ = ["MultiExtrusionMesh", "build_multi_extrusions"]
