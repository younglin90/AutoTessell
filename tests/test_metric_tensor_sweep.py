from __future__ import annotations

import numpy as np


def test_metric_sweep_rejects_duplicate_face_candidate() -> None:
    from core.generator.native_tet.metric_tensor_sweep import metric_tensor_sweep

    rng = np.random.RandomState(7)
    from scipy.spatial import Delaunay
    points = rng.rand(24, 3)
    tets = Delaunay(points).simplices.astype(np.int64)
    invalid = np.vstack([tets, tets[:1]])
    out_points, out_tets, result = metric_tensor_sweep(points, invalid, n_cycles=1)
    assert not result.accepted
    assert result.reason == "strict_writer_topology_rejected"
    assert np.array_equal(out_points, points)
    assert np.array_equal(out_tets, invalid)
    assert result.n_collapse == result.n_split == result.n_flip == result.n_smooth == 0
