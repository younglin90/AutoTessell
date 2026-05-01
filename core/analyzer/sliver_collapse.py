"""AA1 / beta2744 — tet sliver edge-collapse candidate detector.

각 sliver tet 의 가장 짧은 edge (collapse 후보) 식별.
- shortest edge collapse → tet 제거 + vertex pair 병합.
- 너무 긴 edge 는 collapse 부적합 (mesh 변경 큼).

Klingner 2008 §3.2 sliver removal pre-screen.
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from numpy.typing import NDArray


@dataclass
class SliverCollapseResult:
    n_sliver_tets: int = 0
    n_collapse_candidates: int = 0
    median_short_edge: float = 0.0
    elapsed_s: float = 0.0


_TET_EDGES = np.array(
    [[0, 1], [0, 2], [0, 3], [1, 2], [1, 3], [2, 3]],
    dtype=np.int64,
)


def detect_sliver_collapse_edges(
    pts: NDArray[np.float64],
    tets: NDArray[np.int64],
    *,
    sliver_q_threshold: float = 0.1,
    max_collapse_edge: float | None = None,
) -> tuple[NDArray[np.int64], SliverCollapseResult]:
    """sliver tet 의 shortest edge 추출 → collapse 후보.

    Args:
        pts: (N, 3).
        tets: (T, 4).
        sliver_q_threshold: Q < threshold 인 tet 만 대상.
        max_collapse_edge: edge length 가 이 값 초과면 후보 제외 (None = no limit).

    Returns:
        (collapse_edges (k, 2), SliverCollapseResult).
    """
    import time
    t0 = time.perf_counter()

    pts = np.asarray(pts, dtype=np.float64)
    tets = np.asarray(tets, dtype=np.int64)
    n_t = int(tets.shape[0])

    if n_t == 0:
        return np.zeros((0, 2), dtype=np.int64), SliverCollapseResult(
            elapsed_s=time.perf_counter() - t0,
        )

    from core.evaluator.tet_qshape import tet_qshape
    Q, _ = tet_qshape(pts, tets)

    sliver_mask = Q < sliver_q_threshold
    n_sliver = int(sliver_mask.sum())
    if n_sliver == 0:
        return np.zeros((0, 2), dtype=np.int64), SliverCollapseResult(
            elapsed_s=time.perf_counter() - t0,
        )

    # 각 tet 의 6 edge length, shortest edge 인덱스.
    e_idx = tets[:, _TET_EDGES]  # (T, 6, 2).
    p0 = pts[e_idx[..., 0]]
    p1 = pts[e_idx[..., 1]]
    e_lens = np.linalg.norm(p1 - p0, axis=-1)  # (T, 6).

    short_edge_local = e_lens.argmin(axis=1)  # (T,) 0..5.
    short_edge_len = e_lens[np.arange(n_t), short_edge_local]

    short_edges = np.zeros((n_t, 2), dtype=np.int64)
    for k in range(n_t):
        short_edges[k] = e_idx[k, short_edge_local[k]]

    keep = sliver_mask
    if max_collapse_edge is not None:
        keep = keep & (short_edge_len <= max_collapse_edge)

    out = short_edges[keep]
    out_lens = short_edge_len[keep]
    median_short = float(np.median(out_lens)) if out.shape[0] > 0 else 0.0

    return out, SliverCollapseResult(
        n_sliver_tets=n_sliver,
        n_collapse_candidates=int(out.shape[0]),
        median_short_edge=median_short,
        elapsed_s=time.perf_counter() - t0,
    )
