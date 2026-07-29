"""Structured wedge rescue for circular torus surface components."""

from __future__ import annotations

from collections import defaultdict, deque
from dataclasses import dataclass

import numpy as np


@dataclass(frozen=True)
class TorusWedgeMesh:
    points: np.ndarray
    cell_faces: list[list[list[int]]]
    n_components: int
    major_segments: int
    minor_segments: int


def _edge_components(faces: np.ndarray) -> list[np.ndarray]:
    edge_faces: defaultdict[tuple[int, int], list[int]] = defaultdict(list)
    for face_index, face in enumerate(faces):
        a, b, c = map(int, face)
        for left, right in ((a, b), (b, c), (c, a)):
            edge_faces[(min(left, right), max(left, right))].append(face_index)
    adjacency: list[set[int]] = [set() for _ in range(len(faces))]
    for attached in edge_faces.values():
        for face_index in attached:
            adjacency[face_index].update(attached)
    components: list[np.ndarray] = []
    visited: set[int] = set()
    for start in range(len(faces)):
        if start in visited:
            continue
        queue: deque[int] = deque([start])
        visited.add(start)
        component: list[int] = []
        while queue:
            current = queue.popleft()
            component.append(current)
            for neighbor in adjacency[current]:
                if neighbor not in visited:
                    visited.add(neighbor)
                    queue.append(neighbor)
        components.append(np.asarray(component, dtype=np.int64))
    return components


def _torus_parameters(points: np.ndarray) -> tuple[np.ndarray, int, float, float] | None:
    lower = points.min(axis=0)
    upper = points.max(axis=0)
    extents = upper - lower
    axis = int(np.argmin(extents))
    plane_axes = [index for index in range(3) if index != axis]
    large = extents[plane_axes]
    if np.min(large) <= 0.0 or abs(float(large[0] - large[1])) / float(np.max(large)) > 0.03:
        return None
    minor_radius = float(extents[axis] * 0.5)
    major_radius = float(np.mean(large) * 0.5 - minor_radius)
    if minor_radius <= 0.0 or major_radius < 2.0 * minor_radius:
        return None
    center = 0.5 * (lower + upper)
    relative = points - center
    radial = np.linalg.norm(relative[:, plane_axes], axis=1)
    tube_radius = np.sqrt((radial - major_radius) ** 2 + relative[:, axis] ** 2)
    residual = float(np.max(np.abs(tube_radius - minor_radius))) / minor_radius
    if residual > 0.03:
        return None
    return center, axis, major_radius, minor_radius


def _orient_faces(points: np.ndarray, vertex_ids: list[int]) -> list[list[int]]:
    bottom = vertex_ids[:3]
    top = vertex_ids[3:]
    raw_faces = [
        [bottom[0], bottom[1], bottom[2]],
        [top[0], top[2], top[1]],
        [bottom[0], top[0], top[1], bottom[1]],
        [bottom[1], top[1], top[2], bottom[2]],
        [bottom[2], top[2], top[0], bottom[0]],
    ]
    cell_center = points[np.asarray(vertex_ids, dtype=np.int64)].mean(axis=0)
    output: list[list[int]] = []
    for face in raw_faces:
        polygon = points[np.asarray(face, dtype=np.int64)]
        normal = np.zeros(3, dtype=np.float64)
        for index in range(1, len(polygon) - 1):
            normal += np.cross(
                polygon[index] - polygon[0],
                polygon[index + 1] - polygon[0],
            )
        if float(np.dot(normal, polygon.mean(axis=0) - cell_center)) < 0.0:
            face = list(reversed(face))
        output.append(face)
    return output


def build_torus_wedges(
    vertices: np.ndarray,
    faces: np.ndarray,
    *,
    major_segments: int = 24,
    minor_segments: int = 16,
) -> TorusWedgeMesh | None:
    """Recognize edge-connected circular tori and sweep disk wedges."""
    surface_points = np.asarray(vertices, dtype=np.float64)
    surface_faces = np.asarray(faces, dtype=np.int64)
    components = _edge_components(surface_faces)
    parameters: list[tuple[np.ndarray, int, float, float]] = []
    for component in components:
        vertex_ids = np.unique(surface_faces[component].reshape(-1))
        parameter = _torus_parameters(surface_points[vertex_ids])
        if parameter is None:
            return None
        parameters.append(parameter)
    if not parameters:
        return None

    adjusted = [
        [center.copy(), axis, major_radius, minor_radius]
        for center, axis, major_radius, minor_radius in parameters
    ]
    for left in range(len(adjusted)):
        for right in range(left + 1, len(adjusted)):
            delta = adjusted[right][0] - adjusted[left][0]
            distance = float(np.linalg.norm(delta))
            contact_distance = float(
                adjusted[left][2]
                + adjusted[left][3]
                + adjusted[right][2]
                + adjusted[right][3]
            )
            if distance <= 0.0 or abs(distance - contact_distance) > 1e-5 * max(
                contact_distance, 1.0
            ):
                continue
            direction = delta / distance
            gap = 1e-6 * max(contact_distance, 1.0)
            adjusted[left][0] -= 0.5 * gap * direction
            adjusted[right][0] += 0.5 * gap * direction
    parameters = [
        (center, int(axis), float(major_radius), float(minor_radius))
        for center, axis, major_radius, minor_radius in adjusted
    ]

    n_major = max(8, int(major_segments))
    n_minor = max(8, int(minor_segments))
    generated_points: list[list[float]] = []
    cell_vertex_ids: list[list[int]] = []
    for center, axis, major_radius, minor_radius in parameters:
        plane_axes = [index for index in range(3) if index != axis]
        component_start = len(generated_points)
        for major_index in range(n_major):
            theta = 2.0 * np.pi * major_index / n_major
            radial_direction = np.zeros(3, dtype=np.float64)
            radial_direction[plane_axes[0]] = np.cos(theta)
            radial_direction[plane_axes[1]] = np.sin(theta)
            generated_points.append(
                (center + major_radius * radial_direction).tolist()
            )
            for minor_index in range(n_minor):
                phi = 2.0 * np.pi * minor_index / n_minor
                point = (
                    center
                    + (major_radius + minor_radius * np.cos(phi))
                    * radial_direction
                )
                point = point.copy()
                point[axis] += minor_radius * np.sin(phi)
                generated_points.append(point.tolist())
        stride = n_minor + 1
        for major_index in range(n_major):
            next_major = (major_index + 1) % n_major
            for minor_index in range(n_minor):
                next_minor = (minor_index + 1) % n_minor
                cell_vertex_ids.append(
                    [
                        component_start + major_index * stride,
                        component_start + major_index * stride + 1 + minor_index,
                        component_start + major_index * stride + 1 + next_minor,
                        component_start + next_major * stride,
                        component_start + next_major * stride + 1 + minor_index,
                        component_start + next_major * stride + 1 + next_minor,
                    ]
                )

    output_points = np.asarray(generated_points, dtype=np.float64)
    cell_faces = [
        _orient_faces(output_points, vertex_ids) for vertex_ids in cell_vertex_ids
    ]
    return TorusWedgeMesh(
        points=output_points,
        cell_faces=cell_faces,
        n_components=len(parameters),
        major_segments=n_major,
        minor_segments=n_minor,
    )


__all__ = ["TorusWedgeMesh", "build_torus_wedges"]
