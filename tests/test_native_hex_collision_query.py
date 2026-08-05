from __future__ import annotations

import numpy as np

from core.layers.native_bl_collision import query_centroid_overlap_mask
from core.utils.native_extensions import import_native_extension


def test_cpp_query_collision_matches_wall_centroid_predicate() -> None:
    queries = np.asarray(
        [[0.0, 0.0, 0.0], [2.0, 0.0, 0.0], [4.0, 0.0, 0.0]],
        dtype=np.float64,
    )
    radii = np.asarray([0.6, 0.2, 0.6], dtype=np.float64)
    sources = np.asarray([[0.4, 0.0, 0.0], [2.0, 0.0, 0.0]], dtype=np.float64)
    expected = np.asarray([True, False, False], dtype=bool)
    kernel = import_native_extension("native_bl")
    actual = np.asarray(
        kernel.centroid_query_overlap_mask(queries, radii, sources), dtype=bool
    )
    assert np.array_equal(actual, expected)
    assert np.array_equal(query_centroid_overlap_mask(queries, radii, sources), expected)


def test_cpp_query_collision_is_deterministic_for_large_wall_front() -> None:
    queries = np.asarray([[float(i), float(i % 17), 0.1] for i in range(3000)])
    radii = np.full(len(queries), 0.3, dtype=np.float64)
    sources = np.asarray([[float(i), float(i % 17), 0.0] for i in range(3000)])
    kernel = import_native_extension("native_bl")
    first = np.asarray(
        kernel.centroid_query_overlap_mask(queries, radii, sources), dtype=bool
    )
    second = np.asarray(
        kernel.centroid_query_overlap_mask(queries, radii, sources), dtype=bool
    )
    assert np.array_equal(first, second)
    assert first.all()
