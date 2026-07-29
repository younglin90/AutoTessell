"""Report-only sampled surface-contract audit for a sparse selected volume.

The closed-volume proof alone says nothing about preserving the input surface.
This audit measures both candidate-boundary-to-source and source-to-candidate
distances.  It deliberately does not turn finite samples into an exact surface
identity claim, and is disconnected from mesh generation and writing.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass

import numpy as np

from core.utils.aabb import TriangleBVH

from .sparse_closed_volume_l3 import _tile_corners
from .sparse_leaf_partition_l0 import _leaf_faces
from .sparse_partition_provenance_l1 import SparseProvenanceLeaf


@dataclass(frozen=True)
class SparseSurfaceContractReport:
    """One-sided and reverse sampled distances for a selected sparse boundary."""

    status: str
    boundary_face_tiles: int
    candidate_probe_count: int
    source_probe_count: int
    candidate_to_source_max: float
    candidate_to_source_mean: float
    source_to_candidate_max: float
    source_to_candidate_mean: float
    tolerance: float
    sampled_coincident: bool
    strict_surface_contract_proven: bool
    production_octree_changed: bool


def _selected_boundary_tiles(
    leaves: tuple[SparseProvenanceLeaf, ...], *, max_level: int
) -> tuple[tuple[int, int, int, int], ...]:
    owners: dict[tuple[int, int, int, int], int] = defaultdict(int)
    for item in leaves:
        if item.provenance not in {"inside", "surface"}:
            continue
        for side in _leaf_faces(item.key, max_level=max_level):
            for tile in side:
                owners[tile] += 1
    return tuple(sorted(tile for tile, count in owners.items() if count == 1))


def audit_sparse_selected_surface_contract(
    leaves: tuple[SparseProvenanceLeaf, ...],
    vertices: np.ndarray,
    faces: np.ndarray,
    *,
    root_min: np.ndarray,
    target_edge: float,
    max_level: int,
    tolerance: float,
) -> SparseSurfaceContractReport:
    """Measure sampled geometric coincidence without claiming exact identity."""
    points = np.asarray(vertices, dtype=np.float64)
    triangles = np.asarray(faces, dtype=np.int64)
    lower = np.asarray(root_min, dtype=np.float64)
    if points.ndim != 2 or points.shape[1] != 3 or triangles.shape[1:] != (3,):
        raise ValueError("vertices must be (n, 3) and faces must be triangular")
    if lower.shape != (3,) or target_edge <= 0.0 or max_level < 0 or tolerance < 0.0:
        raise ValueError("root, edge, depth, and tolerance must be valid")
    tiles = _selected_boundary_tiles(leaves, max_level=max_level)
    if not tiles:
        return SparseSurfaceContractReport(
            status="reject_empty_selected_boundary",
            boundary_face_tiles=0,
            candidate_probe_count=0,
            source_probe_count=0,
            candidate_to_source_max=float("inf"),
            candidate_to_source_mean=float("inf"),
            source_to_candidate_max=float("inf"),
            source_to_candidate_mean=float("inf"),
            tolerance=tolerance,
            sampled_coincident=False,
            strict_surface_contract_proven=False,
            production_octree_changed=False,
        )
    scale = target_edge / (1 << max_level)
    corner_ids: dict[tuple[int, int, int], int] = {}
    boundary_vertices: list[np.ndarray] = []
    boundary_triangles: list[tuple[int, int, int]] = []
    centers: list[np.ndarray] = []
    for tile in tiles:
        ids: list[int] = []
        corners = _tile_corners(tile)
        for corner in corners:
            if corner not in corner_ids:
                corner_ids[corner] = len(boundary_vertices)
                boundary_vertices.append(lower + scale * np.asarray(corner, dtype=np.float64))
            ids.append(corner_ids[corner])
        boundary_triangles.extend(((ids[0], ids[1], ids[2]), (ids[0], ids[2], ids[3])))
        centers.append(np.mean([boundary_vertices[index] for index in ids], axis=0))
    candidate_vertices = np.asarray(boundary_vertices, dtype=np.float64)
    candidate_faces = np.asarray(boundary_triangles, dtype=np.int64)
    candidate_probes = np.vstack((candidate_vertices, np.asarray(centers, dtype=np.float64)))
    source_probes = np.vstack((points, points[triangles].mean(axis=1)))
    source_bvh = TriangleBVH.build(points, triangles)
    candidate_bvh = TriangleBVH.build(candidate_vertices, candidate_faces)
    candidate_distances = source_bvh.unsigned_distances(candidate_probes)
    source_distances = candidate_bvh.unsigned_distances(source_probes)
    candidate_max = float(candidate_distances.max(initial=0.0))
    source_max = float(source_distances.max(initial=0.0))
    coincident = candidate_max <= tolerance and source_max <= tolerance
    return SparseSurfaceContractReport(
        status=(
            "pass_sampled_surface_coincidence" if coincident else "reject_sampled_surface_deviation"
        ),
        boundary_face_tiles=len(tiles),
        candidate_probe_count=len(candidate_probes),
        source_probe_count=len(source_probes),
        candidate_to_source_max=candidate_max,
        candidate_to_source_mean=float(candidate_distances.mean()),
        source_to_candidate_max=source_max,
        source_to_candidate_mean=float(source_distances.mean()),
        tolerance=tolerance,
        sampled_coincident=coincident,
        strict_surface_contract_proven=False,
        production_octree_changed=False,
    )
