"""C++-first broad-phase predicates for native wall-layer guards."""

from __future__ import annotations

import numpy as np

from core.utils.native_extensions import load_native_bl


def centroid_overlap_mask(points: list[np.ndarray], radii: list[float]) -> np.ndarray:
    """Return the legacy asymmetric overlap predicate in deterministic order."""
    coordinates = np.ascontiguousarray(np.asarray(points, dtype=np.float64))
    values = np.ascontiguousarray(np.asarray(radii, dtype=np.float64))
    kernel = load_native_bl()
    if kernel is not None and hasattr(kernel, "centroid_overlap_mask"):
        return np.asarray(kernel.centroid_overlap_mask(coordinates, values), dtype=bool)
    result = np.zeros(len(coordinates), dtype=bool)
    for index, point in enumerate(coordinates):
        for other_index, other in enumerate(coordinates):
            if index == other_index:
                continue
            distance = float(np.linalg.norm(point - other))
            if distance > 1.0e-12 and distance < float(values[index]):
                result[index] = True
                break
    return result


def query_centroid_overlap_mask(
    query_points: list[np.ndarray],
    radii: list[float],
    source_points: list[np.ndarray],
) -> np.ndarray:
    """Return the legacy query-against-wall-centroid collision predicate."""
    queries = np.ascontiguousarray(np.asarray(query_points, dtype=np.float64))
    values = np.ascontiguousarray(np.asarray(radii, dtype=np.float64))
    sources = np.ascontiguousarray(np.asarray(source_points, dtype=np.float64))
    kernel = load_native_bl()
    if kernel is not None and hasattr(kernel, "centroid_query_overlap_mask"):
        return np.asarray(
            kernel.centroid_query_overlap_mask(queries, values, sources),
            dtype=bool,
        )
    result = np.zeros(len(queries), dtype=bool)
    for index, point in enumerate(queries):
        for other in sources:
            distance = float(np.linalg.norm(point - other))
            if distance > 1.0e-12 and distance < float(values[index]):
                result[index] = True
                break
    return result
