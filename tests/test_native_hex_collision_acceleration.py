from __future__ import annotations

import numpy as np

from core.layers.native_bl_collision import centroid_overlap_mask
from core.utils.native_extensions import import_native_extension


def _reference(points: np.ndarray, radii: np.ndarray) -> np.ndarray:
    result = np.zeros(len(points), dtype=bool)
    for i, point in enumerate(points):
        for j, other in enumerate(points):
            if i == j:
                continue
            distance = float(np.linalg.norm(point - other))
            if distance > 1.0e-12 and distance < float(radii[i]):
                result[i] = True
                break
    return result


def test_cpp_centroid_overlap_mask_matches_legacy_predicate() -> None:
    points = np.asarray(
        [[0.0, 0.0, 0.0], [0.4, 0.0, 0.0], [2.0, 0.0, 0.0],
         [2.0, 2.0, 2.0], [2.0, 2.0, 2.0]],
        dtype=np.float64,
    )
    radii = np.asarray([0.5, 0.1, 0.2, 0.3, 0.3], dtype=np.float64)
    expected = _reference(points, radii)
    kernel = import_native_extension("native_bl")
    actual = np.asarray(kernel.centroid_overlap_mask(points, radii), dtype=bool)
    assert np.array_equal(actual, expected)
    assert np.array_equal(centroid_overlap_mask(points, radii), expected)


def test_cpp_centroid_overlap_mask_is_deterministic_for_large_sparse_front() -> None:
    points = np.asarray([[float(i), float((i * 17) % 13), 0.0] for i in range(2000)])
    radii = np.full(len(points), 0.25, dtype=np.float64)
    kernel = import_native_extension("native_bl")
    first = np.asarray(kernel.centroid_overlap_mask(points, radii), dtype=bool)
    second = np.asarray(kernel.centroid_overlap_mask(points, radii), dtype=bool)
    assert np.array_equal(first, second)
    assert not first.any()
