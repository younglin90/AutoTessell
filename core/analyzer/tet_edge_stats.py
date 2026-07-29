"""U1 / beta2702 — Tet edge length statistics + anisotropy.

각 tet 의 6 edge length 분포 → mesh anisotropy / sliver tendency 진단.
- min/max/mean edge length
- edge length ratio (max/min) per tet
- volume vs edge^3 ratio (regular tet ≈ 0.118)

ML feature 보강 입력 + sliver 탐지 utility.
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from numpy.typing import NDArray

try:
    from core.generator.native_tet._native import (
        tet_edge_stats_batch as _c_tet_edge_stats_batch,
    )
except Exception:  # pragma: no cover - native extension optional
    _c_tet_edge_stats_batch = None


@dataclass
class TetEdgeStatsResult:
    n_tets: int = 0
    edge_min: float = 0.0
    edge_max: float = 0.0
    edge_mean: float = 0.0
    edge_p99: float = 0.0  # 99th percentile.
    aniso_max: float = 0.0  # max edge ratio over all tets.
    aniso_mean: float = 0.0
    n_sliver: int = 0  # tet 들 중 aniso_ratio > 10.
    elapsed_s: float = 0.0


_TET_EDGES = np.array(
    [[0, 1], [0, 2], [0, 3], [1, 2], [1, 3], [2, 3]],
    dtype=np.int64,
)


def tet_edge_stats(
    pts: NDArray[np.float64],
    tets: NDArray[np.int64],
    *,
    sliver_aniso: float = 10.0,
) -> TetEdgeStatsResult:
    """tet edge length 통계 + sliver detector.

    Args:
        pts: (N, 3).
        tets: (T, 4).
        sliver_aniso: aniso ratio 이 값보다 크면 sliver 카운트.

    Returns:
        TetEdgeStatsResult.
    """
    import time
    t0 = time.perf_counter()

    pts = np.asarray(pts, dtype=np.float64)
    tets = np.asarray(tets, dtype=np.int64)
    n_t = int(tets.shape[0])

    if n_t == 0:
        return TetEdgeStatsResult(elapsed_s=time.perf_counter() - t0)

    if _c_tet_edge_stats_batch is not None:
        native = _c_tet_edge_stats_batch(pts, tets, sliver_aniso)
        if native is not None:
            stats, n_sliver = native
            return TetEdgeStatsResult(
                n_tets=n_t,
                edge_min=stats[0],
                edge_max=stats[1],
                edge_mean=stats[2],
                edge_p99=stats[3],
                aniso_max=stats[4],
                aniso_mean=stats[5],
                n_sliver=n_sliver,
                elapsed_s=time.perf_counter() - t0,
            )

    # (T, 6, 2) edge index → (T, 6) length.
    e_idx = tets[:, _TET_EDGES]  # (T, 6, 2).
    p0 = pts[e_idx[..., 0]]
    p1 = pts[e_idx[..., 1]]
    edge_len = np.linalg.norm(p1 - p0, axis=-1)  # (T, 6).

    e_flat = edge_len.reshape(-1)
    e_min_per_t = edge_len.min(axis=1)
    e_max_per_t = edge_len.max(axis=1)
    safe = e_min_per_t > 1e-30
    aniso = np.zeros(n_t, dtype=np.float64)
    aniso[safe] = e_max_per_t[safe] / e_min_per_t[safe]

    n_sliver = int((aniso > sliver_aniso).sum())

    return TetEdgeStatsResult(
        n_tets=n_t,
        edge_min=float(e_flat.min()),
        edge_max=float(e_flat.max()),
        edge_mean=float(e_flat.mean()),
        edge_p99=float(np.percentile(e_flat, 99)),
        aniso_max=float(aniso.max()),
        aniso_mean=float(aniso.mean()),
        n_sliver=n_sliver,
        elapsed_s=time.perf_counter() - t0,
    )
