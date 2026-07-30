"""Geometry-derived sparse provenance refresh, report-only and deterministic."""

from __future__ import annotations

import numpy as np

from .sparse_leaf_partition_l0 import SparseLeafKey
from .sparse_partition_provenance_l1 import SparseProvenanceLeaf


def _leaf_bounds(key: SparseLeafKey, root_min: np.ndarray, target_edge: float) -> tuple[np.ndarray, np.ndarray]:
    edge = target_edge / (1 << key.level)
    lower = root_min + edge * np.asarray((key.i, key.j, key.k), dtype=np.float64)
    return lower, lower + edge


def _triangle_intersects_bounds(triangle: np.ndarray, lower: np.ndarray, upper: np.ndarray) -> bool:
    """Conservative AABB overlap; uncertainty remains ``surface``."""
    return bool(np.all(triangle.max(axis=0) >= lower) and np.all(triangle.min(axis=0) <= upper))


def classify_sparse_mesh_leaf_keys(
    keys: tuple[SparseLeafKey, ...], vertices: np.ndarray, faces: np.ndarray, *, root_min: np.ndarray, target_edge: float
) -> tuple[SparseProvenanceLeaf, ...]:
    """Classify fresh leaves from triangle geometry, never inherited parent labels.

    Surface overlap is deliberately conservative.  Non-overlapping leaves are
    ``outside`` because this report-only primitive has no closed-solid proof.
    """
    points = np.asarray(vertices, dtype=np.float64)
    triangles = np.asarray(faces, dtype=np.int64)
    lower = np.asarray(root_min, dtype=np.float64)
    if points.ndim != 2 or points.shape[1] != 3 or triangles.ndim != 2 or triangles.shape[1] != 3:
        raise ValueError("vertices must be (n, 3) and faces must be (m, 3)")
    if lower.shape != (3,) or not np.isfinite(points).all() or not np.isfinite(lower).all() or target_edge <= 0.0:
        raise ValueError("geometry and root bounds must be finite and target edge positive")
    if len(triangles) and (triangles.min() < 0 or triangles.max() >= len(points)):
        raise ValueError("faces must index vertices")
    soup = points[triangles]
    classified: list[SparseProvenanceLeaf] = []
    for key in sorted(keys):
        box_lower, box_upper = _leaf_bounds(key, lower, target_edge)
        provenance = "surface" if any(_triangle_intersects_bounds(triangle, box_lower, box_upper) for triangle in soup) else "outside"
        classified.append(SparseProvenanceLeaf(key, provenance))
    return tuple(classified)
