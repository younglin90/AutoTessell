"""Structured wedge rescue for extreme axis-aligned extrusions."""

from __future__ import annotations

from dataclasses import dataclass
import os

import numpy as np
from scipy.spatial import ConvexHull, Delaunay


@dataclass(frozen=True)
class ThinExtrusionMesh:
    points: np.ndarray
    cell_faces: list[list[list[int]]]
    extrusion_axis: int
    n_slabs: int
    n_cap_triangles: int


def _extrusion_axis(
    vertices: np.ndarray,
    faces: np.ndarray,
    *,
    min_bbox_aspect: float,
) -> tuple[int, np.ndarray, np.ndarray] | None:
    extents = np.ptp(vertices, axis=0)
    positive = extents[extents > max(float(np.max(extents)), 1.0) * 1e-12]
    aspect = float(np.max(positive) / np.min(positive)) if positive.size else 1.0

    tolerance = max(float(np.max(extents)), 1.0) * 1e-8
    geometric_mean = float(np.exp(np.mean(np.log(positive))))
    best: tuple[tuple[int, float], int, np.ndarray, np.ndarray] | None = None
    if aspect >= min_bbox_aspect:
        for axis in range(3):
            lower = float(np.min(vertices[:, axis]))
            upper = float(np.max(vertices[:, axis]))
            lower_mask = np.all(
                np.abs(vertices[faces, axis] - lower) <= tolerance, axis=1
            )
            upper_mask = np.all(
                np.abs(vertices[faces, axis] - upper) <= tolerance, axis=1
            )
            if not bool(lower_mask.any()) or not bool(upper_mask.any()):
                continue
            count = int(lower_mask.sum() + upper_mask.sum())
            score = (
                count,
                abs(np.log(max(float(extents[axis]), 1e-300) / geometric_mean)),
            )
            if best is None or score > best[0]:
                best = (score, axis, lower_mask, upper_mask)
    if best is not None:
        return best[1], best[2], best[3]

    if vertices.shape[0] < 4:
        return None
    try:
        _, singular_values, basis = np.linalg.svd(
            vertices - vertices.mean(axis=0),
            full_matrices=False,
        )
    except np.linalg.LinAlgError:
        return None
    if singular_values.shape[0] < 3:
        return None
    normal = np.asarray(basis[-1], dtype=np.float64)
    axis = int(np.argmax(np.abs(normal)))
    alignment = float(abs(normal[axis]))
    if alignment < float(
        os.environ.get("AUTO_TESSELL_THIN_EXTRUSION_PCA_AXIS_ALIGNMENT", "0.98")
    ):
        return None
    if normal[axis] < 0.0:
        normal = -normal
    projection = vertices @ normal
    lower = float(np.min(projection))
    upper = float(np.max(projection))
    thickness = upper - lower
    if thickness <= 0.0:
        return None
    planar = (vertices - vertices.mean(axis=0)) @ basis[:2].T
    planar_extents = np.ptp(planar, axis=0)
    pca_bbox_aspect = float(np.max(planar_extents) / max(thickness, 1e-30))
    if pca_bbox_aspect < min_bbox_aspect:
        return None
    tolerance = max(float(np.max(extents)), 1.0) * float(
        os.environ.get("AUTO_TESSELL_THIN_EXTRUSION_PCA_PLANE_TOL_REL", "1e-6")
    )
    lower_mask = np.all(np.abs(projection[faces] - lower) <= tolerance, axis=1)
    upper_mask = np.all(np.abs(projection[faces] - upper) <= tolerance, axis=1)
    if not bool(lower_mask.any()) or not bool(upper_mask.any()):
        return None
    return axis, lower_mask, upper_mask


def build_thin_extrusion_wedges(
    vertices: np.ndarray,
    faces: np.ndarray,
    *,
    target_cells: int,
    bl_layers: int = 2,
    min_bbox_aspect: float = 100.0,
) -> ThinExtrusionMesh | None:
    """Build quality-stable wedges for a convex extreme extrusion."""
    points = np.asarray(vertices, dtype=np.float64)
    triangles = np.asarray(faces, dtype=np.int64)
    detected = _extrusion_axis(
        points,
        triangles,
        min_bbox_aspect=float(min_bbox_aspect),
    )
    if detected is None:
        return None
    axis, lower_faces, _ = detected
    uv_axes = ((axis + 1) % 3, (axis + 2) % 3)
    lower = float(np.min(points[:, axis]))
    upper = float(np.max(points[:, axis]))
    extent = upper - lower
    transverse_extents = np.ptp(points[:, uv_axes], axis=0)
    if extent <= 0.0 or np.any(transverse_extents <= 0.0):
        return None

    cap_vertex_ids = np.unique(triangles[lower_faces].reshape(-1))
    cap_points = np.unique(points[cap_vertex_ids][:, uv_axes], axis=0)
    if len(cap_points) < 3:
        return None
    hull = ConvexHull(cap_points)
    cap_area = 0.0
    for face in triangles[lower_faces]:
        projected = points[face][:, uv_axes]
        first = projected[1] - projected[0]
        second = projected[2] - projected[0]
        cap_area += 0.5 * abs(
            float(first[0] * second[1] - first[1] * second[0])
        )
    if hull.volume <= 0.0 or abs(cap_area - hull.volume) / hull.volume > 0.02:
        return None

    axial_ratio = extent / float(np.min(transverse_extents))
    layers_added_per_cap = max(1, int(bl_layers))
    cap_triangles: np.ndarray | None = None
    _quality_cap_ratio = float(os.environ.get("AUTO_TESSELL_THIN_QUALITY_CAP_RATIO", "2.5"))
    if axial_ratio <= _quality_cap_ratio:
        # Keep the source boundary loop fixed but avoid raw-Delaunay
        # trailing-edge slivers in the quality candidate.
        n_slabs = 1
        triangle_refinement_factor = float(os.environ.get("AUTO_TESSELL_THIN_TRIANGLE_REFINEMENT_FACTOR", "1.10"))
        target_triangles = max(len(cap_points) - 2, int(round(target_cells / triangle_refinement_factor)))
        try:
            import meshpy.triangle as mtri
            cap_loop = cap_points[hull.vertices]
            mesh_info = mtri.MeshInfo()
            mesh_info.set_points([(float(value[0]), float(value[1])) for value in cap_loop])
            mesh_info.set_facets([(index, (index + 1) % len(cap_loop)) for index in range(len(cap_loop))])
            plane_mesh = mtri.build(
                mesh_info,
                max_volume=float(hull.volume) / max(target_triangles, 1),
                min_angle=25.0,
                allow_boundary_steiner=True,
            )
            cap_points = np.asarray(plane_mesh.points, dtype=np.float64)
            cap_triangles = np.asarray(plane_mesh.elements, dtype=np.int64)
        except Exception:
            cap_triangles = None
    elif axial_ratio <= 0.1:
        n_slabs = 3
        triangle_refinement_factor = float(
            os.environ.get("AUTO_TESSELL_THIN_TRIANGLE_REFINEMENT_FACTOR", "1.10")
        )
        target_triangles = max(
            len(cap_points) - 2,
            int(
                round(
                    target_cells
                    / (
                        triangle_refinement_factor
                        * (n_slabs + 2 * layers_added_per_cap)
                    )
                )
            ),
        )
        try:
            import meshpy.triangle as mtri

            cap_loop = cap_points[hull.vertices]
            mesh_info = mtri.MeshInfo()
            mesh_info.set_points(
                [(float(value[0]), float(value[1])) for value in cap_loop]
            )
            mesh_info.set_facets(
                [
                    (index, (index + 1) % len(cap_loop))
                    for index in range(len(cap_loop))
                ]
            )
            plane_mesh = mtri.build(
                mesh_info,
                max_volume=float(hull.volume) / max(target_triangles, 1),
                min_angle=25.0,
                allow_boundary_steiner=True,
            )
            cap_points = np.asarray(plane_mesh.points, dtype=np.float64)
            cap_triangles = np.asarray(plane_mesh.elements, dtype=np.int64)
        except Exception:
            cap_triangles = None
    else:
        preliminary = Delaunay(cap_points).simplices
        n_cap = max(1, len(preliminary))
        n_slabs = max(
            1,
            int(round(target_cells / n_cap - 2 * layers_added_per_cap)),
        )

    if cap_triangles is None:
        cap_triangles = Delaunay(cap_points).simplices.astype(np.int64, copy=False)
        centres = cap_points[cap_triangles].mean(axis=1)
        inside = np.all(
            centres @ hull.equations[:, :2].T
            + hull.equations[:, 2][None, :]
            <= max(float(np.max(transverse_extents)), 1.0) * 1e-10,
            axis=1,
        )
        cap_triangles = cap_triangles[inside]
    if len(cap_triangles) == 0:
        return None

    n_cap_points = len(cap_points)
    output_points = np.empty(((n_slabs + 1) * n_cap_points, 3), dtype=np.float64)
    for layer in range(n_slabs + 1):
        fraction = layer / n_slabs
        block = output_points[layer * n_cap_points : (layer + 1) * n_cap_points]
        block[:, axis] = lower + extent * fraction
        block[:, uv_axes[0]] = cap_points[:, 0]
        block[:, uv_axes[1]] = cap_points[:, 1]

    cell_faces: list[list[list[int]]] = []
    for layer in range(n_slabs):
        for raw_triangle in cap_triangles:
            a, b, c = map(int, raw_triangle)
            projected = cap_points[[a, b, c]]
            signed_area = (
                (projected[1, 0] - projected[0, 0])
                * (projected[2, 1] - projected[0, 1])
                - (projected[1, 1] - projected[0, 1])
                * (projected[2, 0] - projected[0, 0])
            )
            if signed_area < 0.0:
                b, c = c, b
            bottom = [layer * n_cap_points + index for index in (a, b, c)]
            top = [(layer + 1) * n_cap_points + index for index in (a, b, c)]
            cell_faces.append(
                [
                    [bottom[2], bottom[1], bottom[0]],
                    [top[0], top[1], top[2]],
                    [bottom[0], bottom[1], top[1], top[0]],
                    [bottom[1], bottom[2], top[2], top[1]],
                    [bottom[2], bottom[0], top[0], top[2]],
                ]
            )
    return ThinExtrusionMesh(
        points=output_points,
        cell_faces=cell_faces,
        extrusion_axis=axis,
        n_slabs=n_slabs,
        n_cap_triangles=len(cap_triangles),
    )


__all__ = ["ThinExtrusionMesh", "build_thin_extrusion_wedges"]
