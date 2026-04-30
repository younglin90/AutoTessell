"""R2 / beta2682 — Volume mesh cell adjacency graph.

각 cell 의 face-shared neighbours 추출. mesh smoothness 분석 / partition 입력.
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from numpy.typing import NDArray


@dataclass
class AdjacencyGraphResult:
    n_cells: int = 0
    n_edges: int = 0           # graph edges (cell-cell pairs).
    avg_degree: float = 0.0
    max_degree: int = 0
    min_degree: int = 0
    n_isolated_cells: int = 0  # degree 0.
    elapsed_s: float = 0.0


def build_tet_adjacency(
    tets: NDArray[np.int64],
) -> tuple[list[list[int]], AdjacencyGraphResult]:
    """Tet mesh face-shared adjacency (4 face/tet, each shared by 1 neighbor).

    Args:
        tets: (T, 4).

    Returns:
        (adj_list, AdjacencyGraphResult).
        adj_list[i] = list of neighbor cell IDs (face-shared).
    """
    import time
    t0 = time.perf_counter()

    tets = np.asarray(tets, dtype=np.int64)
    n_t = int(tets.shape[0])
    if n_t == 0:
        return [], AdjacencyGraphResult(elapsed_s=time.perf_counter() - t0)

    # 각 tet 의 4 face = 4 sorted vertex triple.
    # face = sorted(t[i], t[j], t[k]) for (0,1,2)/(0,1,3)/(0,2,3)/(1,2,3).
    face_combos = np.array([[0,1,2],[0,1,3],[0,2,3],[1,2,3]], dtype=np.int64)
    faces_per_tet = tets[:, face_combos]  # (T, 4, 3).
    faces_flat = faces_per_tet.reshape(-1, 3)  # (4T, 3).
    faces_sorted = np.sort(faces_flat, axis=1)
    cell_ids = np.repeat(np.arange(n_t, dtype=np.int64), 4)

    # group by face → cells sharing it.
    # canonical face key.
    n_v_max = int(tets.max()) + 1
    keys = (
        faces_sorted[:, 0].astype(np.int64) * (n_v_max + 1) ** 2
        + faces_sorted[:, 1].astype(np.int64) * (n_v_max + 1)
        + faces_sorted[:, 2].astype(np.int64)
    )
    # sort by key.
    order = np.argsort(keys, kind="stable")
    sorted_keys = keys[order]
    sorted_cells = cell_ids[order]
    # group boundaries.
    diff = np.diff(sorted_keys)
    starts = np.concatenate(([0], np.where(diff != 0)[0] + 1))
    ends = np.concatenate((starts[1:], [len(sorted_keys)]))

    adj: list[list[int]] = [[] for _ in range(n_t)]
    for s, e in zip(starts.tolist(), ends.tolist()):
        cells_in_group = sorted_cells[s:e].tolist()
        if len(cells_in_group) == 2:
            a, b = int(cells_in_group[0]), int(cells_in_group[1])
            adj[a].append(b)
            adj[b].append(a)
        # else: 1 cell (boundary face) or 3+ cells (non-manifold — ignored).

    degrees = [len(a) for a in adj]
    n_edges = sum(degrees) // 2
    n_isolated = sum(1 for d in degrees if d == 0)

    return adj, AdjacencyGraphResult(
        n_cells=n_t,
        n_edges=n_edges,
        avg_degree=float(sum(degrees)) / max(n_t, 1),
        max_degree=int(max(degrees)) if degrees else 0,
        min_degree=int(min(degrees)) if degrees else 0,
        n_isolated_cells=n_isolated,
        elapsed_s=time.perf_counter() - t0,
    )
