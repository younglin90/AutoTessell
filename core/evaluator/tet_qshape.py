"""V1 / beta2709 — Tet Q-shape (Klingner-like aspect quality).

Q_shape = 12 * (3*V)^(2/3) / (sum_i L_i^2)
   regular tet 에서 Q ≈ 1, degenerate 시 Q → 0.

Klingner 2007, "Aggressive Tetrahedral Mesh Improvement", Eq. (2) 변형.
빠른 quality 분포 측정 + Evaluator pre-check.
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from numpy.typing import NDArray

try:
    from core.generator.native_tet._native import tet_qshape_batch as _c_tet_qshape_batch
except Exception:  # pragma: no cover - optional native extension
    _c_tet_qshape_batch = None


@dataclass
class TetQShapeResult:
    n_tets: int = 0
    q_min: float = 0.0
    q_max: float = 0.0
    q_mean: float = 0.0
    q_p01: float = 0.0
    q_p99: float = 0.0
    n_below_0p3: int = 0   # poor
    n_below_0p1: int = 0   # very poor / sliver
    elapsed_s: float = 0.0


_TET_EDGES = np.array(
    [[0, 1], [0, 2], [0, 3], [1, 2], [1, 3], [2, 3]],
    dtype=np.int64,
)


def tet_qshape(
    pts: NDArray[np.float64],
    tets: NDArray[np.int64],
) -> tuple[NDArray[np.float64], TetQShapeResult]:
    """tet 별 Q_shape ∈ [0, 1].

    Returns:
        (Q array (T,), TetQShapeResult).
    """
    import time
    t0 = time.perf_counter()

    pts = np.asarray(pts, dtype=np.float64)
    tets = np.asarray(tets, dtype=np.int64)
    n_t = int(tets.shape[0])

    if n_t == 0:
        return np.zeros(0, dtype=np.float64), TetQShapeResult(
            elapsed_s=time.perf_counter() - t0,
        )

    Q = None
    if _c_tet_qshape_batch is not None:
        Q = _c_tet_qshape_batch(pts, tets)

    if Q is None:
        a = pts[tets[:, 0]]
        b = pts[tets[:, 1]]
        c = pts[tets[:, 2]]
        d = pts[tets[:, 3]]
        vol = np.einsum("ij,ij->i", np.cross(b - a, c - a), d - a) / 6.0
        abs_vol = np.abs(vol)

        e_idx = tets[:, _TET_EDGES]
        p0 = pts[e_idx[..., 0]]
        p1 = pts[e_idx[..., 1]]
        e_lens_sq = ((p1 - p0) ** 2).sum(axis=-1)  # (T, 6).
        sum_l_sq = e_lens_sq.sum(axis=1)

        safe = sum_l_sq > 1e-30
        Q = np.zeros(n_t, dtype=np.float64)
        # constant: 12 * (3)^(2/3) ≈ 12 * 2.0801 = 24.96 — but normalize so regular = 1.
        # regular tet edge=1: V = sqrt(2)/12, sum L_sq = 6.
        # raw = (3V)^(2/3) / sum L_sq = (sqrt(2)/4)^(2/3) / 6 = 0.0857
        # 그래서 Q = raw / 0.0857 → regular = 1.
        raw = np.zeros(n_t, dtype=np.float64)
        raw[safe] = (3.0 * abs_vol[safe]) ** (2.0 / 3.0) / sum_l_sq[safe]
        Q = raw / 0.0857  # regular = 1.
        Q = np.clip(Q, 0.0, 1.0)
        # inverted tets → 0.
        Q[vol <= 0] = 0.0

    return Q, TetQShapeResult(
        n_tets=n_t,
        q_min=float(Q.min()),
        q_max=float(Q.max()),
        q_mean=float(Q.mean()),
        q_p01=float(np.percentile(Q, 1)),
        q_p99=float(np.percentile(Q, 99)),
        n_below_0p3=int((Q < 0.3).sum()),
        n_below_0p1=int((Q < 0.1).sum()),
        elapsed_s=time.perf_counter() - t0,
    )
