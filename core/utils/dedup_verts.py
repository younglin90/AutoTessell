"""W5 / beta2720 — mesh duplicate vertex deduplication.

근접 (tol 이내) vertex pair 병합 → reindex F.
STL → mesh load 후 weld, surface repair 의 보조 단계.
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from numpy.typing import NDArray


@dataclass
class DedupResult:
    n_in: int = 0
    n_out: int = 0
    n_merged: int = 0
    elapsed_s: float = 0.0


def dedup_vertices(
    V: NDArray[np.float64],
    F: NDArray[np.int64] | None = None,
    *,
    tol: float = 1e-9,
) -> tuple[NDArray[np.float64], NDArray[np.int64] | None, DedupResult]:
    """근접 vertex 병합.

    Args:
        V: (N, 3).
        F: (M, 3) optional — 주어지면 reindex 해서 반환.
        tol: 같다고 간주할 거리.

    Returns:
        (V_out, F_out_or_None, DedupResult).
    """
    import time
    t0 = time.perf_counter()

    V = np.asarray(V, dtype=np.float64)
    n_in = int(V.shape[0])
    if n_in == 0:
        return V, F, DedupResult(elapsed_s=time.perf_counter() - t0)

    # quantize coords to tol grid → unique → mapping.
    if tol <= 0:
        keys = V
    else:
        keys = np.round(V / tol).astype(np.int64) * tol
    # use np.unique on rows.
    keys_view = keys.view([("", keys.dtype)] * keys.shape[1]).reshape(-1)
    uniq, inverse = np.unique(keys_view, return_inverse=True)
    n_out = int(uniq.shape[0])

    # rebuild V_out: average of original V at each unique cluster.
    V_out = np.zeros((n_out, 3), dtype=np.float64)
    cnt = np.zeros(n_out, dtype=np.int64)
    for i in range(n_in):
        c = int(inverse[i])
        V_out[c] += V[i]
        cnt[c] += 1
    V_out = V_out / np.maximum(cnt[:, None], 1)

    F_out = None
    if F is not None:
        F = np.asarray(F, dtype=np.int64)
        if F.size > 0:
            F_out = inverse[F].astype(np.int64)
        else:
            F_out = F.copy()

    return V_out, F_out, DedupResult(
        n_in=n_in,
        n_out=n_out,
        n_merged=n_in - n_out,
        elapsed_s=time.perf_counter() - t0,
    )
