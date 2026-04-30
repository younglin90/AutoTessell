"""S3 / beta2690 — Cell quality delta tracker (before/after mesh op).

mesh op (smoothing / swap / split) 전후 의 cell quality 변화 정량.
사용처: AMIPS smoothing 효과 측정, ML smoothing 검증, P4D fallback 비교.
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from numpy.typing import NDArray


@dataclass
class QualityDeltaResult:
    n_cells_pre: int = 0
    n_cells_post: int = 0
    min_q_pre: float = 0.0
    min_q_post: float = 0.0
    mean_q_pre: float = 0.0
    mean_q_post: float = 0.0
    delta_min: float = 0.0
    delta_mean: float = 0.0
    n_improved: int = 0       # cell 단위 (pre/post tet topology 동일 시).
    n_degraded: int = 0
    n_unchanged: int = 0
    elapsed_s: float = 0.0


def _vectorized_tet_quality(pts: np.ndarray, tets: np.ndarray) -> np.ndarray:
    if tets.size == 0:
        return np.zeros(0, dtype=np.float64)
    p0 = pts[tets[:, 0]]; p1 = pts[tets[:, 1]]
    p2 = pts[tets[:, 2]]; p3 = pts[tets[:, 3]]
    e0 = p1 - p0; e1 = p2 - p0; e2 = p3 - p0
    e3 = p2 - p1; e4 = p3 - p1; e5 = p3 - p2
    e_sq = (
        (e0 ** 2).sum(1) + (e1 ** 2).sum(1) + (e2 ** 2).sum(1)
        + (e3 ** 2).sum(1) + (e4 ** 2).sum(1) + (e5 ** 2).sum(1)
    )
    vol6 = (np.cross(e1, e2) * e0).sum(1)
    vol = np.abs(vol6) / 6.0
    return np.where(
        e_sq > 1e-30,
        np.clip(12.0 * ((3.0 * vol) ** (2.0 / 3.0)) / e_sq, 0.0, 1.0),
        0.0,
    )


def compute_quality_delta(
    pts_pre: NDArray[np.float64],
    tets_pre: NDArray[np.int64],
    pts_post: NDArray[np.float64],
    tets_post: NDArray[np.int64],
    *,
    eps_unchanged: float = 1e-6,
) -> QualityDeltaResult:
    """Pre/Post cell quality 비교.

    topology 가 동일 (tets_pre.shape == tets_post.shape) 이면 per-cell delta
    계산 (n_improved/n_degraded/n_unchanged). 다르면 aggregate 만 비교.
    """
    import time
    t0 = time.perf_counter()

    qs_pre = _vectorized_tet_quality(np.asarray(pts_pre, np.float64),
                                      np.asarray(tets_pre, np.int64))
    qs_post = _vectorized_tet_quality(np.asarray(pts_post, np.float64),
                                       np.asarray(tets_post, np.int64))

    n_pre = int(qs_pre.size)
    n_post = int(qs_post.size)

    min_pre = float(qs_pre.min()) if n_pre > 0 else 0.0
    min_post = float(qs_post.min()) if n_post > 0 else 0.0
    mean_pre = float(qs_pre.mean()) if n_pre > 0 else 0.0
    mean_post = float(qs_post.mean()) if n_post > 0 else 0.0

    n_imp = n_deg = n_same = 0
    if n_pre == n_post and n_pre > 0:
        delta = qs_post - qs_pre
        n_imp = int((delta > eps_unchanged).sum())
        n_deg = int((delta < -eps_unchanged).sum())
        n_same = int((np.abs(delta) <= eps_unchanged).sum())

    return QualityDeltaResult(
        n_cells_pre=n_pre, n_cells_post=n_post,
        min_q_pre=min_pre, min_q_post=min_post,
        mean_q_pre=mean_pre, mean_q_post=mean_post,
        delta_min=min_post - min_pre,
        delta_mean=mean_post - mean_pre,
        n_improved=n_imp, n_degraded=n_deg, n_unchanged=n_same,
        elapsed_s=time.perf_counter() - t0,
    )
