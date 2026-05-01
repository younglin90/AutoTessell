"""AA5 / beta2748 — tet 2-3 / 3-2 flip candidate detector.

각 internal face (3 vertex 공유) 가 두 tet 사이에 있을 때 → 2-3 flip 검토.
2-3 flip: 2 tets sharing face → 3 tets sharing edge (worst case quality 개선 가능).

Stellar §3.4 의 face-flip pre-screen.
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from numpy.typing import NDArray


@dataclass
class FlipCandidatesResult:
    n_internal_faces: int = 0
    n_flip_candidates: int = 0   # worst Q < threshold 인 face pair.
    elapsed_s: float = 0.0


def screen_flip_candidates(
    pts: NDArray[np.float64],
    tets: NDArray[np.int64],
    *,
    q_threshold: float = 0.3,
) -> tuple[NDArray[np.int64], NDArray[np.float64], FlipCandidatesResult]:
    """internal face 의 worst Q → 2-3 flip 후보.

    Args:
        pts: (N, 3).
        tets: (T, 4).
        q_threshold: worst Q < 임계 인 face 만 후보.

    Returns:
        (face_pairs (k, 2) tet indices, worst_q (k,), result).
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
            FlipCandidatesResult(elapsed_s=time.perf_counter() - t0),
        )

    from core.analyzer.tet_face_adj import build_tet_face_adjacency
    from core.evaluator.tet_qshape import tet_qshape

    adj, _ = build_tet_face_adjacency(tets)
    Q, _ = tet_qshape(pts, tets)

    # 각 internal face → (tet_a, tet_b) where adj[a, f]=b.
    pairs: list[tuple[int, int]] = []
    qs: list[float] = []
    seen: set[tuple[int, int]] = set()

    for ti in range(n_t):
        for fi in range(4):
            tj = int(adj[ti, fi])
            if tj < 0:
                continue
            key = (min(ti, tj), max(ti, tj))
            if key in seen:
                continue
            seen.add(key)
            worst = min(float(Q[ti]), float(Q[tj]))
            if worst < q_threshold:
                pairs.append(key)
                qs.append(worst)

    n_internal = len(seen)
    if pairs:
        out = np.array(pairs, dtype=np.int64)
        out_q = np.array(qs, dtype=np.float64)
        order = np.argsort(out_q)
        out = out[order]
        out_q = out_q[order]
    else:
        out = np.zeros((0, 2), dtype=np.int64)
        out_q = np.zeros(0, dtype=np.float64)

    return out, out_q, FlipCandidatesResult(
        n_internal_faces=n_internal,
        n_flip_candidates=int(out.shape[0]),
        elapsed_s=time.perf_counter() - t0,
    )
