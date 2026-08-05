from __future__ import annotations

import numpy as np

from core.generator.native_tet.bounded_steiner import (
    enumerate_bounded_steiner_1to4,
)


def test_bounded_steiner_1to4_uses_exact_positive_children() -> None:
    points = np.asarray(
        [[0.0, 0.0, 0.0], [1.0, 0.0, 0.0], [0.0, 1.0, 0.0], [0.0, 0.0, 1.0]],
        dtype=np.float64,
    )
    tets = np.asarray([[0, 1, 2, 3]], dtype=np.int64)
    candidates = enumerate_bounded_steiner_1to4(
        points, tets, [0], denominator=8, max_candidates=2
    )
    assert len(candidates) == 2
    candidate = candidates[0]
    assert candidate.points.shape == (5, 3)
    assert candidate.tets.shape == (4, 4)
    assert candidate.tets.dtype == np.int64
    assert candidate.parent_tet == 0
    assert sum(candidate.barycentric_weights) == 8
    assert all(value >= 1 for value in candidate.barycentric_weights)
    assert np.array_equal(points, np.asarray([[0, 0, 0], [1, 0, 0], [0, 1, 0], [0, 0, 1]], dtype=np.float64))
