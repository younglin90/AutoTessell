"""Structured wedge mesh for a convex slab crossed by repeated tools."""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from scipy.spatial import ConvexHull

from core.generator.native_tet.torus_wedge import _edge_components


@dataclass(frozen=True)
class PerforatedExtrusionMesh:
    points: np.ndarray
    cell_faces: list[list[list[int]]]
    reference_vertices: np.ndarray
    reference_faces: np.ndarray
    extrusion_axis: int
    n_holes: int
    n_slabs: int
    n_cap_triangles: int


def _main_component(
    points: np.ndarray,
    faces: np.ndarray,
    components: list[np.ndarray],
) -> tuple[int, np.ndarray, np.ndarray] | None:
    best: tuple[float, int, np.ndarray, np.ndarray] | None = None
    for index, component in enumerate(components):
        vertex_ids = np.unique(faces[component].reshape(-1))
        if len(vertex_ids) > 32 or len(component) > 64:
            continue
        local_points = points[vertex_ids]
        try:
            volume = float(ConvexHull(local_points).volume)
        except Exception:
            continue
        if best is None or volume > best[0]:
            best = (volume, index, vertex_ids, local_points)
    if best is None or best[0] <= 0.0:
        return None
    return best[1], best[2], best[3]


def _signed_area_2d(points: np.ndarray) -> float:
    first = points[1] - points[0]
    second = points[2] - points[0]
    return float(first[0] * second[1] - first[1] * second[0])


def _boundary_edges(triangles: np.ndarray) -> list[tuple[int, int, int]]:
    records: dict[tuple[int, int], list[tuple[int, int, int]]] = {}
    for raw in triangles:
        a, b, c = map(int, raw)
        for first, second, opposite in ((a, b, c), (b, c, a), (c, a, b)):
            records.setdefault(tuple(sorted((first, second))), []).append(
                (first, second, opposite)
            )
    return [values[0] for values in records.values() if len(values) == 1]


def _orient_triangle(
    points: np.ndarray,
    face: list[int],
    outward: np.ndarray,
) -> list[int]:
    polygon = points[np.asarray(face, dtype=np.int64)]
    normal = np.cross(polygon[1] - polygon[0], polygon[2] - polygon[0])
    if float(np.dot(normal, outward)) < 0.0:
        return [face[0], face[2], face[1]]
    return face


def build_perforated_extrusion_wedges(
    vertices: np.ndarray,
    faces: np.ndarray,
    *,
    target_cells: int,
    bl_layers: int = 3,
) -> PerforatedExtrusionMesh | None:
    """Infer slab-minus-through-tools semantics and build non-overlapping wedges."""
    points = np.asarray(vertices, dtype=np.float64)
    triangles = np.asarray(faces, dtype=np.int64)
    components = _edge_components(triangles)
    if len(components) < 8:
        return None
    main = _main_component(points, triangles, components)
    if main is None:
        return None
    main_index, _, main_points = main
    main_lower = main_points.min(axis=0)
    main_upper = main_points.max(axis=0)
    main_extent = main_upper - main_lower
    tolerance = max(float(np.max(main_extent)), 1.0) * 1e-7

    tool_data: list[tuple[np.ndarray, np.ndarray]] = []
    for index, component in enumerate(components):
        if index == main_index:
            continue
        vertex_ids = np.unique(triangles[component].reshape(-1))
        local_points = points[vertex_ids]
        if len(local_points) < 6:
            return None
        tool_data.append((component, local_points))

    axis_scores = []
    for axis in range(3):
        crossed = sum(
            float(local[:, axis].min()) < main_lower[axis] - tolerance
            and float(local[:, axis].max()) > main_upper[axis] + tolerance
            for _, local in tool_data
        )
        axis_scores.append(int(crossed))
    axis = int(np.argmax(axis_scores))
    if axis_scores[axis] != len(tool_data):
        return None
    uv_axes = tuple(index for index in range(3) if index != axis)

    outer_cloud = np.unique(main_points[:, uv_axes], axis=0)
    outer_hull = ConvexHull(outer_cloud)
    outer_loop = outer_cloud[outer_hull.vertices]
    if len(outer_loop) < 3:
        return None

    hole_loops: list[np.ndarray] = []
    hole_centres: list[tuple[float, float]] = []
    hole_area = 0.0
    for _, local_points in tool_data:
        projected = np.unique(local_points[:, uv_axes], axis=0)
        try:
            hull = ConvexHull(projected)
        except Exception:
            return None
        loop = projected[hull.vertices]
        if len(loop) > 8:
            sample = np.linspace(0, len(loop), 8, endpoint=False, dtype=np.int64)
            loop = loop[sample]
        centre = loop.mean(axis=0)
        signed = (
            centre @ outer_hull.equations[:, :2].T
            + outer_hull.equations[:, 2]
        )
        if np.any(signed >= -tolerance):
            return None
        hole_loops.append(loop)
        hole_centres.append((float(centre[0]), float(centre[1])))
        hole_area += float(hull.volume)

    try:
        import meshpy.triangle as mtri
    except Exception:
        return None

    plane_points: list[tuple[float, float]] = []
    facets: list[tuple[int, int]] = []

    def add_loop(loop: np.ndarray) -> None:
        start = len(plane_points)
        plane_points.extend((float(value[0]), float(value[1])) for value in loop)
        facets.extend(
            (start + index, start + (index + 1) % len(loop))
            for index in range(len(loop))
        )

    add_loop(outer_loop)
    for loop in hole_loops:
        add_loop(loop)

    n_slabs = 4
    target_triangles = max(
        len(plane_points),
        int(target_cells) // max(n_slabs + 2 * max(int(bl_layers), 1), 1),
    )
    domain_area = float(outer_hull.volume) - hole_area
    if domain_area <= 0.0:
        return None
    mesh_info = mtri.MeshInfo()
    mesh_info.set_points(plane_points)
    mesh_info.set_facets(facets)
    mesh_info.set_holes(hole_centres)
    plane_mesh = mtri.build(
        mesh_info,
        max_volume=domain_area / max(target_triangles, 1),
        min_angle=25.0,
        allow_boundary_steiner=True,
    )
    cap_points = np.asarray(plane_mesh.points, dtype=np.float64)
    cap_triangles = np.asarray(plane_mesh.elements, dtype=np.int64)
    if len(cap_points) == 0 or len(cap_triangles) == 0:
        return None

    n_cap_points = len(cap_points)
    layered = np.empty(((n_slabs + 1) * n_cap_points, 3), dtype=np.float64)
    for layer in range(n_slabs + 1):
        block = layered[layer * n_cap_points : (layer + 1) * n_cap_points]
        block[:, uv_axes[0]] = cap_points[:, 0]
        block[:, uv_axes[1]] = cap_points[:, 1]
        block[:, axis] = main_lower[axis] + main_extent[axis] * layer / n_slabs

    cell_faces: list[list[list[int]]] = []
    for layer in range(n_slabs):
        for raw in cap_triangles:
            a, b, c = map(int, raw)
            projected = cap_points[[a, b, c]]
            signed_area = _signed_area_2d(projected)
            if signed_area < 0.0:
                b, c = c, b
            bottom = [layer * n_cap_points + value for value in (a, b, c)]
            top = [(layer + 1) * n_cap_points + value for value in (a, b, c)]
            cell_faces.append(
                [
                    [bottom[2], bottom[1], bottom[0]],
                    [top[0], top[1], top[2]],
                    [bottom[0], bottom[1], top[1], top[0]],
                    [bottom[1], bottom[2], top[2], top[1]],
                    [bottom[2], bottom[0], top[0], top[2]],
                ]
            )

    bottom_offset = 0
    top_offset = n_slabs * n_cap_points
    reference_faces: list[list[int]] = []
    for raw in cap_triangles:
        a, b, c = map(int, raw)
        projected = cap_points[[a, b, c]]
        if _signed_area_2d(projected) < 0.0:
            b, c = c, b
        bottom_face = [bottom_offset + a, bottom_offset + b, bottom_offset + c]
        top_face = [top_offset + a, top_offset + b, top_offset + c]
        outward = np.zeros(3, dtype=np.float64)
        outward[axis] = -1.0
        reference_faces.append(_orient_triangle(layered, bottom_face, outward))
        outward[axis] = 1.0
        reference_faces.append(_orient_triangle(layered, top_face, outward))
    for a, b, opposite in _boundary_edges(cap_triangles):
        first = [int(a), int(b), top_offset + int(b)]
        second = [int(a), top_offset + int(b), top_offset + int(a)]
        side_center = layered[np.asarray(first + second, dtype=np.int64)].mean(axis=0)
        interior_center = (
            layered[
                np.asarray(
                    [int(a), int(b), int(opposite), top_offset + int(a), top_offset + int(b), top_offset + int(opposite)],
                    dtype=np.int64,
                )
            ].mean(axis=0)
        )
        outward = side_center - interior_center
        reference_faces.append(_orient_triangle(layered, first, outward))
        reference_faces.append(_orient_triangle(layered, second, outward))

    reference_vertices = np.vstack(
        (layered[:n_cap_points], layered[top_offset : top_offset + n_cap_points])
    )
    remap = np.asarray(reference_faces, dtype=np.int64)
    remap[remap >= top_offset] -= top_offset - n_cap_points
    return PerforatedExtrusionMesh(
        points=layered,
        cell_faces=cell_faces,
        reference_vertices=reference_vertices,
        reference_faces=remap,
        extrusion_axis=axis,
        n_holes=len(hole_loops),
        n_slabs=n_slabs,
        n_cap_triangles=len(cap_triangles),
    )


__all__ = ["PerforatedExtrusionMesh", "build_perforated_extrusion_wedges"]
