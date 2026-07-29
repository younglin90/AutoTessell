"""X3 / beta2725 — mesh anisotropy tensor (eigenvalue based).

각 tet 에서 edge vector 들의 covariance matrix → eigenvalue.
- λ_max / λ_min ratio = anisotropy.
- principal direction = eigenvector of λ_max.

CVT3D / metric tensor / curvature-aligned remesh 의 진단 입력.
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from numpy.typing import NDArray

try:
    from core.generator.native_tet._native import (
        tet_aniso_tensor_batch as _c_tet_aniso_tensor_batch,
    )
except Exception:  # pragma: no cover - native extension optional
    _c_tet_aniso_tensor_batch = None


@dataclass
class AnisoTensorResult:
    n_tets: int = 0
    aniso_min: float = 0.0
    aniso_max: float = 0.0
    aniso_mean: float = 0.0
    aniso_p99: float = 0.0
    n_above_5: int = 0   # ratio > 5 → 매우 anisotropic.
    elapsed_s: float = 0.0


_TET_EDGES = np.array(
    [[0, 1], [0, 2], [0, 3], [1, 2], [1, 3], [2, 3]],
    dtype=np.int64,
)


def tet_aniso_tensor(
    pts: NDArray[np.float64],
    tets: NDArray[np.int64],
) -> tuple[NDArray[np.float64], AnisoTensorResult]:
    """tet 별 anisotropy ratio = sqrt(λ_max / λ_min).

    edge vector cov matrix M (3x3) = (1/6) Σ e_i e_i^T.
    eigenvalue λ_1 ≥ λ_2 ≥ λ_3 ≥ 0.

    Returns:
        (aniso_ratio (T,), AnisoTensorResult).
    """
    import time
    t0 = time.perf_counter()

    pts = np.asarray(pts, dtype=np.float64)
    tets = np.asarray(tets, dtype=np.int64)
    n_t = int(tets.shape[0])

    if n_t == 0:
        return np.zeros(0, dtype=np.float64), AnisoTensorResult(
            elapsed_s=time.perf_counter() - t0,
        )

    if _c_tet_aniso_tensor_batch is not None:
        native = _c_tet_aniso_tensor_batch(pts, tets)
        if native is not None:
            ratio, stats, n_above_5 = native
            return ratio, AnisoTensorResult(
                n_tets=n_t,
                aniso_min=stats[0],
                aniso_max=stats[1],
                aniso_mean=stats[2],
                aniso_p99=stats[3],
                n_above_5=n_above_5,
                elapsed_s=time.perf_counter() - t0,
            )

    # (T, 6, 2) → (T, 6, 3) edge vectors.
    e_idx = tets[:, _TET_EDGES]
    p0 = pts[e_idx[..., 0]]
    p1 = pts[e_idx[..., 1]]
    e_vec = p1 - p0  # (T, 6, 3).

    # covariance: (T, 3, 3) = sum_i e_i e_i^T / 6.
    M = np.einsum("tic,tid->tcd", e_vec, e_vec) / 6.0  # (T, 3, 3).

    # eigenvalues per tet (symmetric).
    eigs = np.linalg.eigvalsh(M)  # (T, 3) ascending.
    lam_min = eigs[:, 0]
    lam_max = eigs[:, 2]
    safe = lam_min > 1e-30
    ratio = np.zeros(n_t, dtype=np.float64)
    ratio[safe] = np.sqrt(lam_max[safe] / lam_min[safe])
    # degenerate cases → big ratio.
    ratio[~safe] = 1e6

    return ratio, AnisoTensorResult(
        n_tets=n_t,
        aniso_min=float(ratio.min()),
        aniso_max=float(ratio.max()),
        aniso_mean=float(ratio.mean()),
        aniso_p99=float(np.percentile(ratio, 99)),
        n_above_5=int((ratio > 5.0).sum()),
        elapsed_s=time.perf_counter() - t0,
    )
