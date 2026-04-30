"""T1 / beta2695 — Surface vertex normal smoothing (1-ring Laplacian).

각 vertex 의 정상값 = area-weighted incident face normal 평균 → smooth.
n_iter 회 반복하여 noisy normal 정규화.
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from numpy.typing import NDArray


@dataclass
class NormalSmoothResult:
    n_vertices: int = 0
    n_iter: int = 0
    elapsed_s: float = 0.0


def compute_vertex_normals(
    V: NDArray[np.float64],
    F: NDArray[np.int64],
) -> NDArray[np.float64]:
    """Area-weighted vertex normals."""
    V = np.asarray(V, dtype=np.float64)
    F = np.asarray(F, dtype=np.int64)
    n = int(V.shape[0])
    vn = np.zeros((n, 3), dtype=np.float64)
    if F.shape[0] == 0:
        return vn

    e1 = V[F[:, 1]] - V[F[:, 0]]
    e2 = V[F[:, 2]] - V[F[:, 0]]
    fn = np.cross(e1, e2)  # area × 2 normal.

    # scatter into vertex normals.
    np.add.at(vn, F[:, 0], fn)
    np.add.at(vn, F[:, 1], fn)
    np.add.at(vn, F[:, 2], fn)

    # normalize.
    norms = np.linalg.norm(vn, axis=1, keepdims=True)
    safe = norms[:, 0] > 1e-30
    out = np.zeros_like(vn)
    out[safe] = vn[safe] / norms[safe]
    return out


def smooth_vertex_normals(
    V: NDArray[np.float64],
    F: NDArray[np.int64],
    *,
    n_iter: int = 3,
) -> tuple[NDArray[np.float64], NormalSmoothResult]:
    """1-ring Laplacian smoothing of vertex normals.

    Args:
        V: (N, 3) coords.
        F: (M, 3) tri indices.
        n_iter: smoothing iterations.

    Returns:
        (smoothed_normals (N, 3), NormalSmoothResult).
    """
    import time
    t0 = time.perf_counter()

    V = np.asarray(V, dtype=np.float64)
    F = np.asarray(F, dtype=np.int64)
    n = int(V.shape[0])

    if n == 0 or F.shape[0] == 0:
        return np.zeros((n, 3), dtype=np.float64), NormalSmoothResult(
            n_vertices=n, n_iter=0,
            elapsed_s=time.perf_counter() - t0,
        )

    vn = compute_vertex_normals(V, F)

    # 1-ring neighbor sum 를 face edges 로 빌드.
    edges = np.stack([
        F[:, [0, 1]], F[:, [1, 2]], F[:, [2, 0]],
        F[:, [1, 0]], F[:, [2, 1]], F[:, [0, 2]],
    ], axis=1).reshape(-1, 2)

    for _ in range(int(n_iter)):
        nbr_sum = np.zeros((n, 3), dtype=np.float64)
        nbr_cnt = np.zeros(n, dtype=np.int64)
        np.add.at(nbr_sum, edges[:, 0], vn[edges[:, 1]])
        np.add.at(nbr_cnt, edges[:, 0], 1)
        nz = nbr_cnt > 0
        new_vn = np.zeros_like(vn)
        # weighted: 0.5 × self + 0.5 × neighbor avg.
        new_vn[nz] = (
            0.5 * vn[nz]
            + 0.5 * (nbr_sum[nz] / nbr_cnt[nz, None])
        )
        # renormalize.
        norms = np.linalg.norm(new_vn, axis=1, keepdims=True)
        safe = norms[:, 0] > 1e-30
        new_vn[safe] = new_vn[safe] / norms[safe]
        vn = new_vn

    return vn, NormalSmoothResult(
        n_vertices=n,
        n_iter=int(n_iter),
        elapsed_s=time.perf_counter() - t0,
    )
