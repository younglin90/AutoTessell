"""Deterministic, read-only localization of triangle-surface defects."""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from typing import cast

import numpy as np
from numpy.typing import NDArray

from core.preprocessor.native_repair.hole_fill import _ear_clip_2d, _loop_plane_basis
from core.preprocessor.native_repair.self_intersect import detect_self_intersections

type DefectRecord = dict[str, object]
type Edge = tuple[int, int]
type DirectedIncidence = tuple[int, int]
type FloatArray = NDArray[np.float64]
type IntArray = NDArray[np.int64]

__all__ = [
    "DefectRecord",
    "apply_surface_defect_repair",
    "detect_surface_defects",
    "localize_surface_defects",
]


def _validated_mesh(
    vertices: NDArray[np.generic], faces: NDArray[np.generic]
) -> tuple[FloatArray, IntArray]:
    vertex_array = cast(FloatArray, np.asarray(vertices, dtype=np.float64))
    face_array = np.asarray(faces)

    if vertex_array.ndim != 2 or vertex_array.shape[1] != 3:
        raise ValueError("vertices must have shape (n, 3)")
    if face_array.ndim != 2 or face_array.shape[1] != 3:
        raise ValueError("faces must have shape (m, 3)")
    if not np.issubdtype(face_array.dtype, np.integer):
        raise TypeError("faces must contain integer vertex indices")
    if not np.isfinite(vertex_array).all():
        raise ValueError("vertices must contain only finite coordinates")

    integer_faces = cast(IntArray, face_array.astype(np.int64, copy=False))
    if integer_faces.size:
        if int(integer_faces.min()) < 0 or int(integer_faces.max()) >= len(vertex_array):
            raise ValueError("faces contain an out-of-range vertex index")
    return vertex_array, integer_faces


def _canonical_edge(first: int, second: int) -> Edge:
    return (first, second) if first < second else (second, first)


def _bounds(vertices: FloatArray, vertex_ids: Sequence[int]) -> dict[str, list[float]]:
    points = vertices[np.asarray(vertex_ids, dtype=np.int64)]
    return {
        "min": [float(value) for value in points.min(axis=0)],
        "max": [float(value) for value in points.max(axis=0)],
    }


def _record(
    *,
    defect_id: str,
    defect_type: str,
    severity: str,
    face_ids: Iterable[int],
    edges: Iterable[Edge],
    vertex_ids: Iterable[int],
    vertices: FloatArray,
    repair_actions: Sequence[str],
) -> DefectRecord:
    sorted_faces = sorted({int(face_id) for face_id in face_ids})
    sorted_edges = sorted({_canonical_edge(int(edge[0]), int(edge[1])) for edge in edges})
    sorted_vertices = sorted({int(vertex_id) for vertex_id in vertex_ids})
    return {
        "defect_id": defect_id,
        "type": defect_type,
        "severity": severity,
        "face_ids": sorted_faces,
        "edge_vertex_ids": [[first, second] for first, second in sorted_edges],
        "vertex_ids": sorted_vertices,
        "bounds": _bounds(vertices, sorted_vertices),
        "repair_actions": list(repair_actions),
    }


def _degenerate_face_ids(
    vertices: FloatArray,
    faces: IntArray,
    area_epsilon: float | None,
) -> list[int]:
    if area_epsilon is not None and (not np.isfinite(area_epsilon) or area_epsilon < 0.0):
        raise ValueError("area_epsilon must be finite and non-negative")
    if len(faces) == 0:
        return []

    extent = np.ptp(vertices, axis=0) if len(vertices) else np.zeros(3, dtype=np.float64)
    scale_squared = float(np.dot(extent, extent))
    automatic_epsilon = max(
        64.0 * np.finfo(np.float64).eps * scale_squared,
        np.finfo(np.float64).tiny,
    )
    threshold = automatic_epsilon if area_epsilon is None else float(area_epsilon)

    triangles = vertices[faces]
    doubled_areas = np.linalg.norm(
        np.cross(triangles[:, 1] - triangles[:, 0], triangles[:, 2] - triangles[:, 0]),
        axis=1,
    )
    repeated_vertex = (
        (faces[:, 0] == faces[:, 1]) | (faces[:, 1] == faces[:, 2]) | (faces[:, 2] == faces[:, 0])
    )
    return [
        int(face_id) for face_id in np.flatnonzero(repeated_vertex | (doubled_areas <= threshold))
    ]


def _face_groups(faces: IntArray) -> dict[tuple[int, int, int], list[int]]:
    groups: dict[tuple[int, int, int], list[int]] = {}
    for face_id, face in enumerate(faces):
        sorted_ids = sorted(int(vertex_id) for vertex_id in face)
        key = (sorted_ids[0], sorted_ids[1], sorted_ids[2])
        groups.setdefault(key, []).append(face_id)
    return groups


def _edge_incidence(
    faces: IntArray,
    degenerate_faces: set[int],
) -> dict[Edge, list[DirectedIncidence]]:
    incidence: dict[Edge, list[DirectedIncidence]] = {}
    for face_id, face in enumerate(faces):
        if face_id in degenerate_faces:
            continue
        for first_raw, second_raw in (
            (face[0], face[1]),
            (face[1], face[2]),
            (face[2], face[0]),
        ):
            first = int(first_raw)
            second = int(second_raw)
            edge = _canonical_edge(first, second)
            direction = 1 if (first, second) == edge else -1
            incidence.setdefault(edge, []).append((face_id, direction))
    return incidence


def _boundary_components(boundary_edges: Sequence[Edge]) -> list[list[Edge]]:
    edges_by_vertex: dict[int, list[Edge]] = {}
    for edge in boundary_edges:
        for vertex_id in edge:
            edges_by_vertex.setdefault(vertex_id, []).append(edge)

    unseen = set(boundary_edges)
    components: list[list[Edge]] = []
    while unseen:
        seed = min(unseen)
        stack = [seed]
        component: list[Edge] = []
        unseen.remove(seed)
        while stack:
            edge = stack.pop()
            component.append(edge)
            neighbors = {
                neighbor
                for vertex_id in edge
                for neighbor in edges_by_vertex[vertex_id]
                if neighbor in unseen
            }
            for neighbor in sorted(neighbors, reverse=True):
                unseen.remove(neighbor)
                stack.append(neighbor)
        components.append(sorted(component))
    return sorted(components, key=lambda component: component[0])


def _is_boundary_loop(edges: Sequence[Edge]) -> bool:
    degrees: dict[int, int] = {}
    for first, second in edges:
        degrees[first] = degrees.get(first, 0) + 1
        degrees[second] = degrees.get(second, 0) + 1
    return len(edges) >= 3 and all(degree == 2 for degree in degrees.values())


def detect_surface_defects(
    vertices: NDArray[np.generic],
    faces: NDArray[np.generic],
    *,
    area_epsilon: float | None = None,
) -> list[DefectRecord]:
    """Locate core defects without changing ``vertices`` or ``faces``.

    Results are JSON-safe dictionaries. Defect ordering and IDs derive only from
    face and vertex IDs, making repeated calls byte-for-byte deterministic after
    JSON serialization with sorted keys.

    ``area_epsilon`` is a threshold for doubled triangle area. The default is a
    scale-aware floating-point tolerance.
    """
    vertex_array, face_array = _validated_mesh(vertices, faces)
    degenerate_ids = _degenerate_face_ids(vertex_array, face_array, area_epsilon)
    degenerate_set = set(degenerate_ids)
    groups = _face_groups(face_array)
    duplicate_groups = sorted(
        ((key, face_ids) for key, face_ids in groups.items() if len(face_ids) > 1),
        key=lambda item: item[1],
    )
    duplicate_keys = {key for key, _ in duplicate_groups}
    incidence = _edge_incidence(face_array, degenerate_set)
    defects: list[DefectRecord] = []

    for face_id in degenerate_ids:
        vertex_ids = sorted({int(vertex_id) for vertex_id in face_array[face_id]})
        defects.append(
            _record(
                defect_id=f"degenerate_face:{face_id}",
                defect_type="degenerate_face",
                severity="error",
                face_ids=[face_id],
                edges=[],
                vertex_ids=vertex_ids,
                vertices=vertex_array,
                repair_actions=["remove_face"],
            )
        )

    for key, face_ids in duplicate_groups:
        identity = "-".join(str(face_id) for face_id in face_ids)
        defects.append(
            _record(
                defect_id=f"duplicate_faces:{identity}",
                defect_type="duplicate_faces",
                severity="warning",
                face_ids=face_ids,
                edges=[],
                vertex_ids=key,
                vertices=vertex_array,
                repair_actions=["remove_duplicate_faces"],
            )
        )

    boundary_edges = sorted(edge for edge, incident in incidence.items() if len(incident) == 1)
    for component in _boundary_components(boundary_edges):
        loop = _is_boundary_loop(component)
        defect_type = "boundary_loop" if loop else "boundary_component"
        first_edge = component[0]
        face_ids = [incidence[edge][0][0] for edge in component]
        vertex_ids = [vertex_id for edge in component for vertex_id in edge]
        defects.append(
            _record(
                defect_id=f"{defect_type}:{first_edge[0]}-{first_edge[1]}",
                defect_type=defect_type,
                severity="error",
                face_ids=face_ids,
                edges=component,
                vertex_ids=vertex_ids,
                vertices=vertex_array,
                repair_actions=["fill_hole"] if loop else [],
            )
        )

    for edge, incident in sorted(incidence.items()):
        if len(incident) <= 2:
            continue
        face_ids = [face_id for face_id, _ in incident]
        defects.append(
            _record(
                defect_id=f"non_manifold_edge:{edge[0]}-{edge[1]}",
                defect_type="non_manifold_edge",
                severity="error",
                face_ids=face_ids,
                edges=[edge],
                vertex_ids=edge,
                vertices=vertex_array,
                repair_actions=["split_non_manifold_edge", "remove_incident_faces"],
            )
        )

    for edge, incident in sorted(incidence.items()):
        if len(incident) != 2 or incident[0][1] != incident[1][1]:
            continue
        first_face, second_face = incident[0][0], incident[1][0]
        if tuple(sorted(int(vertex_id) for vertex_id in face_array[first_face])) in duplicate_keys:
            continue
        defects.append(
            _record(
                defect_id=f"inconsistent_winding:{edge[0]}-{edge[1]}",
                defect_type="inconsistent_winding",
                severity="warning",
                face_ids=[first_face, second_face],
                edges=[edge],
                vertex_ids=edge,
                vertices=vertex_array,
                repair_actions=["flip_face_winding"],
            )
        )

    self_intersection_report = detect_self_intersections(vertex_array, face_array)
    pairs = sorted(
        {
            (min(int(first), int(second)), max(int(first), int(second)))
            for first, second in self_intersection_report.intersecting_face_pairs
        }
    )
    for first_face, second_face in pairs:
        vertex_ids = sorted(
            {
                int(vertex_id)
                for face_id in (first_face, second_face)
                for vertex_id in face_array[face_id]
            }
        )
        defects.append(
            _record(
                defect_id=f"self_intersection:{first_face}-{second_face}",
                defect_type="self_intersection",
                severity="error",
                face_ids=[first_face, second_face],
                edges=[],
                vertex_ids=vertex_ids,
                vertices=vertex_array,
                repair_actions=["resolve_self_intersection"],
            )
        )

    return defects


localize_surface_defects = detect_surface_defects


def _remove_faces(faces: IntArray, face_ids: Sequence[int]) -> IntArray:
    keep = np.ones(len(faces), dtype=bool)
    keep[np.asarray(face_ids, dtype=np.int64)] = False
    return faces[keep].copy()


def _ordered_boundary_loop(raw_edges: object) -> list[int]:
    edges = [(int(edge[0]), int(edge[1])) for edge in cast(Sequence[Sequence[int]], raw_edges)]
    adjacency: dict[int, list[int]] = {}
    for first, second in edges:
        adjacency.setdefault(first, []).append(second)
        adjacency.setdefault(second, []).append(first)
    if len(edges) < 3 or any(len(neighbors) != 2 for neighbors in adjacency.values()):
        raise ValueError("selected boundary is not a closed loop")

    start = min(adjacency)
    loop = [start]
    previous = -1
    current = start
    while True:
        candidates = sorted(vertex for vertex in adjacency[current] if vertex != previous)
        if not candidates:
            raise ValueError("selected boundary loop is disconnected")
        following = candidates[0]
        if following == start:
            break
        if following in loop or len(loop) > len(edges):
            raise ValueError("selected boundary loop is branched")
        loop.append(following)
        previous, current = current, following
    if len(loop) != len(edges):
        raise ValueError("selected boundary loop is incomplete")
    return loop


def _fill_selected_boundary(
    vertices: FloatArray,
    faces: IntArray,
    raw_edges: object,
) -> IntArray:
    loop = _ordered_boundary_loop(raw_edges)
    centroid, first_axis, second_axis = _loop_plane_basis(vertices, loop)
    relative = vertices[loop] - centroid
    projected = np.stack([relative @ first_axis, relative @ second_axis], axis=1)
    local_triangles = _ear_clip_2d(projected)
    if not local_triangles:
        raise ValueError("selected boundary loop cannot be triangulated")

    directed_edges = {
        (int(first), int(second))
        for face in faces
        for first, second in (
            (face[0], face[1]),
            (face[1], face[2]),
            (face[2], face[0]),
        )
    }
    first_local = local_triangles[0]
    first_triangle = tuple(loop[index] for index in first_local)
    flip = any(
        (first, second) in directed_edges
        for first, second in (
            (first_triangle[0], first_triangle[1]),
            (first_triangle[1], first_triangle[2]),
            (first_triangle[2], first_triangle[0]),
        )
    )
    added = []
    for local in local_triangles:
        triangle = [loop[local[0]], loop[local[1]], loop[local[2]]]
        if flip:
            triangle[1], triangle[2] = triangle[2], triangle[1]
        added.append(triangle)
    return cast(IntArray, np.vstack([faces, np.asarray(added, dtype=np.int64)]))


def apply_surface_defect_repair(
    vertices: NDArray[np.generic],
    faces: NDArray[np.generic],
    defect_id: str,
    action: str,
) -> tuple[FloatArray, IntArray]:
    """Apply one repair to one current defect; never mutate input arrays."""
    vertex_array, face_array = _validated_mesh(vertices, faces)
    defect = next(
        (
            item
            for item in detect_surface_defects(vertex_array, face_array)
            if item["defect_id"] == defect_id
        ),
        None,
    )
    if defect is None:
        raise ValueError(f"defect not found: {defect_id}")
    actions = cast(Sequence[str], defect["repair_actions"])
    if action not in actions:
        raise ValueError(f"repair action not available for {defect_id}: {action}")

    output_vertices = vertex_array.copy()
    output_faces = face_array.copy()
    face_ids = cast(Sequence[int], defect["face_ids"])

    if action == "remove_face":
        output_faces = _remove_faces(output_faces, face_ids)
    elif action == "remove_duplicate_faces":
        output_faces = _remove_faces(output_faces, face_ids[1:])
    elif action == "fill_hole":
        output_faces = _fill_selected_boundary(
            output_vertices, output_faces, defect["edge_vertex_ids"]
        )
    elif action == "flip_face_winding":
        face_id = int(face_ids[-1])
        output_faces[face_id, [1, 2]] = output_faces[face_id, [2, 1]]
    elif action == "remove_incident_faces":
        output_faces = _remove_faces(output_faces, face_ids[2:])
    elif action == "split_non_manifold_edge":
        edge = cast(Sequence[Sequence[int]], defect["edge_vertex_ids"])[0]
        first, second = int(edge[0]), int(edge[1])
        for face_id in face_ids[2:]:
            replacements: dict[int, int] = {}
            for vertex_id in (first, second):
                replacements[vertex_id] = len(output_vertices)
                output_vertices = cast(
                    FloatArray,
                    np.vstack([output_vertices, output_vertices[vertex_id]]),
                )
            for corner, vertex_id in enumerate(output_faces[int(face_id)]):
                replacement = replacements.get(int(vertex_id))
                if replacement is not None:
                    output_faces[int(face_id), corner] = replacement
    elif action == "resolve_self_intersection":
        output_faces = _remove_faces(output_faces, [face_ids[-1]])
    else:
        raise ValueError(f"unsupported repair action: {action}")

    return output_vertices, output_faces
