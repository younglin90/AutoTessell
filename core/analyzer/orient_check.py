"""V2 / beta2710 — surface orientation consistency check.

각 edge 가 두 incident face 에서 반대 방향으로 등장해야 watertight orientation.
같은 방향으로 등장 = inconsistent (winding error).

mesh repair / native_repair winding pass 의 진단 입력.
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from numpy.typing import NDArray


@dataclass
class OrientCheckResult:
    n_triangles: int = 0
    n_edges: int = 0
    n_consistent_edges: int = 0     # 두 face 가 반대 방향.
    n_inconsistent_edges: int = 0   # 두 face 가 같은 방향 (잘못됨).
    n_boundary_edges: int = 0       # 1 face only.
    n_nonmanifold_edges: int = 0    # 3+ faces.
    consistency_ratio: float = 1.0  # consistent / (consistent + inconsistent).
    elapsed_s: float = 0.0


def orient_check(F: NDArray[np.int64]) -> OrientCheckResult:
    """tri F (M, 3) 의 winding 일관성 검사.

    각 face → 3 directed edges (v0→v1, v1→v2, v2→v0).
    edge (u, v) 가 두 face 에 나타날 때:
        - 한 쪽이 (u, v), 다른 쪽이 (v, u) → consistent.
        - 둘 다 (u, v) 또는 둘 다 (v, u) → inconsistent.
    """
    import time
    t0 = time.perf_counter()

    F = np.asarray(F, dtype=np.int64)
    n_f = int(F.shape[0])
    if n_f == 0:
        return OrientCheckResult(elapsed_s=time.perf_counter() - t0)

    # directed edges.
    dedges = np.concatenate([F[:, [0, 1]], F[:, [1, 2]], F[:, [2, 0]]], axis=0)

    # undirected key: (min, max).
    udges = np.sort(dedges, axis=1)
    # whether dedge is in "forward" order matching udges.
    forward = (dedges[:, 0] <= dedges[:, 1])  # True → dedge == udges, False → reversed.

    # group by undirected key.
    sort_idx = np.lexsort((udges[:, 1], udges[:, 0]))
    udges_s = udges[sort_idx]
    forward_s = forward[sort_idx]

    # find run-length groups.
    n_dedges = udges_s.shape[0]
    starts = [0]
    for i in range(1, n_dedges):
        if udges_s[i, 0] != udges_s[i - 1, 0] or udges_s[i, 1] != udges_s[i - 1, 1]:
            starts.append(i)
    starts.append(n_dedges)

    n_unique = len(starts) - 1
    n_consistent = 0
    n_inconsistent = 0
    n_bnd = 0
    n_nm = 0
    for k in range(n_unique):
        s, e = starts[k], starts[k + 1]
        cnt = e - s
        if cnt == 1:
            n_bnd += 1
        elif cnt == 2:
            # two faces incident: forward + reversed = consistent.
            f0, f1 = forward_s[s], forward_s[s + 1]
            if f0 != f1:
                n_consistent += 1
            else:
                n_inconsistent += 1
        else:
            n_nm += 1

    cons_total = n_consistent + n_inconsistent
    ratio = float(n_consistent) / cons_total if cons_total > 0 else 1.0

    return OrientCheckResult(
        n_triangles=n_f,
        n_edges=n_unique,
        n_consistent_edges=n_consistent,
        n_inconsistent_edges=n_inconsistent,
        n_boundary_edges=n_bnd,
        n_nonmanifold_edges=n_nm,
        consistency_ratio=ratio,
        elapsed_s=time.perf_counter() - t0,
    )
