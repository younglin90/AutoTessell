"""Local near-wall cavity refinement for tetrahedral meshes.

This module is deliberately independent from the native mesher driver.  It inserts
one interior point at a time and accepts a retriangulation only when topology,
volume, element validity, and boundary skewness all pass conservative guards.
"""

from __future__ import annotations

from collections import Counter, deque
from dataclasses import dataclass, field

import numpy as np

Face = tuple[int, int, int]


@dataclass(frozen=True)
class BoundaryFaceOwner:
    face: Face
    owner: int
    apex: int
    height: float
    diameter: float
    height_ratio: float
    skew: float


@dataclass
class NearWallResult:
    points: np.ndarray
    tets: np.ndarray
    attempted: int = 0
    accepted: int = 0
    rejection_counters: dict[str, int] = field(default_factory=dict)
    before_skew: float = 0.0
    after_skew: float = 0.0
    volume_before: float = 0.0
    volume_after: float = 0.0


@dataclass(frozen=True)
class TetQualityMetrics:
    boundary_skew: float
    internal_skew: float
    non_orthogonality: float
    min_face_weight: float
    min_volume_ratio: float


def _faces(tets: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    faces = np.concatenate(
        [
            tets[:, [0, 1, 2]],
            tets[:, [0, 1, 3]],
            tets[:, [0, 2, 3]],
            tets[:, [1, 2, 3]],
        ],
        axis=0,
    )
    owners = np.tile(np.arange(tets.shape[0], dtype=np.int64), 4)
    return faces, owners


def boundary_face_keys(tets: np.ndarray) -> set[Face]:
    """Return orientation-free global tet boundary faces."""
    tets = np.asarray(tets, dtype=np.int64)
    if tets.size == 0:
        return set()
    faces, _ = _faces(tets)
    sorted_faces = np.sort(faces, axis=1)
    unique, counts = np.unique(sorted_faces, axis=0, return_counts=True)
    return {tuple(map(int, face)) for face in unique[counts == 1]}


def _boundary_records(tets: np.ndarray) -> list[tuple[Face, int]]:
    if tets.size == 0:
        return []
    faces, owners = _faces(tets)
    sorted_faces = np.sort(faces, axis=1)
    _, inverse, counts = np.unique(sorted_faces, axis=0, return_inverse=True, return_counts=True)
    ids = np.flatnonzero(counts[inverse] == 1)
    records = [(tuple(map(int, sorted_faces[index])), int(owners[index])) for index in ids]
    return sorted(records)


def _face_skew(points: np.ndarray, face: Face, owner_tet: np.ndarray) -> float:
    vertices = points[np.asarray(face)]
    normal = np.cross(vertices[1] - vertices[0], vertices[2] - vertices[0])
    magnitude = float(np.linalg.norm(normal))
    if magnitude <= 1e-30:
        return float("inf")
    normal /= magnitude
    face_centre = vertices.mean(axis=0)
    cell_centre = points[owner_tet].mean(axis=0)
    normal_distance = float(np.dot(face_centre - cell_centre, normal))
    projection = cell_centre + normal_distance * normal
    return float(np.linalg.norm(face_centre - projection) / max(abs(normal_distance), 1e-30))


def max_boundary_skew(points: np.ndarray, tets: np.ndarray) -> float:
    """Evaluator-faithful maximum boundary skewness."""
    points = np.asarray(points, dtype=np.float64)
    tets = np.asarray(tets, dtype=np.int64)
    values = [_face_skew(points, face, tets[owner]) for face, owner in _boundary_records(tets)]
    return max(values, default=0.0)


def tet_quality_metrics(points: np.ndarray, tets: np.ndarray) -> TetQualityMetrics:
    """Evaluator-faithful tet face metrics from one deterministic face map."""
    points = np.asarray(points, dtype=np.float64)
    tets = np.asarray(tets, dtype=np.int64)
    if tets.size == 0:
        return TetQualityMetrics(0.0, 0.0, 0.0, 1.0, 1.0)
    faces, owners = _faces(tets)
    sorted_faces = np.sort(faces, axis=1)
    unique, inverse, counts = np.unique(
        sorted_faces, axis=0, return_inverse=True, return_counts=True
    )
    order = np.argsort(inverse, kind="stable")
    grouped_owners = owners[order]
    starts = np.zeros(counts.shape[0], dtype=np.int64)
    starts[1:] = np.cumsum(counts)[:-1]
    cell_centres = points[tets].mean(axis=1)
    face_centres = points[unique].mean(axis=1)

    boundary_skew = 0.0
    boundary_mask = counts == 1
    if bool(boundary_mask.any()):
        boundary_faces = points[unique[boundary_mask]]
        normals = np.cross(
            boundary_faces[:, 1] - boundary_faces[:, 0],
            boundary_faces[:, 2] - boundary_faces[:, 0],
        )
        normal_magnitudes = np.linalg.norm(normals, axis=1)
        valid = normal_magnitudes > 1e-30
        if bool(valid.any()):
            unit_normals = normals[valid] / normal_magnitudes[valid, None]
            owner_centres = cell_centres[grouped_owners[starts[boundary_mask]]][valid]
            centres = face_centres[boundary_mask][valid]
            normal_distance = np.einsum(
                "ij,ij->i", centres - owner_centres, unit_normals
            )
            projection = owner_centres + normal_distance[:, None] * unit_normals
            values = np.linalg.norm(centres - projection, axis=1) / np.maximum(
                np.abs(normal_distance), 1e-30
            )
            boundary_skew = float(np.nanmax(values)) if values.size else 0.0

    internal_skew = 0.0
    non_orthogonality = 0.0
    min_face_weight = 1.0
    min_volume_ratio = 1.0
    internal_mask = counts == 2
    if bool(internal_mask.any()):
        internal_starts = starts[internal_mask]
        own = grouped_owners[internal_starts]
        neighbor = grouped_owners[internal_starts + 1]
        owner_centres = cell_centres[own]
        neighbor_centres = cell_centres[neighbor]
        centres = face_centres[internal_mask]
        direction = neighbor_centres - owner_centres
        direction_magnitude = np.linalg.norm(direction, axis=1)
        valid_direction = direction_magnitude > 1e-30
        if bool(valid_direction.any()):
            difference = centres[valid_direction] - owner_centres[valid_direction]
            parameter = np.einsum(
                "ij,ij->i", difference, direction[valid_direction]
            ) / (direction_magnitude[valid_direction] ** 2)
            projection = owner_centres[valid_direction] + parameter[:, None] * direction[
                valid_direction
            ]
            internal_values = np.linalg.norm(
                centres[valid_direction] - projection, axis=1
            ) / direction_magnitude[valid_direction]
            internal_skew = (
                float(np.nanmax(internal_values)) if internal_values.size else 0.0
            )

        internal_faces = points[unique[internal_mask]]
        area_vectors = np.cross(
            internal_faces[:, 1] - internal_faces[:, 0],
            internal_faces[:, 2] - internal_faces[:, 0],
        )
        area_magnitudes = np.linalg.norm(area_vectors, axis=1)
        valid_angle = valid_direction & (area_magnitudes > 1e-30)
        if bool(valid_angle.any()):
            cosine = np.clip(
                np.abs(
                    np.einsum(
                        "ij,ij->i",
                        area_vectors[valid_angle],
                        direction[valid_angle],
                    )
                )
                / (
                    area_magnitudes[valid_angle]
                    * direction_magnitude[valid_angle]
                ),
                0.0,
                1.0,
            )
            non_orthogonality = float(np.nanmax(np.degrees(np.arccos(cosine))))

        distance_owner = np.abs(
            np.einsum("ij,ij->i", area_vectors, centres - owner_centres)
        )
        distance_neighbor = np.abs(
            np.einsum("ij,ij->i", area_vectors, neighbor_centres - centres)
        )
        denominator = distance_owner + distance_neighbor
        valid_weight = denominator > 1e-300
        if bool(valid_weight.any()):
            weights = np.minimum(
                distance_owner[valid_weight], distance_neighbor[valid_weight]
            ) / denominator[valid_weight]
            min_face_weight = float(np.nanmin(weights)) if weights.size else 1.0

        volumes = np.abs(_volumes(points, tets))
        owner_volumes = volumes[own]
        neighbor_volumes = volumes[neighbor]
        valid_volume = (owner_volumes > 1e-30) & (neighbor_volumes > 1e-30)
        if bool(valid_volume.any()):
            adjacent_ratio = np.maximum(
                owner_volumes[valid_volume], neighbor_volumes[valid_volume]
            ) / np.minimum(owner_volumes[valid_volume], neighbor_volumes[valid_volume])
            min_volume_ratio = float(1.0 / max(float(np.nanmax(adjacent_ratio)), 1.0))
        else:
            min_volume_ratio = 0.0
    return TetQualityMetrics(
        boundary_skew=boundary_skew,
        internal_skew=internal_skew,
        non_orthogonality=non_orthogonality,
        min_face_weight=min_face_weight,
        min_volume_ratio=min_volume_ratio,
    )


def _failure_vector(metrics: TetQualityMetrics) -> tuple[float, ...]:
    failures = (
        metrics.boundary_skew / 4.0,
        metrics.internal_skew / 4.0,
        metrics.non_orthogonality / 70.0,
        0.05 / max(metrics.min_face_weight, 1e-300),
        0.01 / max(metrics.min_volume_ratio, 1e-300),
    )
    return tuple(sorted((float(value) for value in failures), reverse=True))


def _quality_rejection(
    before: TetQualityMetrics, after: TetQualityMetrics
) -> str | None:
    maximum_metrics = (
        ("boundary_skew", before.boundary_skew, after.boundary_skew),
        ("internal_skew", before.internal_skew, after.internal_skew),
        ("non_orthogonality", before.non_orthogonality, after.non_orthogonality),
    )
    minimum_metrics = (
        ("face_weight", before.min_face_weight, after.min_face_weight),
        ("volume_ratio", before.min_volume_ratio, after.min_volume_ratio),
    )
    for name, old, new in maximum_metrics:
        tolerance = 1e-10 * max(1.0, abs(old))
        if np.isfinite(old) and (not np.isfinite(new) or new > old + tolerance):
            return name
    for name, old, new in minimum_metrics:
        tolerance = 1e-10 * max(1.0, abs(old))
        if np.isfinite(old) and (not np.isfinite(new) or new < old - tolerance):
            return name
    if not after.boundary_skew < before.boundary_skew - 1e-12:
        return "non_improving"
    if not _failure_vector(after) < _failure_vector(before):
        return "quality_non_improving"
    return None


def detect_boundary_face_owners(
    points: np.ndarray,
    tets: np.ndarray,
    *,
    max_height_ratio: float = 0.20,
) -> list[BoundaryFaceOwner]:
    """Detect flat boundary-owner tetrahedra, worst skew first."""
    points = np.asarray(points, dtype=np.float64)
    tets = np.asarray(tets, dtype=np.int64)
    detected: list[BoundaryFaceOwner] = []
    for face, owner in _boundary_records(tets):
        apex_candidates = sorted(set(map(int, tets[owner])) - set(face))
        if len(apex_candidates) != 1:
            continue
        apex = apex_candidates[0]
        triangle = points[np.asarray(face)]
        normal = np.cross(triangle[1] - triangle[0], triangle[2] - triangle[0])
        area2 = float(np.linalg.norm(normal))
        diameter = max(
            float(np.linalg.norm(triangle[i] - triangle[j])) for i, j in ((0, 1), (0, 2), (1, 2))
        )
        if area2 <= 1e-30 or diameter <= 1e-30:
            continue
        height = abs(float(np.dot(points[apex] - triangle[0], normal / area2)))
        ratio = height / diameter
        if ratio <= max_height_ratio:
            detected.append(
                BoundaryFaceOwner(
                    face=face,
                    owner=owner,
                    apex=apex,
                    height=height,
                    diameter=diameter,
                    height_ratio=ratio,
                    skew=_face_skew(points, face, tets[owner]),
                )
            )
    return sorted(detected, key=lambda item: (-item.skew, item.face, item.owner))


def build_tet_adjacency(tets: np.ndarray) -> tuple[tuple[int, ...], ...]:
    """Build deterministic face-sharing tet adjacency."""
    tets = np.asarray(tets, dtype=np.int64)
    face_to_tets: dict[Face, list[int]] = {}
    for tet_id, tet in enumerate(tets):
        for omitted in range(4):
            face = tuple(sorted(int(tet[i]) for i in range(4) if i != omitted))
            face_to_tets.setdefault(face, []).append(tet_id)
    neighbors = [set() for _ in range(tets.shape[0])]
    for incident in face_to_tets.values():
        for left in incident:
            neighbors[left].update(right for right in incident if right != left)
    return tuple(tuple(sorted(items)) for items in neighbors)


def _face_incidence(tets: np.ndarray) -> dict[Face, tuple[int, ...]]:
    incident: dict[Face, list[int]] = {}
    for tet_id, tet in enumerate(tets):
        for omitted in range(4):
            face = tuple(sorted(int(tet[index]) for index in range(4) if index != omitted))
            incident.setdefault(face, []).append(tet_id)
    return {face: tuple(sorted(tet_ids)) for face, tet_ids in incident.items()}


def find_containing_tet(
    points: np.ndarray,
    tets: np.ndarray,
    point: np.ndarray,
    *,
    relative_tolerance: float = 1e-11,
    _bounds: tuple[np.ndarray, np.ndarray] | None = None,
) -> int | None:
    """Find first containing tet using scaled barycentric orientation tests."""
    points = np.asarray(points, dtype=np.float64)
    tets = np.asarray(tets, dtype=np.int64)
    point = np.asarray(point, dtype=np.float64)
    if tets.size == 0:
        return None
    if _bounds is None:
        all_vertices = points[tets]
        lower = all_vertices.min(axis=1)
        upper = all_vertices.max(axis=1)
    else:
        lower, upper = _bounds
    diagonal = max(float(np.linalg.norm(np.ptp(points, axis=0))), np.finfo(float).tiny)
    absolute_tolerance = relative_tolerance * diagonal
    candidate_ids = np.flatnonzero(
        np.all(point >= lower - absolute_tolerance, axis=1)
        & np.all(point <= upper + absolute_tolerance, axis=1)
    )
    if candidate_ids.size == 0:
        return None
    vertices = points[tets[candidate_ids]]
    matrices = np.transpose(vertices[:, 1:] - vertices[:, :1], (0, 2, 1))
    determinants = np.linalg.det(matrices)
    scales = np.linalg.norm(np.ptp(vertices, axis=1), axis=1)
    floors = np.finfo(float).eps * np.maximum(scales, np.finfo(float).tiny) ** 3 * 32.0
    valid = np.abs(determinants) > floors
    valid_local_ids = np.flatnonzero(valid)
    if valid_local_ids.size == 0:
        return None
    right_hand_side = point[None, :] - vertices[valid_local_ids, 0]
    bary = np.linalg.solve(
        matrices[valid_local_ids], right_hand_side[..., None]
    )[..., 0]
    weights = np.column_stack([1.0 - bary.sum(axis=1), bary])
    inside = np.all(weights >= -relative_tolerance, axis=1) & np.all(
        weights <= 1.0 + relative_tolerance, axis=1
    )
    containing = candidate_ids[valid_local_ids[np.flatnonzero(inside)]]
    return int(containing[0]) if containing.size else None


def _shortest_path(
    adjacency: tuple[tuple[int, ...], ...],
    start: int,
    goal: int,
    blocked_edges: set[tuple[int, int]] | None = None,
) -> list[int]:
    blocked_edges = blocked_edges or set()
    queue: deque[int] = deque([start])
    parent = {start: -1}
    while queue:
        current = queue.popleft()
        if current == goal:
            break
        for neighbor in adjacency[current]:
            if tuple(sorted((current, neighbor))) in blocked_edges:
                continue
            if neighbor not in parent:
                parent[neighbor] = current
                queue.append(neighbor)
    if goal not in parent:
        return []
    path = []
    current = goal
    while current >= 0:
        path.append(current)
        current = parent[current]
    return path[::-1]


def _path_alternatives(
    adjacency: tuple[tuple[int, ...], ...], start: int, goal: int, limit: int
) -> list[list[int]]:
    first = _shortest_path(adjacency, start, goal)
    if not first:
        return []
    paths = [first]
    seen = {tuple(first)}
    for left, right in zip(first, first[1:]):
        alternate = _shortest_path(adjacency, start, goal, {tuple(sorted((left, right)))})
        key = tuple(alternate)
        if alternate and key not in seen:
            paths.append(alternate)
            seen.add(key)
            if len(paths) >= limit:
                break
    return paths


def _cavity_boundary(tets: np.ndarray, cavity: set[int]) -> list[Face]:
    counts: Counter[Face] = Counter()
    for tet_id in sorted(cavity):
        tet = tets[tet_id]
        for omitted in range(4):
            counts[tuple(sorted(int(tet[i]) for i in range(4) if i != omitted))] += 1
    return sorted(face for face, count in counts.items() if count == 1)


def grow_visibility_cavity(
    points: np.ndarray,
    tets: np.ndarray,
    point: np.ndarray,
    seed_cavity: set[int],
    *,
    max_steps: int = 64,
    max_cavity_tets: int = 512,
    _incidence: dict[Face, tuple[int, ...]] | None = None,
    _global_boundary: set[Face] | None = None,
) -> tuple[set[int] | None, str]:
    """Grow a connected cavity until ``point`` sees every boundary face.

    A boundary face is visible from the wrong side when ``point`` and the
    cavity tet's opposite vertex lie on opposite sides of its plane.  Crossing
    that internal face removes the overlapping fan tet.  Original global
    boundary faces are hard constraints and are never crossed.
    """
    points = np.asarray(points, dtype=np.float64)
    tets = np.asarray(tets, dtype=np.int64)
    point = np.asarray(point, dtype=np.float64)
    cavity = set(seed_cavity)
    if not cavity or min(cavity) < 0 or max(cavity) >= tets.shape[0]:
        return None, "invalid_seed"
    incidence = _incidence if _incidence is not None else _face_incidence(tets)
    global_boundary = (
        _global_boundary
        if _global_boundary is not None
        else {face for face, owners in incidence.items() if len(owners) == 1}
    )
    diagonal = max(float(np.linalg.norm(np.ptp(points, axis=0))), np.finfo(float).tiny)
    orientation_floor = np.finfo(float).eps * diagonal**3 * 64.0

    for _ in range(max_steps):
        additions: set[int] = set()
        for face in _cavity_boundary(tets, cavity):
            incident = incidence.get(face, ())
            inside = [tet_id for tet_id in incident if tet_id in cavity]
            if len(inside) != 1:
                return None, "nonmanifold_cavity"
            owner = inside[0]
            apex_ids = set(map(int, tets[owner])) - set(face)
            if len(apex_ids) != 1:
                return None, "nonmanifold_cavity"
            triangle = points[np.asarray(face)]
            normal = np.cross(triangle[1] - triangle[0], triangle[2] - triangle[0])
            apex_side = float(np.dot(points[apex_ids.pop()] - triangle[0], normal))
            point_side = float(np.dot(point - triangle[0], normal))
            if apex_side * point_side > orientation_floor**2:
                continue
            if face in global_boundary:
                return None, "visibility_boundary"
            outside = [tet_id for tet_id in incident if tet_id not in cavity]
            if len(outside) != 1:
                return None, "nonmanifold_cavity"
            additions.add(outside[0])
        if not additions:
            return cavity, "visible"
        cavity.update(additions)
        if len(cavity) > max_cavity_tets:
            return None, "cavity_limit"
    return None, "visibility_limit"


def _volumes(points: np.ndarray, tets: np.ndarray) -> np.ndarray:
    vertices = points[tets]
    return (
        np.einsum(
            "ij,ij->i",
            vertices[:, 1] - vertices[:, 0],
            np.cross(vertices[:, 2] - vertices[:, 0], vertices[:, 3] - vertices[:, 0]),
        )
        / 6.0
    )


def _try_cavity(
    points: np.ndarray,
    tets: np.ndarray,
    point: np.ndarray,
    cavity: set[int],
    original_boundary: set[Face],
    before_metrics: TetQualityMetrics,
    *,
    volume_relative_tolerance: float,
) -> tuple[np.ndarray, np.ndarray, str, TetQualityMetrics] | None:
    boundary = _cavity_boundary(tets, cavity)
    if not boundary:
        return None
    new_id = points.shape[0]
    candidate_points = np.vstack([points, point])
    new_tets = np.asarray([(*face, new_id) for face in boundary], dtype=np.int64)
    volumes = _volumes(candidate_points, new_tets)
    diagonal = max(float(np.linalg.norm(np.ptp(points, axis=0))), np.finfo(float).tiny)
    floor = np.finfo(float).eps * diagonal**3 * 128.0
    if bool(np.any(np.abs(volumes) <= floor)):
        return candidate_points, tets, "degenerate", before_metrics
    negative = volumes < 0.0
    swapped = new_tets[negative].copy()
    swapped[:, [1, 2]] = swapped[:, [2, 1]]
    new_tets[negative] = swapped
    removed_volume = float(np.abs(_volumes(points, tets[sorted(cavity)])).sum())
    inserted_volume = float(np.abs(volumes).sum())
    tolerance = volume_relative_tolerance * max(removed_volume, diagonal**3 * 1e-30)
    if abs(inserted_volume - removed_volume) > tolerance:
        return candidate_points, tets, "volume", before_metrics
    kept = tets[[index not in cavity for index in range(tets.shape[0])]]
    candidate_tets = np.vstack([kept, new_tets])
    new_canonical = np.sort(new_tets, axis=1)
    if np.unique(new_canonical, axis=0).shape[0] != new_tets.shape[0]:
        return candidate_points, tets, "duplicate", before_metrics
    if boundary_face_keys(candidate_tets) != original_boundary:
        return candidate_points, tets, "boundary", before_metrics
    after_metrics = tet_quality_metrics(candidate_points, candidate_tets)
    quality_rejection = _quality_rejection(before_metrics, after_metrics)
    if quality_rejection is not None:
        return candidate_points, tets, quality_rejection, after_metrics
    if not np.array_equal(candidate_points[: points.shape[0]], points):
        return candidate_points, tets, "surface_points", after_metrics
    return candidate_points, candidate_tets, "accepted", after_metrics


def _candidate_direction(
    points: np.ndarray,
    owner: BoundaryFaceOwner,
    surface_vertices: np.ndarray,
    surface_faces: np.ndarray,
    depth: float,
    lateral_fraction: float = 0.0,
) -> np.ndarray:
    del surface_vertices, surface_faces
    triangle = points[np.asarray(owner.face)]
    centre = triangle.mean(axis=0)
    normal = np.cross(triangle[1] - triangle[0], triangle[2] - triangle[0])
    normal /= np.linalg.norm(normal)
    owner_sign = float(np.dot(points[owner.apex] - centre, normal))
    signed_normal = normal if owner_sign >= 0.0 else -normal
    apex_vector = points[owner.apex] - centre
    tangential = apex_vector - float(np.dot(apex_vector, signed_normal)) * signed_normal
    height_fraction = min(depth / max(owner.height, 1e-30), 1.0)
    return (
        centre
        + depth * signed_normal
        + lateral_fraction * height_fraction * tangential
    )


def _interior_target_candidates(
    points: np.ndarray,
    tets: np.ndarray,
    adjacency: tuple[tuple[int, ...], ...],
    owner: BoundaryFaceOwner,
    *,
    max_layers: int = 2,
    max_candidates: int = 12,
) -> list[np.ndarray]:
    """Return bounded inward candidates aimed at nearby tet centroids."""
    triangle = points[np.asarray(owner.face)]
    centre = triangle.mean(axis=0)
    normal = np.cross(triangle[1] - triangle[0], triangle[2] - triangle[0])
    normal /= np.linalg.norm(normal)
    if float(np.dot(points[owner.apex] - centre, normal)) < 0.0:
        normal = -normal

    scale = max(float(np.linalg.norm(np.ptp(points, axis=0))), np.finfo(float).tiny)
    depth_floor = np.finfo(float).eps * scale * 64.0
    visited = {owner.owner}
    frontier = [owner.owner]
    ranked: list[tuple[tuple[float, int, int, float], np.ndarray]] = []
    for layer in range(1, max_layers + 1):
        next_frontier: list[int] = []
        for tet_id in frontier:
            for neighbor in adjacency[tet_id]:
                if neighbor in visited:
                    continue
                visited.add(neighbor)
                next_frontier.append(neighbor)
        frontier = sorted(next_frontier)
        for tet_id in frontier:
            target = points[tets[tet_id]].mean(axis=0)
            offset = target - centre
            depth = float(np.dot(offset, normal))
            if depth <= depth_floor:
                continue
            tangential = offset - depth * normal
            for lateral_fraction in (0.0, 0.5, 1.0):
                lateral = lateral_fraction * tangential
                skew = float(np.linalg.norm(lateral) / depth)
                if not skew < owner.skew - 1e-12:
                    continue
                point = centre + depth * normal + lateral
                ranked.append(
                    ((skew, layer, tet_id, lateral_fraction), point)
                )

    candidates: list[np.ndarray] = []
    seen: set[bytes] = set()
    for _, point in sorted(ranked, key=lambda item: item[0]):
        key = np.asarray(point, dtype=np.float64).tobytes()
        if key in seen:
            continue
        seen.add(key)
        candidates.append(point)
        if len(candidates) >= max_candidates:
            break
    return candidates


def refine_near_wall(
    points: np.ndarray,
    tets: np.ndarray,
    surface_vertices: np.ndarray,
    surface_faces: np.ndarray,
    *,
    max_height_ratio: float = 0.20,
    depth_fractions: tuple[float, ...] = (0.03, 0.10, 0.30),
    max_owners: int = 32,
    max_expansion_layers: int = 2,
    max_path_alternatives: int = 4,
    max_visibility_steps: int = 64,
    max_cavity_tets: int = 512,
    volume_relative_tolerance: float = 1e-10,
) -> NearWallResult:
    """Apply bounded sequential local refinements with monotone global skew."""
    original_points = np.asarray(points, dtype=np.float64)
    original_tets = np.asarray(tets, dtype=np.int64)
    surface_vertices = np.asarray(surface_vertices, dtype=np.float64)
    surface_faces = np.asarray(surface_faces, dtype=np.int64)
    current_points = original_points.copy()
    current_tets = original_tets.copy()
    initial_metrics = tet_quality_metrics(current_points, current_tets)
    before = initial_metrics.boundary_skew
    result = NearWallResult(
        points=current_points,
        tets=current_tets,
        before_skew=before,
        after_skew=before,
        volume_before=float(np.abs(_volumes(current_points, current_tets)).sum()),
    )
    original_boundary = boundary_face_keys(current_tets)
    owner_attempts = 0
    while owner_attempts < max_owners:
        owners = detect_boundary_face_owners(
            current_points, current_tets, max_height_ratio=max_height_ratio
        )
        if not owners:
            break
        adjacency = build_tet_adjacency(current_tets)
        incidence = _face_incidence(current_tets)
        tet_vertices = current_points[current_tets]
        tet_bounds = (tet_vertices.min(axis=1), tet_vertices.max(axis=1))
        global_boundary = {
            face for face, incident_tets in incidence.items() if len(incident_tets) == 1
        }
        step_metrics = tet_quality_metrics(current_points, current_tets)
        accepted_this_round = False
        for owner in owners:
            if owner_attempts >= max_owners:
                break
            owner_attempts += 1
            best: tuple[
                tuple[float, ...], np.ndarray, np.ndarray, TetQualityMetrics
            ] | None = None
            depths = sorted(
                {
                    *(owner.diameter * fraction for fraction in depth_fractions),
                    *(
                        owner.height * fraction
                        for fraction in (0.02, 0.05, 0.10, 0.25, 0.50, 0.75)
                    ),
                }
            )
            candidate_points = [
                _candidate_direction(
                    current_points,
                    owner,
                    surface_vertices,
                    surface_faces,
                    depth,
                )
                for depth in depths
            ]
            if step_metrics.internal_skew <= 4.0 + 1e-12:
                candidate_points.extend(
                    _interior_target_candidates(
                        current_points,
                        current_tets,
                        adjacency,
                        owner,
                    )
                )
            unique_points: list[np.ndarray] = []
            seen_points: set[bytes] = set()
            for point in candidate_points:
                key = np.asarray(point, dtype=np.float64).tobytes()
                if key not in seen_points:
                    seen_points.add(key)
                    unique_points.append(point)
            for point in unique_points:
                containing = find_containing_tet(
                    current_points, current_tets, point, _bounds=tet_bounds
                )
                result.attempted += 1
                if containing is None:
                    result.rejection_counters["no_containing_tet"] = (
                        result.rejection_counters.get("no_containing_tet", 0) + 1
                    )
                    continue
                paths = _path_alternatives(
                    adjacency, owner.owner, containing, max(1, max_path_alternatives)
                )
                if not paths:
                    result.rejection_counters["disconnected"] = (
                        result.rejection_counters.get("disconnected", 0) + 1
                    )
                    continue
                seeds = [{owner.owner}, *(set(path) for path in paths)]
                seen_seeds: set[frozenset[int]] = set()
                for seed in seeds:
                    seed_key = frozenset(seed)
                    if seed_key in seen_seeds:
                        continue
                    seen_seeds.add(seed_key)
                    cavity, growth_reason = grow_visibility_cavity(
                        current_points,
                        current_tets,
                        point,
                        seed,
                        max_steps=max(max_visibility_steps, 16 * (max_expansion_layers + 1)),
                        max_cavity_tets=max_cavity_tets,
                        _incidence=incidence,
                        _global_boundary=global_boundary,
                    )
                    if cavity is None:
                        result.rejection_counters[growth_reason] = (
                            result.rejection_counters.get(growth_reason, 0) + 1
                        )
                        continue
                    trial = _try_cavity(
                        current_points,
                        current_tets,
                        point,
                        cavity,
                        original_boundary,
                        step_metrics,
                        volume_relative_tolerance=volume_relative_tolerance,
                    )
                    if trial is None:
                        reason = "empty_cavity"
                    else:
                        trial_points, trial_tets, reason, metrics = trial
                        if reason == "accepted":
                            key = (
                                *_failure_vector(metrics),
                                metrics.boundary_skew,
                                metrics.internal_skew,
                                metrics.non_orthogonality,
                                -metrics.min_face_weight,
                                -metrics.min_volume_ratio,
                            )
                            if best is None or key < best[0]:
                                best = (key, trial_points, trial_tets, metrics)
                            continue
                    result.rejection_counters[reason] = result.rejection_counters.get(reason, 0) + 1
            if best is not None:
                _, current_points, current_tets, accepted_metrics = best
                result.after_skew = accepted_metrics.boundary_skew
                result.points = current_points
                result.tets = current_tets
                result.accepted += 1
                accepted_this_round = True
                break
        if not accepted_this_round:
            break
    result.volume_after = float(np.abs(_volumes(result.points, result.tets)).sum())
    return result


__all__ = [
    "BoundaryFaceOwner",
    "NearWallResult",
    "TetQualityMetrics",
    "boundary_face_keys",
    "build_tet_adjacency",
    "detect_boundary_face_owners",
    "find_containing_tet",
    "grow_visibility_cavity",
    "max_boundary_skew",
    "refine_near_wall",
    "tet_quality_metrics",
]
