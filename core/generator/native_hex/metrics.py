"""Read-only Phase 0 reporting metrics for native hex output.

The adaptive writer accepts generic cell faces, so all metrics in this module
operate on that representation.  The uniform path is converted to the same
representation before calling :func:`compute_native_hex_metrics`.
"""

from __future__ import annotations

from collections import deque
from collections.abc import Sequence
from dataclasses import dataclass
from itertools import combinations
from pathlib import Path

import numpy as np

CellFaces = Sequence[Sequence[Sequence[int]]]
_CELL_TYPES = ("hex", "prism", "tet", "other")
_DEFAULT_BETA = 1.0e-3


def read_written_polymesh_cells(case_dir: Path) -> tuple[np.ndarray, list[list[list[int]]]] | None:
    """Reconstruct the cell-face representation from the written polyMesh."""
    poly_dir = case_dir / "constant" / "polyMesh"
    try:
        from core.utils.polymesh_reader import (
            parse_foam_faces,
            parse_foam_labels,
            parse_foam_points_array,
        )

        points = parse_foam_points_array(poly_dir / "points")
        faces = parse_foam_faces(poly_dir / "faces")
        owners = parse_foam_labels(poly_dir / "owner")
        neighbors = parse_foam_labels(poly_dir / "neighbour")
    except Exception:
        return None
    if not faces or not owners or len(owners) != len(faces):
        return None

    max_cell = max(
        max((int(owner) for owner in owners), default=-1),
        max((int(neighbor) for neighbor in neighbors), default=-1),
    )
    if max_cell < 0:
        return None
    cells: list[list[list[int]]] = [[] for _ in range(max_cell + 1)]
    n_internal = len(neighbors)
    for face_index, face in enumerate(faces):
        owner = int(owners[face_index])
        if 0 <= owner < len(cells):
            cells[owner].append([int(vertex) for vertex in face])
        if face_index < n_internal:
            neighbor = int(neighbors[face_index])
            if 0 <= neighbor < len(cells):
                cells[neighbor].append([int(vertex) for vertex in face])
    return points, cells


@dataclass(frozen=True)
class NativeHexMetrics:
    """Phase 0 metrics kept separate from mesh acceptance decisions."""

    cell_census: dict[str, int]
    cell_count_fractions: dict[str, float]
    cell_volume_fractions: dict[str, float]
    cell_volumes: dict[str, float]
    total_volume: float
    score_che: float
    n_hex_clusters: int
    largest_cluster_frac: float
    beta: float
    min_corner_jacobian: float
    local_mean_volume: float
    beta_margin: float
    beta_margin_ratio: float
    beta_pass: bool


def _cell_kind(cell: Sequence[Sequence[int]]) -> str:
    """Classify a closed generic cell from its actual face topology."""
    n_tri = sum(len(face) == 3 for face in cell)
    n_quad = sum(len(face) == 4 for face in cell)
    n_faces = len(cell)
    if n_faces == 6 and n_quad == 6:
        return "hex"
    if n_faces == 5 and n_tri == 2 and n_quad == 3:
        return "prism"
    if n_faces == 4 and n_tri == 4:
        return "tet"
    return "other"


def _face_key(face: Sequence[int]) -> tuple[int, ...]:
    return tuple(sorted(int(vertex) for vertex in face))


def _face_owners(cell_faces: CellFaces) -> dict[tuple[int, ...], list[int]]:
    owners: dict[tuple[int, ...], list[int]] = {}
    for cell_index, cell in enumerate(cell_faces):
        for face in cell:
            key = _face_key(face)
            owners.setdefault(key, []).append(cell_index)
    return owners


def _cell_volume(points: np.ndarray, cell: Sequence[Sequence[int]]) -> float:
    """Compute orientation-free volume from centroid-to-face pyramids."""
    if not cell:
        return 0.0
    vertex_ids = sorted({int(vertex) for face in cell for vertex in face})
    if len(vertex_ids) < 4:
        return 0.0
    center = points[np.asarray(vertex_ids, dtype=np.int64)].mean(axis=0)
    volume = 0.0
    for face in cell:
        if len(face) < 3:
            continue
        anchor = points[int(face[0])] - center
        for index in range(1, len(face) - 1):
            edge_a = points[int(face[index])] - center
            edge_b = points[int(face[index + 1])] - center
            volume += abs(float(np.dot(anchor, np.cross(edge_a, edge_b)))) / 6.0
    return float(volume)


def _cell_volumes(points: np.ndarray, cell_faces: CellFaces) -> np.ndarray:
    return np.asarray([_cell_volume(points, cell) for cell in cell_faces], dtype=np.float64)


def _hex_corner_jacobians(points: np.ndarray, cell: Sequence[Sequence[int]]) -> np.ndarray:
    """Return orientation-independent corner determinant magnitudes.

    The polyMesh writer is allowed to reorder a cell's faces, so a report
    computed from the written shell cannot depend on the original local face
    ordering.  A topological hex has exactly three incident edges at each
    vertex; the absolute determinant of those three edges is the corresponding
    corner-Jacobian magnitude.
    """
    if len(cell) != 6 or any(len(face) != 4 for face in cell):
        return np.empty(0, dtype=np.float64)

    vertex_ids = sorted({int(vertex) for face in cell for vertex in face})
    if len(vertex_ids) != 8:
        return np.empty(0, dtype=np.float64)

    incident: dict[int, set[int]] = {vertex: set() for vertex in vertex_ids}
    for face in cell:
        for index, vertex_raw in enumerate(face):
            vertex = int(vertex_raw)
            prev_vertex = int(face[index - 1])
            next_vertex = int(face[(index + 1) % len(face)])
            incident[vertex].update((prev_vertex, next_vertex))

    values: list[float] = []
    for vertex in vertex_ids:
        neighbors = sorted(incident[vertex])
        if len(neighbors) != 3:
            return np.empty(0, dtype=np.float64)
        origin = points[vertex]
        edges = points[np.asarray(neighbors, dtype=np.int64)] - origin
        values.append(abs(float(np.dot(edges[0], np.cross(edges[1], edges[2])))))
    return np.asarray(values, dtype=np.float64)


def _generic_corner_jacobian(points: np.ndarray, cell: Sequence[Sequence[int]]) -> float:
    """Use centroid-to-face-triangle determinants for non-canonical cells."""
    vertex_ids = sorted({int(vertex) for face in cell for vertex in face})
    if len(vertex_ids) < 4:
        return 0.0
    center = points[np.asarray(vertex_ids, dtype=np.int64)].mean(axis=0)
    values: list[float] = []
    for face in cell:
        if len(face) < 3:
            continue
        anchor = points[int(face[0])] - center
        for index in range(1, len(face) - 1):
            edge_a = points[int(face[index])] - center
            edge_b = points[int(face[index + 1])] - center
            values.append(abs(float(np.dot(anchor, np.cross(edge_a, edge_b)))))
    return min(values, default=0.0)


def _local_cell_neighbors(
    cell_faces: CellFaces,
    owners: dict[tuple[int, ...], list[int]],
) -> list[set[int]]:
    neighbors = [set() for _ in cell_faces]
    for face_owners in owners.values():
        unique = sorted(set(face_owners))
        for left, right in combinations(unique, 2):
            neighbors[left].add(right)
            neighbors[right].add(left)
    return neighbors


def _hex_distribution(
    cell_faces: CellFaces,
    kinds: Sequence[str],
    owners: dict[tuple[int, ...], list[int]],
) -> tuple[float, int, float]:
    hex_ids = {index for index, kind in enumerate(kinds) if kind == "hex"}
    if not hex_ids:
        return 0.0, 0, 0.0

    hex_neighbors = {index: set() for index in sorted(hex_ids)}
    face_virtual_counts = {index: 0 for index in hex_ids}
    for face_owners in owners.values():
        unique = sorted(set(face_owners))
        face_hexes = [index for index in unique if index in hex_ids]
        for left, right in combinations(face_hexes, 2):
            hex_neighbors[left].add(right)
            hex_neighbors[right].add(left)
        if len(unique) == 1 and unique[0] in hex_ids:
            face_virtual_counts[unique[0]] += 1

    score_sum = sum(
        min(6, len(hex_neighbors[index]) + face_virtual_counts[index]) for index in sorted(hex_ids)
    )
    score_che = float(score_sum) / float(6 * len(hex_ids))

    remaining = set(hex_ids)
    cluster_sizes: list[int] = []
    while remaining:
        seed = min(remaining)
        remaining.remove(seed)
        queue: deque[int] = deque([seed])
        size = 0
        while queue:
            current = queue.popleft()
            size += 1
            for neighbor in sorted(hex_neighbors[current]):
                if neighbor in remaining:
                    remaining.remove(neighbor)
                    queue.append(neighbor)
        cluster_sizes.append(size)
    largest = max(cluster_sizes, default=0)
    return score_che, len(cluster_sizes), float(largest) / float(len(hex_ids))


def compute_native_hex_metrics(
    points: np.ndarray,
    cell_faces: CellFaces,
    *,
    beta: float = _DEFAULT_BETA,
) -> NativeHexMetrics:
    """Compute the Phase 0 census, distribution, and beta-margin simulation."""
    pts = np.asarray(points, dtype=np.float64)
    cells = [[[int(vertex) for vertex in face] for face in cell] for cell in cell_faces]
    kinds = [_cell_kind(cell) for cell in cells]
    volumes = _cell_volumes(pts, cells)
    owners = _face_owners(cells)
    neighbors = _local_cell_neighbors(cells, owners)

    counts = {kind: int(sum(cell_kind == kind for cell_kind in kinds)) for kind in _CELL_TYPES}
    total_cells = len(cells)
    count_fractions = {
        kind: float(counts[kind]) / float(total_cells) if total_cells else 0.0
        for kind in _CELL_TYPES
    }
    volume_totals: dict[str, float] = {}
    for kind in _CELL_TYPES:
        indices = [i for i, value in enumerate(kinds) if value == kind]
        volume_totals[kind] = (
            float(volumes[np.asarray(indices, dtype=np.int64)].sum()) if indices else 0.0
        )
    total_volume = float(volumes.sum())
    volume_fractions = {
        kind: volume_totals[kind] / total_volume if total_volume > 0.0 else 0.0
        for kind in _CELL_TYPES
    }

    corner_jacobians: list[float] = []
    local_means: list[float] = []
    margin_ratios: list[float] = []
    for index, cell in enumerate(cells):
        if kinds[index] == "hex" and len({int(v) for f in cell for v in f}) == 8:
            cell_jacobians = _hex_corner_jacobians(pts, cell)
            jacobian = float(np.min(cell_jacobians)) if cell_jacobians.size else 0.0
        else:
            jacobian = _generic_corner_jacobian(pts, cell)
        local_ids = sorted({index, *neighbors[index]})
        local_mean = float(np.mean(volumes[local_ids])) if local_ids else 0.0
        ratio = jacobian / local_mean if local_mean > 0.0 else 0.0
        corner_jacobians.append(jacobian)
        local_means.append(local_mean)
        margin_ratios.append(ratio)

    if corner_jacobians:
        worst_index = int(np.argmin(np.asarray(margin_ratios, dtype=np.float64)))
        min_jacobian = float(corner_jacobians[worst_index])
        worst_local_mean = float(local_means[worst_index])
        min_ratio = float(margin_ratios[worst_index])
        margin = min_jacobian - float(beta) * worst_local_mean
    else:
        min_jacobian = 0.0
        worst_local_mean = 0.0
        min_ratio = 0.0
        margin = 0.0

    score_che, n_clusters, largest_cluster_frac = _hex_distribution(cells, kinds, owners)
    return NativeHexMetrics(
        cell_census=counts,
        cell_count_fractions=count_fractions,
        cell_volume_fractions=volume_fractions,
        cell_volumes=volume_totals,
        total_volume=total_volume,
        score_che=score_che,
        n_hex_clusters=n_clusters,
        largest_cluster_frac=largest_cluster_frac,
        beta=float(beta),
        min_corner_jacobian=min_jacobian,
        local_mean_volume=worst_local_mean,
        beta_margin=margin,
        beta_margin_ratio=min_ratio,
        beta_pass=bool(min_ratio >= float(beta)) if cells else True,
    )


def metrics_log_fields(metrics: NativeHexMetrics) -> dict[str, object]:
    """Flatten the metric object for structlog and result summaries."""
    counts = metrics.cell_census
    count_fractions = metrics.cell_count_fractions
    volume_fractions = metrics.cell_volume_fractions
    return {
        "cell_census": dict(metrics.cell_census),
        "hex_count": counts["hex"],
        "prism_count": counts["prism"],
        "tet_count": counts["tet"],
        "other_count": counts["other"],
        "poly_count": counts["other"],
        "hex_count_fraction": count_fractions["hex"],
        "prism_count_fraction": count_fractions["prism"],
        "tet_count_fraction": count_fractions["tet"],
        "other_count_fraction": count_fractions["other"],
        "hex_volume_fraction": volume_fractions["hex"],
        "prism_volume_fraction": volume_fractions["prism"],
        "tet_volume_fraction": volume_fractions["tet"],
        "other_volume_fraction": volume_fractions["other"],
        "poly_volume_fraction": volume_fractions["other"],
        "cell_count_fractions": dict(metrics.cell_count_fractions),
        "cell_volume_fractions": dict(metrics.cell_volume_fractions),
        "cell_volumes": dict(metrics.cell_volumes),
        "total_volume": metrics.total_volume,
        "score_che": metrics.score_che,
        "n_hex_clusters": metrics.n_hex_clusters,
        "largest_cluster_frac": metrics.largest_cluster_frac,
        "untangle_beta": metrics.beta,
        "untangle_min_corner_jacobian": metrics.min_corner_jacobian,
        "untangle_local_mean_volume": metrics.local_mean_volume,
        "untangle_beta_margin": metrics.beta_margin,
        "untangle_beta_margin_ratio": metrics.beta_margin_ratio,
        "untangle_beta_pass": metrics.beta_pass,
    }
