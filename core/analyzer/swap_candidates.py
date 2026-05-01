"""Z1 / beta2737 — tet edge swap candidate pre-screen.

각 internal edge (e_v0, e_v1) 의 incident tet 수 + 해당 tet 들의 worst Q.
- 2-3 (low) 또는 4-7 (mid) cell shell 인 edge 가 swap 후보.
- Stellar 32-44 swap (Klingner §3.4) 의 pre-screening.

Returns: 후보 edges + 각 edge 의 (n_incident_tets, worst_q_among_them).
heap-based prioritization 으로 Stellar swap 의 입력.
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from numpy.typing import NDArray


@dataclass
class SwapCandidatesResult:
    n_internal_edges: int = 0
    n_swap_candidates: int = 0
    n_2_3_shell: int = 0    # 2 or 3 cells around edge — 2-3 swap candidate.
    n_4_7_shell: int = 0    # 4-7 cells — 4-4 swap candidate.
    elapsed_s: float = 0.0


_TET_EDGES = np.array(
    [[0, 1], [0, 2], [0, 3], [1, 2], [1, 3], [2, 3]],
    dtype=np.int64,
)


def screen_swap_candidates(
    pts: NDArray[np.float64],
    tets: NDArray[np.int64],
    *,
    q_threshold: float = 0.3,
) -> tuple[NDArray[np.int64], NDArray[np.float64], SwapCandidatesResult]:
    """tet edge → swap candidate 분석.

    Args:
        pts: (N, 3).
        tets: (T, 4).
        q_threshold: worst Q < threshold 인 edge 만 후보.

    Returns:
        (candidate_edges (k, 2) sorted, worst_q_per_edge (k,), result).
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
            SwapCandidatesResult(elapsed_s=time.perf_counter() - t0),
        )

    # tet shape quality (Klingner-like Q from BETA2709).
    from core.evaluator.tet_qshape import tet_qshape
    Q, _ = tet_qshape(pts, tets)

    # build edge → list of incident tets.
    e_idx = tets[:, _TET_EDGES]  # (T, 6, 2).
    e_idx_sorted = np.sort(e_idx, axis=-1)  # (T, 6, 2).

    # flatten: (T*6, 2) edges.
    flat_e = e_idx_sorted.reshape(-1, 2)
    flat_t = np.repeat(np.arange(n_t, dtype=np.int64), 6)

    # group by edge key.
    keys = flat_e[:, 0] * (1 << 32) + flat_e[:, 1]  # composite int.
    sort_idx = np.argsort(keys)
    keys_s = keys[sort_idx]
    edges_s = flat_e[sort_idx]
    t_s = flat_t[sort_idx]

    n_edges = keys_s.shape[0]
    cand_edges: list[np.ndarray] = []
    cand_worst_q: list[float] = []
    n_internal = 0
    n_2_3 = 0
    n_4_7 = 0

    i = 0
    while i < n_edges:
        j = i
        while j < n_edges and keys_s[j] == keys_s[i]:
            j += 1
        cnt = j - i
        # internal edge: 2+ incident tets.
        if cnt >= 2:
            n_internal += 1
            tet_ids = t_s[i:j]
            worst = float(Q[tet_ids].min())
            if cnt in (2, 3):
                n_2_3 += 1
            elif 4 <= cnt <= 7:
                n_4_7 += 1
            if worst < q_threshold and cnt <= 7:
                cand_edges.append(edges_s[i])
                cand_worst_q.append(worst)
        i = j

    if cand_edges:
        out_edges = np.stack(cand_edges, axis=0)
        out_q = np.array(cand_worst_q, dtype=np.float64)
        # sort by worst Q ascending (worst first).
        order = np.argsort(out_q)
        out_edges = out_edges[order]
        out_q = out_q[order]
    else:
        out_edges = np.zeros((0, 2), dtype=np.int64)
        out_q = np.zeros(0, dtype=np.float64)

    return out_edges, out_q, SwapCandidatesResult(
        n_internal_edges=n_internal,
        n_swap_candidates=int(out_edges.shape[0]),
        n_2_3_shell=n_2_3,
        n_4_7_shell=n_4_7,
        elapsed_s=time.perf_counter() - t0,
    )
