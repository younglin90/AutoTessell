"""Target-sized wedge mesh for a single convex constant-section extrusion."""

from __future__ import annotations

from dataclasses import dataclass
import os

import numpy as np
from scipy.spatial import ConvexHull

from core.generator.native_tet.perforated_extrusion import _signed_area_2d
from core.generator.native_tet.torus_wedge import _edge_components


@dataclass(frozen=True)
class ConvexExtrusionMesh:
    points: np.ndarray
    cell_faces: list[list[list[int]]]
    tets: np.ndarray
    extrusion_axis: int
    n_slabs: int
    n_cap_triangles: int
    tiny_hole_profile: bool = False


def _prism_to_tets(
    bottom: list[int],
    top: list[int],
) -> tuple[tuple[int, int, int, int], ...]:
    """Split one prism into three conforming tetrahedra.

    The global-minimum rule makes every shared quad choose the same diagonal.
    It is the Dompierre prism split used by the tet boundary-layer converter.
    """
    vertices = bottom + top
    minimum = min(range(6), key=vertices.__getitem__)
    if minimum < 3:
        start, lower, upper = minimum, bottom, top
    else:
        start, lower, upper = minimum - 3, top, bottom
    i1, i2 = (start + 1) % 3, (start + 2) % 3
    v0, v1, v2 = lower[start], lower[i1], lower[i2]
    v3, v4, v5 = upper[start], upper[i1], upper[i2]
    if min(v1, v5) < min(v2, v4):
        return ((v0, v3, v4, v5), (v0, v1, v2, v5), (v0, v1, v4, v5))
    return ((v0, v3, v4, v5), (v0, v1, v2, v4), (v0, v2, v4, v5))


def _tet_faces(tet: tuple[int, int, int, int]) -> list[list[int]]:
    a, b, c, d = tet
    return [[b, c, d], [a, d, c], [a, b, d], [a, c, b]]


def _polygon_area_2d(points: np.ndarray) -> float:
    if len(points) < 3:
        return 0.0
    shifted = np.roll(points, -1, axis=0)
    return 0.5 * float(
        np.sum(points[:, 0] * shifted[:, 1] - shifted[:, 0] * points[:, 1])
    )


def _cap_boundary_loops(
    points: np.ndarray,
    cap_triangles: np.ndarray,
    uv_axes: tuple[int, int],
) -> list[np.ndarray]:
    """Return ordered boundary loops from a cap triangulation."""
    edge_counts: dict[tuple[int, int], int] = {}
    for raw in np.asarray(cap_triangles, dtype=np.int64):
        a, b, c = map(int, raw)
        for first, second in ((a, b), (b, c), (c, a)):
            edge = (first, second) if first < second else (second, first)
            edge_counts[edge] = edge_counts.get(edge, 0) + 1
    remaining = {edge for edge, count in edge_counts.items() if count == 1}
    loops: list[np.ndarray] = []
    while remaining:
        start_edge = next(iter(remaining))
        remaining.remove(start_edge)
        start, current = start_edge
        loop = [start, current]
        while current != start:
            next_edge = None
            for edge in list(remaining):
                if current in edge:
                    next_edge = edge
                    break
            if next_edge is None:
                break
            remaining.remove(next_edge)
            current = next_edge[1] if next_edge[0] == current else next_edge[0]
            if current != start:
                loop.append(current)
            if len(loop) > len(edge_counts) + 1:
                break
        if len(loop) >= 3 and current == start:
            projected = points[np.asarray(loop, dtype=np.int64)][:, uv_axes]
            if abs(_polygon_area_2d(projected)) > 1e-30:
                loops.append(projected)
    return loops


def _resample_loop(loop: np.ndarray, max_vertices: int) -> np.ndarray:
    """Uniformly decimate an ordered loop while preserving closure semantics."""
    if len(loop) <= max_vertices:
        return loop
    count = max(3, int(max_vertices))
    ids = np.linspace(0, len(loop), count, endpoint=False, dtype=np.int64)
    return loop[ids]


def build_convex_extrusion_wedges(
    vertices: np.ndarray,
    faces: np.ndarray,
    *,
    target_cells: int,
    bl_layers: int = 3,
    allow_sharp_profile: bool = False,
    prefer_quality_slabs: bool = False,
) -> ConvexExtrusionMesh | None:
    """Build balanced wedges when input is one convex axis extrusion."""
    points = np.asarray(vertices, dtype=np.float64)
    triangles = np.asarray(faces, dtype=np.int64)
    if len(_edge_components(triangles)) != 1 or len(points) < 4:
        return None
    extents = np.ptp(points, axis=0)
    tolerance = max(float(np.max(extents)), 1.0) * float(
        os.environ.get("AUTO_TESSELL_CONVEX_EXTRUSION_CAP_TOL_REL", "1e-6")
    )
    cap_masks: list[tuple[np.ndarray, np.ndarray]] = []
    cap_counts: list[int] = []
    for axis in range(3):
        lower = float(points[:, axis].min())
        upper = float(points[:, axis].max())
        lower_mask = np.all(np.abs(points[triangles, axis] - lower) <= tolerance, axis=1)
        upper_mask = np.all(np.abs(points[triangles, axis] - upper) <= tolerance, axis=1)
        cap_masks.append((lower_mask, upper_mask))
        cap_counts.append(int(lower_mask.sum() + upper_mask.sum()))
    axis = int(np.argmax(cap_counts))
    lower_mask, upper_mask = cap_masks[axis]
    if not bool(lower_mask.any()) or not bool(upper_mask.any()):
        return None

    try:
        hull_3d = ConvexHull(points)
    except Exception:
        return None
    input_area = 0.5 * float(
        np.linalg.norm(
            np.cross(
                points[triangles[:, 1]] - points[triangles[:, 0]],
                points[triangles[:, 2]] - points[triangles[:, 0]],
            ),
            axis=1,
        ).sum()
    )
    compact_cap_fraction = float(cap_counts[axis]) / max(float(len(triangles)), 1.0)
    bbox_positive = extents[extents > max(float(np.max(extents)), 1.0) * 1e-12]
    bbox_aspect = (
        float(np.max(bbox_positive) / np.min(bbox_positive))
        if bbox_positive.size
        else 1.0
    )
    area_tolerance = 0.02
    if compact_cap_fraction >= 0.15:
        area_tolerance = float(
            os.environ.get("AUTO_TESSELL_CONVEX_ANNULAR_AREA_TOL", "0.50")
        )
    if compact_cap_fraction >= 0.4 and bbox_aspect <= 1.5:
        area_tolerance = float(
            os.environ.get("AUTO_TESSELL_CONVEX_COMPACT_AREA_TOL", "0.20")
        )
    if abs(float(hull_3d.area) - input_area) / max(input_area, 1e-30) > area_tolerance:
        return None

    uv_axes = tuple(index for index in range(3) if index != axis)
    cap_vertex_ids = np.unique(triangles[lower_mask].reshape(-1))
    cap_cloud = np.unique(points[cap_vertex_ids][:, uv_axes], axis=0)
    if len(cap_cloud) < 3:
        return None
    cap_hull = ConvexHull(cap_cloud)
    cap_loop = cap_cloud[cap_hull.vertices]
    transverse_extents = np.ptp(cap_loop, axis=0)
    transverse_aspect = float(
        np.max(transverse_extents) / max(float(np.min(transverse_extents)), 1e-30)
    )
    cap_edges = np.linalg.norm(
        cap_loop - np.roll(cap_loop, -1, axis=0), axis=1
    )
    # A cusp needs a constrained general tetrahedralizer.  Splitting its tiny
    # structured prisms into tets creates near-90 degree internal faces even
    # though the exterior is valid.  Keep the fast extrusion route for smooth
    # elongated sections, but hand sharp trailing edges to the P4C path.
    sharp_edge_ratio = float(
        cap_edges.min() / max(float(np.max(transverse_extents)), 1e-30)
    )
    sharp_edge_ratio_min = float(
        os.environ.get("AUTO_TESSELL_CONVEX_SHARP_EDGE_RATIO_MIN", "0.01")
    )
    if sharp_edge_ratio < sharp_edge_ratio_min and not bool(allow_sharp_profile):
        return None
    profile_aspect_limit = float(
        os.environ.get(
            "AUTO_TESSELL_CONVEX_PROFILE_MAX_ASPECT",
            "1000.0" if allow_sharp_profile else "20.0",
        )
    )
    if len(cap_loop) > 8 and transverse_aspect > profile_aspect_limit:
        return None
    predicted_volume = float(cap_hull.volume) * float(extents[axis])
    if abs(predicted_volume - float(hull_3d.volume)) / max(float(hull_3d.volume), 1e-30) > 0.02:
        return None

    compact_smooth_quality_profile = bool(
        compact_cap_fraction >= float(
            os.environ.get(
                "AUTO_TESSELL_CONVEX_SMOOTH_LOOP_MIN_CAP_FRACTION",
                "0.40",
            )
        )
        and len(cap_loop)
        >= int(
            os.environ.get(
                "AUTO_TESSELL_CONVEX_SMOOTH_LOOP_MIN_VERTS",
                "64",
            )
        )
        and transverse_aspect
        <= float(
            os.environ.get(
                "AUTO_TESSELL_CONVEX_SMOOTH_LOOP_MAX_TRANSVERSE_ASPECT",
                "1.50",
            )
        )
        and bbox_aspect
        <= float(
            os.environ.get(
                "AUTO_TESSELL_CONVEX_SMOOTH_LOOP_MAX_BBOX_ASPECT",
                "5.0",
            )
        )
    )
    smooth_loop_max_vertices = int(
        os.environ.get(
            "AUTO_TESSELL_CONVEX_SMOOTH_LOOP_MAX_VERTS",
            "48" if compact_smooth_quality_profile else "0",
        )
    )
    if smooth_loop_max_vertices >= 3 and len(cap_loop) > smooth_loop_max_vertices:
        cap_loop = _resample_loop(cap_loop, smooth_loop_max_vertices)

    try:
        import meshpy.triangle as mtri
    except Exception:
        return None
    cap_loops = _cap_boundary_loops(points, triangles[lower_mask], uv_axes)
    section_area = float(cap_hull.volume)
    plane_points: list[tuple[float, float]] = []
    facets: list[tuple[int, int]] = []
    hole_points: list[tuple[float, float]] = []
    outer_area = 0.0
    hole_area = 0.0
    if len(cap_loops) > 1:
        cap_loops = sorted(
            cap_loops,
            key=lambda loop: abs(_polygon_area_2d(loop)),
            reverse=True,
        )
        loop_budget = max(12.0, float(target_cells) ** 0.5)
        outer_loop = _resample_loop(
            cap_loops[0],
            int(
                os.environ.get(
                    "AUTO_TESSELL_CONVEX_HOLE_OUTER_LOOP_VERTS",
                    str(max(24, int(loop_budget * 0.55))),
                )
            ),
        )
        outer_area = abs(_polygon_area_2d(outer_loop))
        hole_area = 0.0

        def add_loop(loop: np.ndarray) -> None:
            start = len(plane_points)
            plane_points.extend((float(value[0]), float(value[1])) for value in loop)
            facets.extend(
                (start + index, start + (index + 1) % len(loop))
                for index in range(len(loop))
            )

        add_loop(outer_loop)
        for loop in cap_loops[1:]:
            loop = _resample_loop(
                loop,
                int(
                    os.environ.get(
                        "AUTO_TESSELL_CONVEX_HOLE_INNER_LOOP_VERTS",
                        str(max(12, int(loop_budget * 0.35))),
                    )
                ),
            )
            local_area = abs(_polygon_area_2d(loop))
            if local_area <= outer_area * 1e-6:
                continue
            centre = loop.mean(axis=0)
            signed = centre @ cap_hull.equations[:, :2].T + cap_hull.equations[:, 2]
            if np.any(signed >= -tolerance):
                continue
            add_loop(loop)
            hole_points.append((float(centre[0]), float(centre[1])))
            hole_area += local_area
        if hole_points:
            section_area = outer_area - hole_area
        else:
            plane_points = []
            facets = []
    if not plane_points:
        plane_points = [(float(value[0]), float(value[1])) for value in cap_loop]
        facets = [
            (index, (index + 1) % len(cap_loop))
            for index in range(len(cap_loop))
        ]

    mesh_info = mtri.MeshInfo()
    mesh_info.set_points(plane_points)
    mesh_info.set_facets(facets)
    tiny_hole_bracket_profile = False
    if hole_points:
        mesh_info.set_holes(hole_points)
    # Thin airfoil-like sections need denser cap triangles to keep BL wedges
    # above the normalized determinant gate.
    triangle_refinement_factor = 1.1 if transverse_aspect > 4.0 else 1.5
    # A fixed number of slabs makes the tetrahedra progressively more elongated
    # as the requested cell count grows.  Balance the axial slab height against
    # the characteristic cap-triangle length instead.  With n cap triangles,
    # h_cap ~= sqrt(A / n) and n ~= target / (factor * 3 * slabs), so the
    # isotropic condition h_axis / slabs ~= h_cap gives this cube-root rule.
    # Keep the established coarse floor and a bounded cost ceiling.
    if section_area <= 0.0:
        return None
    cap_scale = np.sqrt(max(section_area, 1e-30))
    isotropic_slabs = (
        float(extents[axis])
        / cap_scale
        * (float(target_cells) / (triangle_refinement_factor * 3.0)) ** (1.0 / 3.0)
    )
    tiny_hole_bracket_profile = False
    high_aspect_small_hole_profile = False
    if hole_points:
        hole_area_fraction = hole_area / max(outer_area, 1e-30)
        tiny_hole_bracket_profile = bool(
            len(cap_loop)
            <= int(os.environ.get("AUTO_TESSELL_CONVEX_BRACKET_MAX_CAP_VERTS", "8"))
            and len(hole_points)
            >= int(os.environ.get("AUTO_TESSELL_CONVEX_BRACKET_MIN_HOLES", "2"))
            and hole_area_fraction
            <= float(
                os.environ.get(
                    "AUTO_TESSELL_CONVEX_BRACKET_MAX_HOLE_FRACTION",
                    "0.05",
                )
            )
            and bbox_aspect
            <= float(
                os.environ.get(
                    "AUTO_TESSELL_CONVEX_BRACKET_MAX_BBOX_ASPECT",
                    "3.0",
                )
            )
        )
        high_aspect_small_hole_profile = bool(
            len(cap_loop)
            >= int(
                os.environ.get(
                    "AUTO_TESSELL_CONVEX_HIGH_ASPECT_HOLE_MIN_CAP_VERTS",
                    "24",
                )
            )
            and hole_area_fraction
            <= float(
                os.environ.get(
                    "AUTO_TESSELL_CONVEX_HIGH_ASPECT_HOLE_MAX_FRACTION",
                    "0.15",
                )
            )
            and bbox_aspect
            >= float(
                os.environ.get(
                    "AUTO_TESSELL_CONVEX_HIGH_ASPECT_HOLE_MIN_BBOX_ASPECT",
                    "6.0",
                )
            )
        )
        long_axis_extrusion = bool(
            float(extents[axis]) >= 0.5 * max(float(np.max(extents)), 1e-30)
            and bbox_aspect <= 20.0
        )
        quality_slabs_min_aspect = float(
            os.environ.get(
                "AUTO_TESSELL_CONVEX_HOLE_QUALITY_SLABS_MIN_ASPECT",
                "2.5",
            )
        )
        quality_slabs = bool(
            long_axis_extrusion
            and (prefer_quality_slabs or bbox_aspect >= quality_slabs_min_aspect)
        )
        min_slabs_default = (
            "18"
            if tiny_hole_bracket_profile
            else ("16" if quality_slabs else ("10" if long_axis_extrusion else "4"))
        )
        max_slabs_default = (
            "18"
            if tiny_hole_bracket_profile
            else ("16" if quality_slabs else ("12" if long_axis_extrusion else "6"))
        )
        min_slabs = int(
            os.environ.get("AUTO_TESSELL_CONVEX_HOLE_MIN_SLABS", min_slabs_default)
        )
        max_slabs = max(
            min_slabs,
            int(
                os.environ.get(
                    "AUTO_TESSELL_CONVEX_HOLE_MAX_SLABS",
                    max_slabs_default,
                )
            ),
        )
        n_slabs = int(
            np.clip(
                np.rint(isotropic_slabs),
                min_slabs,
                max_slabs,
            )
        )
    else:
        elongated_profile = bool(transverse_aspect > 3.0 and bbox_aspect <= 10.0)
        min_slabs = int(
            os.environ.get(
                "AUTO_TESSELL_CONVEX_MIN_SLABS",
                (
                    "20"
                    if compact_smooth_quality_profile
                    else ("6" if elongated_profile else "4")
                ),
            )
        )
        max_slabs = max(
            min_slabs,
            int(
                os.environ.get(
                    "AUTO_TESSELL_CONVEX_MAX_SLABS",
                    "20" if compact_smooth_quality_profile else "12",
                )
            ),
        )
        n_slabs = int(
            np.clip(
                np.rint(isotropic_slabs),
                min_slabs,
                max_slabs,
            )
        )
    # A prism used to count as one bulk cell.  native_tet must emit three
    # tetrahedra per prism, so account for that before sizing the cap mesh.
    # The later optional BL stack contributes two cells per cap triangle/layer.
    budget_bl_layers = int(
        os.environ.get(
            "AUTO_TESSELL_CONVEX_BUDGET_BL_LAYERS",
            (
                "1"
                if high_aspect_small_hole_profile
                else str(max(int(bl_layers), 0))
            ),
        )
    )
    cells_per_cap_triangle = 3 * n_slabs + 2 * max(budget_bl_layers, 0)
    target_triangles = max(
        len(cap_loop) - 2,
        int(
            int(target_cells)
            / (
                triangle_refinement_factor * max(cells_per_cap_triangle, 1)
            )
        ),
    )
    plane_mesh = mtri.build(
        mesh_info,
        max_volume=section_area / max(target_triangles, 1),
        min_angle=float(
            os.environ.get(
                "AUTO_TESSELL_CONVEX_TRIANGLE_MIN_ANGLE",
                "30.0" if hole_points and tiny_hole_bracket_profile else "25.0",
            )
        ),
        allow_boundary_steiner=True,
    )
    cap_points = np.asarray(plane_mesh.points, dtype=np.float64)
    cap_triangles = np.asarray(plane_mesh.elements, dtype=np.int64)
    if len(cap_points) == 0 or len(cap_triangles) == 0:
        return None

    n_cap_points = len(cap_points)
    output_points = np.empty(((n_slabs + 1) * n_cap_points, 3), dtype=np.float64)
    lower = float(points[:, axis].min())
    for layer in range(n_slabs + 1):
        block = output_points[layer * n_cap_points : (layer + 1) * n_cap_points]
        block[:, uv_axes[0]] = cap_points[:, 0]
        block[:, uv_axes[1]] = cap_points[:, 1]
        block[:, axis] = lower + float(extents[axis]) * layer / n_slabs

    tets: list[tuple[int, int, int, int]] = []
    for layer in range(n_slabs):
        for raw in cap_triangles:
            a, b, c = map(int, raw)
            if _signed_area_2d(cap_points[[a, b, c]]) < 0.0:
                b, c = c, b
            bottom = [layer * n_cap_points + value for value in (a, b, c)]
            top = [(layer + 1) * n_cap_points + value for value in (a, b, c)]
            tets.extend(_prism_to_tets(bottom, top))
    tet_array = np.asarray(tets, dtype=np.int64)
    return ConvexExtrusionMesh(
        points=output_points,
        cell_faces=[_tet_faces(tet) for tet in tets],
        tets=tet_array,
        extrusion_axis=axis,
        n_slabs=n_slabs,
        n_cap_triangles=len(cap_triangles),
        tiny_hole_profile=bool(tiny_hole_bracket_profile),
    )


__all__ = ["ConvexExtrusionMesh", "build_convex_extrusion_wedges"]
