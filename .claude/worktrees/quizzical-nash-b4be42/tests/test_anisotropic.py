"""Round 37 — anisotropic sizing tests."""
from __future__ import annotations

import numpy as np
import pytest


def test_axis_aligned_metric_isotropic() -> None:
    from core.generator.native_tet.anisotropic import (
        axis_aligned_metric, edge_length_metric,
    )

    V = np.array([[0, 0, 0], [1, 0, 0]], dtype=np.float64)
    M = axis_aligned_metric(V, base_edge=1.0)
    # identity 로 scale → edge length 1 인 실제 edge 의 metric length ≈ 1.
    L = edge_length_metric(V[0], V[1], M[0], M[1])
    assert abs(L - 1.0) < 1e-9


def test_axis_aligned_shorter_x() -> None:
    from core.generator.native_tet.anisotropic import (
        axis_aligned_metric, edge_length_metric,
    )

    V = np.array([[0, 0, 0], [1, 0, 0]], dtype=np.float64)
    M = axis_aligned_metric(V, base_edge=1.0, scale_x=0.5)
    # x 방향이 target 0.5 → 실제 1 길이 edge 는 2 × target → metric length ≈ 2.
    L = edge_length_metric(V[0], V[1], M[0], M[1])
    assert abs(L - 2.0) < 1e-9


def test_curvature_aligned_metric_shape() -> None:
    from core.generator.native_tet.anisotropic import curvature_aligned_metric
    import trimesh

    m = trimesh.creation.icosphere(subdivisions=1, radius=1.0)
    V = np.asarray(m.vertices, dtype=np.float64)
    F = np.asarray(m.faces, dtype=np.int64)
    M = curvature_aligned_metric(V, F, base_edge=0.3, aniso_ratio=0.5)
    assert M.shape == (V.shape[0], 3, 3)
    # 각 metric 은 SPD — eigenvalue 모두 > 0.
    for i in range(V.shape[0]):
        eigs = np.linalg.eigvalsh(M[i])
        assert (eigs > 1e-9).all()


def test_edge_lengths_metric_batch() -> None:
    from core.generator.native_tet.anisotropic import (
        axis_aligned_metric, edge_lengths_metric_batch,
    )

    V = np.array(
        [[0, 0, 0], [1, 0, 0], [0, 1, 0]], dtype=np.float64,
    )
    edges = np.array([[0, 1], [0, 2]], dtype=np.int64)
    M = axis_aligned_metric(V, base_edge=1.0)
    L = edge_lengths_metric_batch(V, M, edges)
    assert L.shape == (2,)
    assert np.allclose(L, 1.0)
