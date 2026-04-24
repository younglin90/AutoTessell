"""R134 — Hausdorff vs 입력 surface."""
from __future__ import annotations

import numpy as np


def test_hausdorff_zero_when_identical() -> None:
    """결과 boundary 가 입력과 동일하면 Hausdorff ≈ 0."""
    from core.generator.native_tet.hausdorff import hausdorff_vs_input

    V = np.array([[0, 0, 0], [1, 0, 0], [0, 1, 0], [0, 0, 1]], dtype=np.float64)
    F = np.array([[0, 1, 2], [0, 1, 3], [0, 2, 3], [1, 2, 3]], dtype=np.int64)
    tets = np.array([[0, 1, 2, 3]], dtype=np.int64)
    r = hausdorff_vs_input(V, F, V, tets, n_samples_per_tri=3)
    assert r.h_symmetric < 1e-9
    assert r.mean_forward < 1e-9


def test_hausdorff_scales_with_offset() -> None:
    """결과 mesh 를 0.1 shift 하면 Hausdorff ≈ 0.1."""
    from core.generator.native_tet.hausdorff import hausdorff_vs_input

    V = np.array([[0, 0, 0], [1, 0, 0], [0, 1, 0], [0, 0, 1]], dtype=np.float64)
    F = np.array([[0, 1, 2], [0, 1, 3], [0, 2, 3], [1, 2, 3]], dtype=np.int64)
    tets = np.array([[0, 1, 2, 3]], dtype=np.int64)
    V_shift = V + np.array([0.1, 0, 0])
    r = hausdorff_vs_input(V, F, V_shift, tets, n_samples_per_tri=3)
    # 0.0 < h < 0.2 정도.
    assert r.h_symmetric > 1e-3
    assert r.h_symmetric < 0.2
