"""Round 50 — missing surface edge recovery.

cdt_check 가 찾은 missing edge 들에 대해 midpoint vertex 를 제안 → Bowyer-
Watson 로 삽입. 각 missing edge (u, v) 의 중점 (V[u] + V[v]) / 2 를 신규 점
으로 추가하면 edge 가 두 sub-edge (u, mid), (mid, v) 로 recovery 될 확률이
올라간다 (완전 보장은 아님; 재귀 처리 필요할 수 있음).

본 모듈은 single-pass 제안만. 반복은 mesher caller 가 수행.

레퍼런스
    - Si 2015, TetGen §4 boundary recovery.
    - Shewchuk 1998 Delaunay refinement.
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np


@dataclass
class EdgeRecoveryProposal:
    n_missing_before: int
    new_points: np.ndarray   # (K, 3).
    edges_resolved_by_proposal: int


def propose_edge_midpoints(
    V: np.ndarray, missing_edges: list[tuple[int, int]],
    *, max_points: int = 500,
) -> EdgeRecoveryProposal:
    """missing edge 각각의 중점을 신규 점으로 제안.

    Args:
        V: (n, 3) — surface vertex indexing.
        missing_edges: cdt_check 의 missing_edges 리스트.
        max_points: 상한.
    """
    V = np.asarray(V, dtype=np.float64)
    if not missing_edges:
        return EdgeRecoveryProposal(0, np.zeros((0, 3)), 0)
    pts_list: list[list[float]] = []
    for (u, v) in missing_edges[: max_points]:
        mid = 0.5 * (V[u] + V[v])
        pts_list.append(mid.tolist())
    return EdgeRecoveryProposal(
        n_missing_before=len(missing_edges),
        new_points=np.asarray(pts_list, dtype=np.float64),
        edges_resolved_by_proposal=-1,    # caller 가 post-insertion 에 측정.
    )
