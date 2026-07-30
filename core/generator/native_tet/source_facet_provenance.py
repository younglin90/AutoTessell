"""Independent Python oracle for exact planar-patch facet provenance."""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass

import numpy as np

_EPS = float(np.finfo(np.float64).eps)
_DISTANCE_TOLERANCE = 256.0 * _EPS
_NORMAL_TOLERANCE = 1024.0 * _EPS
_AREA_TOLERANCE_FACTOR = 8192.0 * _EPS


@dataclass(frozen=True)
class _Patch:
    faces: tuple[int, ...]
    normal: np.ndarray
    offset: float
    axis: int
    triangles: np.ndarray
    boundary_edges: tuple[tuple[int, int], ...]


def _normalized_points(
    source_points: np.ndarray, candidate_points: np.ndarray
) -> tuple[np.ndarray, np.ndarray]:
    maximum = float(np.max(np.abs(source_points)))
    if maximum == 0.0:
        raise ValueError("source surface has zero coordinate scale")
    source_scaled = source_points / maximum
    candidate_scaled = candidate_points / maximum
    origin = np.min(source_scaled, axis=0)
    source_scaled = source_scaled - origin
    candidate_scaled = candidate_scaled - origin
    diagonal = float(np.linalg.norm(np.ptp(source_scaled, axis=0)))
    if not np.isfinite(diagonal) or diagonal <= 0.0:
        raise ValueError("source surface has zero bounding-box diagonal")
    return source_scaled / diagonal, candidate_scaled / diagonal


def _plane(triangle: np.ndarray) -> tuple[np.ndarray, float]:
    normal = np.cross(triangle[1] - triangle[0], triangle[2] - triangle[0])
    length = float(np.linalg.norm(normal))
    if not np.isfinite(length) or length <= _AREA_TOLERANCE_FACTOR:
        raise ValueError("source or candidate boundary contains a degenerate face")
    normal = normal / length
    axis = int(np.argmax(np.abs(normal)))
    if normal[axis] < 0.0:
        normal = -normal
    return normal, float(np.dot(normal, triangle[0]))


def _same_plane(
    left_normal: np.ndarray,
    left_offset: float,
    right_normal: np.ndarray,
    right_offset: float,
) -> bool:
    return bool(
        1.0 - float(np.dot(left_normal, right_normal)) <= _NORMAL_TOLERANCE
        and abs(left_offset - right_offset) <= _DISTANCE_TOLERANCE
    )


def _project(points: np.ndarray, axis: int) -> np.ndarray:
    return np.delete(points, axis, axis=-1)


def _orient2d(first: np.ndarray, second: np.ndarray, third: np.ndarray) -> float:
    return float(
        (second[0] - first[0]) * (third[1] - first[1])
        - (second[1] - first[1]) * (third[0] - first[0])
    )


def _point_in_triangle(point: np.ndarray, triangle: np.ndarray, *, strict: bool = False) -> bool:
    signs = np.asarray(
        (
            _orient2d(triangle[0], triangle[1], point),
            _orient2d(triangle[1], triangle[2], point),
            _orient2d(triangle[2], triangle[0], point),
        )
    )
    tolerance = _AREA_TOLERANCE_FACTOR
    if strict:
        return bool(np.all(signs > tolerance) or np.all(signs < -tolerance))
    return bool(np.all(signs >= -tolerance) or np.all(signs <= tolerance))


def _proper_segment_intersection(
    left: tuple[np.ndarray, np.ndarray], right: tuple[np.ndarray, np.ndarray]
) -> bool:
    a, b = left
    c, d = right
    tolerance = _AREA_TOLERANCE_FACTOR
    ab_c = _orient2d(a, b, c)
    ab_d = _orient2d(a, b, d)
    cd_a = _orient2d(c, d, a)
    cd_b = _orient2d(c, d, b)
    return bool(
        ((ab_c > tolerance and ab_d < -tolerance) or (ab_c < -tolerance and ab_d > tolerance))
        and ((cd_a > tolerance and cd_b < -tolerance) or (cd_a < -tolerance and cd_b > tolerance))
    )


def _triangle_area(triangle: np.ndarray) -> float:
    return 0.5 * abs(_orient2d(triangle[0], triangle[1], triangle[2]))


def _cross2d(left: np.ndarray, right: np.ndarray) -> float:
    return float(left[0] * right[1] - left[1] * right[0])


def _segment_inside_patch(
    segment: tuple[np.ndarray, np.ndarray],
    boundary_segments: list[tuple[np.ndarray, np.ndarray]],
    patch_triangles: np.ndarray,
) -> bool:
    start, end = segment
    direction = end - start
    squared_length = float(np.dot(direction, direction))
    if squared_length <= _DISTANCE_TOLERANCE**2:
        return False
    length = float(np.sqrt(squared_length))
    parameter_tolerance = _DISTANCE_TOLERANCE / length
    parameters = [0.0, 1.0]
    for boundary_start, boundary_end in boundary_segments:
        boundary_direction = boundary_end - boundary_start
        relative = boundary_start - start
        denominator = _cross2d(direction, boundary_direction)
        if abs(denominator) > _AREA_TOLERANCE_FACTOR:
            parameter = _cross2d(relative, boundary_direction) / denominator
            boundary_parameter = _cross2d(relative, direction) / denominator
            if (
                -parameter_tolerance <= parameter <= 1.0 + parameter_tolerance
                and -parameter_tolerance <= boundary_parameter <= 1.0 + parameter_tolerance
            ):
                parameters.append(min(1.0, max(0.0, parameter)))
            continue
        distances = (
            abs(_orient2d(start, end, boundary_start)) / length,
            abs(_orient2d(start, end, boundary_end)) / length,
        )
        if max(distances) > _DISTANCE_TOLERANCE:
            continue
        for point in (boundary_start, boundary_end):
            parameter = float(np.dot(point - start, direction) / squared_length)
            if -parameter_tolerance <= parameter <= 1.0 + parameter_tolerance:
                parameters.append(min(1.0, max(0.0, parameter)))
    parameters.sort()
    unique_parameters = [parameters[0]]
    for parameter in parameters[1:]:
        if parameter > unique_parameters[-1] + parameter_tolerance:
            unique_parameters.append(parameter)
        else:
            unique_parameters[-1] = max(unique_parameters[-1], parameter)
    for low, high in zip(unique_parameters, unique_parameters[1:], strict=False):
        if high <= low + parameter_tolerance:
            continue
        midpoint = start + (0.5 * (low + high)) * direction
        if not any(
            _point_in_triangle(midpoint, source_triangle) for source_triangle in patch_triangles
        ):
            return False
    return True


def _build_patches(source: np.ndarray, faces: np.ndarray) -> list[_Patch]:
    triangles3 = source[faces]
    planes = [_plane(triangle) for triangle in triangles3]
    parent = list(range(len(faces)))

    def find(item: int) -> int:
        while parent[item] != item:
            parent[item] = parent[parent[item]]
            item = parent[item]
        return item

    def union(left: int, right: int) -> None:
        left_root = find(left)
        right_root = find(right)
        if left_root != right_root:
            parent[right_root] = left_root

    edge_faces: dict[tuple[int, int], list[int]] = defaultdict(list)
    for face_index, face in enumerate(faces):
        for first, second in ((0, 1), (1, 2), (0, 2)):
            edge = tuple(sorted((int(face[first]), int(face[second]))))
            edge_faces[edge].append(face_index)
    for owners in edge_faces.values():
        for left, right in zip(owners, owners[1:], strict=False):
            if _same_plane(*planes[left], *planes[right]):
                union(left, right)

    members: dict[int, list[int]] = defaultdict(list)
    for face_index in range(len(faces)):
        members[find(face_index)].append(face_index)

    patches: list[_Patch] = []
    for face_indices in members.values():
        normal, offset = planes[face_indices[0]]
        axis = int(np.argmax(np.abs(normal)))
        patch_faces = faces[np.asarray(face_indices, dtype=np.int64)]
        patch_edge_count: dict[tuple[int, int], int] = defaultdict(int)
        for face in patch_faces:
            for first, second in ((0, 1), (1, 2), (0, 2)):
                edge = tuple(sorted((int(face[first]), int(face[second]))))
                patch_edge_count[edge] += 1
        boundary_edges = tuple(edge for edge, count in patch_edge_count.items() if count == 1)
        patches.append(
            _Patch(
                faces=tuple(face_indices),
                normal=normal,
                offset=offset,
                axis=axis,
                triangles=_project(source[patch_faces], axis),
                boundary_edges=boundary_edges,
            )
        )
    return patches


def _triangle_fully_inside_patch(
    triangle: np.ndarray,
    patch: _Patch,
    source: np.ndarray,
) -> bool:
    candidate = _project(triangle, patch.axis)
    if _triangle_area(candidate) <= _AREA_TOLERANCE_FACTOR:
        return False
    probes = np.vstack((candidate, np.mean(candidate, axis=0, keepdims=True)))
    if any(
        not any(_point_in_triangle(probe, source_triangle) for source_triangle in patch.triangles)
        for probe in probes
    ):
        return False

    candidate_edges = (
        (candidate[0], candidate[1]),
        (candidate[1], candidate[2]),
        (candidate[0], candidate[2]),
    )
    boundary_segments = [
        tuple(_project(source[np.asarray(edge, dtype=np.int64)], patch.axis))
        for edge in patch.boundary_edges
    ]
    if any(
        not _segment_inside_patch(candidate_edge, boundary_segments, patch.triangles)
        for candidate_edge in candidate_edges
    ):
        return False
    boundary_vertices = {vertex for edge in patch.boundary_edges for vertex in edge}
    return not any(
        _point_in_triangle(_project(source[vertex], patch.axis), candidate, strict=True)
        for vertex in boundary_vertices
    )


def _triangles_overlap(left: np.ndarray, right: np.ndarray) -> bool:
    if np.any(np.max(left, axis=0) < np.min(right, axis=0) - _DISTANCE_TOLERANCE):
        return False
    if np.any(np.max(right, axis=0) < np.min(left, axis=0) - _DISTANCE_TOLERANCE):
        return False
    left_edges = ((left[0], left[1]), (left[1], left[2]), (left[0], left[2]))
    right_edges = ((right[0], right[1]), (right[1], right[2]), (right[0], right[2]))
    if any(
        _proper_segment_intersection(left_edge, right_edge)
        for left_edge in left_edges
        for right_edge in right_edges
    ):
        return True
    if any(_point_in_triangle(point, right, strict=True) for point in left):
        return True
    if any(_point_in_triangle(point, left, strict=True) for point in right):
        return True
    left_centroid = np.mean(left, axis=0)
    right_centroid = np.mean(right, axis=0)
    return _point_in_triangle(left_centroid, right, strict=True) or _point_in_triangle(
        right_centroid, left, strict=True
    )


def _segment_covered(
    target: tuple[np.ndarray, np.ndarray],
    covers: list[tuple[np.ndarray, np.ndarray]],
) -> bool:
    start, end = target
    direction = end - start
    squared_length = float(np.dot(direction, direction))
    if squared_length <= _DISTANCE_TOLERANCE**2:
        return False
    length = float(np.sqrt(squared_length))
    parameter_tolerance = _DISTANCE_TOLERANCE / length
    intervals: list[tuple[float, float]] = []
    for cover_start, cover_end in covers:
        distances = (
            abs(_orient2d(start, end, cover_start)) / length,
            abs(_orient2d(start, end, cover_end)) / length,
        )
        if max(distances) > _DISTANCE_TOLERANCE:
            continue
        first = float(np.dot(cover_start - start, direction) / squared_length)
        second = float(np.dot(cover_end - start, direction) / squared_length)
        low, high = sorted((first, second))
        low = max(0.0, low)
        high = min(1.0, high)
        if high >= low - parameter_tolerance:
            intervals.append((low, high))
    if not intervals:
        return False
    intervals.sort()
    covered_end = 0.0
    for low, high in intervals:
        if low > covered_end + parameter_tolerance:
            return False
        covered_end = max(covered_end, high)
    return covered_end >= 1.0 - parameter_tolerance


def _patch_feature_boundary_preserved(
    patch: _Patch,
    source: np.ndarray,
    candidate: np.ndarray,
    candidate_faces: np.ndarray,
) -> bool:
    edge_count: dict[tuple[int, int], int] = defaultdict(int)
    for face in candidate_faces:
        for first, second in ((0, 1), (1, 2), (0, 2)):
            edge = tuple(sorted((int(face[first]), int(face[second]))))
            edge_count[edge] += 1
    candidate_boundary_edges = tuple(edge for edge, count in edge_count.items() if count == 1)
    source_segments = [
        tuple(_project(source[np.asarray(edge, dtype=np.int64)], patch.axis))
        for edge in patch.boundary_edges
    ]
    candidate_segments = [
        tuple(_project(candidate[np.asarray(edge, dtype=np.int64)], patch.axis))
        for edge in candidate_boundary_edges
    ]
    return all(
        _segment_covered(segment, candidate_segments) for segment in source_segments
    ) and all(_segment_covered(segment, source_segments) for segment in candidate_segments)


def audit_source_facet_provenance_python(
    source_points: np.ndarray,
    source_faces: np.ndarray,
    candidate_points: np.ndarray,
    boundary_faces: np.ndarray,
) -> dict[str, int | bool]:
    """Prove complete, non-overlapping planar-patch ownership of boundary faces."""
    source, candidate = _normalized_points(source_points, candidate_points)
    canonical_source = np.sort(source_faces, axis=1)
    candidate_provenance = {
        tuple(float(value) for value in point): index for index, point in enumerate(source_points)
    }
    exact_boundary: set[tuple[int, int, int]] = set()
    for face in boundary_faces:
        provenance = []
        for vertex in face:
            source_vertex = candidate_provenance.get(
                tuple(float(value) for value in candidate_points[int(vertex)])
            )
            provenance.append(-1 if source_vertex is None else source_vertex)
        if all(vertex >= 0 for vertex in provenance):
            exact_boundary.add(tuple(sorted(provenance)))
    source_keys = {tuple(int(vertex) for vertex in face) for face in canonical_source}
    n_exact = len(source_keys & exact_boundary)
    n_source_faces = len(source_faces)
    n_candidate_faces = len(boundary_faces)
    if n_exact == n_source_faces and n_candidate_faces == n_source_faces:
        return {
            "n_source_faces": n_source_faces,
            "n_source_faces_on_boundary": n_exact,
            "n_missing_source_faces": 0,
            "n_candidate_boundary_faces": n_candidate_faces,
            "n_owned_candidate_faces": n_candidate_faces,
            "n_unowned_candidate_faces": 0,
            "n_source_planar_patches": 0,
            "n_uncovered_source_patches": 0,
            "n_area_mismatch_patches": 0,
            "n_feature_boundary_mismatches": 0,
            "n_overlap_pairs": 0,
            "source_faces_preserved": True,
        }

    patches = _build_patches(source, source_faces)
    owners: list[int] = []
    unowned = 0
    for face in boundary_faces:
        triangle = candidate[face]
        try:
            normal, offset = _plane(triangle)
        except ValueError:
            owners.append(-1)
            unowned += 1
            continue
        matches = [
            patch_index
            for patch_index, patch in enumerate(patches)
            if _same_plane(normal, offset, patch.normal, patch.offset)
            and _triangle_fully_inside_patch(triangle, patch, source)
        ]
        owner = matches[0] if len(matches) == 1 else -1
        owners.append(owner)
        unowned += owner < 0

    uncovered_patches = 0
    area_mismatches = 0
    feature_mismatches = 0
    overlap_pairs = 0
    area_tolerance = _AREA_TOLERANCE_FACTOR * max(1, n_source_faces + n_candidate_faces)
    for patch_index, patch in enumerate(patches):
        face_indices = [index for index, owner in enumerate(owners) if owner == patch_index]
        if not face_indices:
            uncovered_patches += 1
            continue
        raw_faces = boundary_faces[np.asarray(face_indices, dtype=np.int64)]
        projected = _project(candidate[raw_faces], patch.axis)
        source_area = sum(_triangle_area(triangle) for triangle in patch.triangles)
        candidate_area = sum(_triangle_area(triangle) for triangle in projected)
        if abs(source_area - candidate_area) > area_tolerance:
            area_mismatches += 1
        for left in range(len(projected)):
            for right in range(left + 1, len(projected)):
                overlap_pairs += _triangles_overlap(projected[left], projected[right])
        if not _patch_feature_boundary_preserved(patch, source, candidate, raw_faces):
            feature_mismatches += 1

    preserved = bool(
        n_source_faces > 0
        and n_candidate_faces > 0
        and unowned == 0
        and uncovered_patches == 0
        and area_mismatches == 0
        and feature_mismatches == 0
        and overlap_pairs == 0
    )
    return {
        "n_source_faces": n_source_faces,
        "n_source_faces_on_boundary": n_exact,
        "n_missing_source_faces": n_source_faces - n_exact,
        "n_candidate_boundary_faces": n_candidate_faces,
        "n_owned_candidate_faces": n_candidate_faces - unowned,
        "n_unowned_candidate_faces": unowned,
        "n_source_planar_patches": len(patches),
        "n_uncovered_source_patches": uncovered_patches,
        "n_area_mismatch_patches": area_mismatches,
        "n_feature_boundary_mismatches": feature_mismatches,
        "n_overlap_pairs": overlap_pairs,
        "source_faces_preserved": preserved,
    }


__all__ = ["audit_source_facet_provenance_python"]
