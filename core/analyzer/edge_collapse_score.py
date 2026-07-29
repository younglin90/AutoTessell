"""DD1 / beta2785 — tet edge collapse score (Klingner §3.2 priority).

각 short edge 의 "collapse 후 quality 향상 기대값" priority score 산출.
Stellar __apply_klingner_edge_contract_topK 의 입력 정렬 보조.

알고리즘:
    1. tet 별 6 edge length, shortest edge 추출.
    2. edge 양 끝의 incident tet 수 + worst Q (1-ring star).
    3. score = (1 - worst_Q) * (1 / edge_length) * (1 / max(incident_tets, 1))
       높을수록 collapse 효과 큼.
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from numpy.typing import NDArray

try:
    from core.generator.native_tet._native import (
        edge_collapse_priority_batch as _c_edge_collapse_priority_batch,
    )
except Exception:  # pragma: no cover - optional native extension
    _c_edge_collapse_priority_batch = None


@dataclass
class CollapseScoreResult:
    n_candidates: int = 0
    score_max: float = 0.0
    score_median: float = 0.0
    elapsed_s: float = 0.0


_TET_EDGES = np.array(
    [[0, 1], [0, 2], [0, 3], [1, 2], [1, 3], [2, 3]],
    dtype=np.int64,
)


def edge_collapse_priority(
    pts: NDArray[np.float64],
    tets: NDArray[np.int64],
    *,
    q_threshold: float = 0.3,
    top_k: int = 100,
) -> tuple[NDArray[np.int64], NDArray[np.float64], CollapseScoreResult]:
    """priority score 기반 collapse 후보 정렬.

    Returns:
        (edges (k, 2) sorted desc, scores (k,), result).
    """
    import time
    t0 = time.perf_counter()

    pts = np.asarray(pts, dtype=np.float64)
    tets = np.asarray(tets, dtype=np.int64)
    n_t = int(tets.shape[0])

    if n_t == 0:
        return (
            np.zeros((0, 2), dtype=np.int64),
            np.zeros(0, dtype=np.float64),
            CollapseScoreResult(elapsed_s=time.perf_counter() - t0),
        )

    from core.evaluator.tet_qshape import tet_qshape
    Q, _ = tet_qshape(pts, tets)

    native_priority = (
        _c_edge_collapse_priority_batch(pts, tets, Q, q_threshold, top_k)
        if _c_edge_collapse_priority_batch is not None
        else None
    )
    if native_priority is not None:
        edges_arr, scores_arr = native_priority
        if edges_arr.shape[0] == 0:
            return (
                np.zeros((0, 2), dtype=np.int64),
                np.zeros(0, dtype=np.float64),
                CollapseScoreResult(elapsed_s=time.perf_counter() - t0),
            )
        return edges_arr, scores_arr, CollapseScoreResult(
            n_candidates=int(edges_arr.shape[0]),
            score_max=float(scores_arr[0]),
            score_median=float(np.median(scores_arr)),
            elapsed_s=time.perf_counter() - t0,
        )

    # tet 의 6 edge.
    e_idx = tets[:, _TET_EDGES]  # (T, 6, 2).
    p0 = pts[e_idx[..., 0]]
    p1 = pts[e_idx[..., 1]]
    e_len = np.linalg.norm(p1 - p0, axis=-1)  # (T, 6).

    # edge → list (canonical: u<v).
    flat_e = e_idx.reshape(-1, 2)
    flat_l = e_len.reshape(-1)
    flat_t = np.repeat(np.arange(n_t, dtype=np.int64), 6)
    e_can = np.sort(flat_e, axis=1)
    keys = e_can[:, 0] * (1 << 32) + e_can[:, 1]
    sort_idx = np.argsort(keys)
    keys_s = keys[sort_idx]
    e_s = e_can[sort_idx]
    l_s = flat_l[sort_idx]
    t_s = flat_t[sort_idx]

    edges_out: list[tuple[int, int]] = []
    scores_out: list[float] = []

    n_e = keys_s.shape[0]
    i = 0
    while i < n_e:
        j = i
        while j < n_e and keys_s[j] == keys_s[i]:
            j += 1
        cnt = j - i
        worst_q = float(Q[t_s[i:j]].min())
        if worst_q < q_threshold:
            edge_len = float(l_s[i])  # all same edge.
            denom = max(edge_len, 1e-30) * max(cnt, 1)
            score = (1.0 - worst_q) / denom
            edges_out.append((int(e_s[i, 0]), int(e_s[i, 1])))
            scores_out.append(score)
        i = j

    if not edges_out:
        return (
            np.zeros((0, 2), dtype=np.int64),
            np.zeros(0, dtype=np.float64),
            CollapseScoreResult(elapsed_s=time.perf_counter() - t0),
        )

    edges_arr = np.array(edges_out, dtype=np.int64)
    scores_arr = np.array(scores_out, dtype=np.float64)
    order = np.argsort(-scores_arr)
    edges_arr = edges_arr[order][:top_k]
    scores_arr = scores_arr[order][:top_k]

    return edges_arr, scores_arr, CollapseScoreResult(
        n_candidates=int(edges_arr.shape[0]),
        score_max=float(scores_arr[0]),
        score_median=float(np.median(scores_arr)),
        elapsed_s=time.perf_counter() - t0,
    )
