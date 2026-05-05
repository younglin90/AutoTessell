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


def propose_recursive_midpoint(
    V: np.ndarray, missing_edges: list[tuple[int, int]],
    *, max_depth: int = 3, max_points: int = 1000,
) -> EdgeRecoveryProposal:
    """beta1170 (R96) — Shewchuk 2002 recursive midpoint segment split.

    midpoint 1번으로 edge 회복이 안 되면 두 half 를 각각 재귀 midpoint 로
    분할 후보에 추가. depth ↑ 로 dense 한 샘플 제공.
    """
    V = np.asarray(V, dtype=np.float64)
    if not missing_edges:
        return EdgeRecoveryProposal(0, np.zeros((0, 3)), 0)

    out: list[list[float]] = []

    def _rec(a: np.ndarray, b: np.ndarray, depth: int) -> None:
        if depth <= 0 or len(out) >= max_points:
            return
        mid = 0.5 * (a + b)
        out.append(mid.tolist())
        _rec(a, mid, depth - 1)
        _rec(mid, b, depth - 1)

    for (u, v) in missing_edges:
        if len(out) >= max_points:
            break
        _rec(V[u], V[v], int(max_depth))

    return EdgeRecoveryProposal(
        n_missing_before=len(missing_edges),
        new_points=np.asarray(out, dtype=np.float64) if out else np.zeros((0, 3)),
        edges_resolved_by_proposal=-1,
    )


def propose_edge_subdivision(
    V: np.ndarray, missing_edges: list[tuple[int, int]],
    *, splits_per_edge: int = 3,
    max_points: int = 1000,
) -> EdgeRecoveryProposal:
    """Shewchuk-style denser recovery — 각 missing edge 를 splits_per_edge 등분.

    중점 1 개 삽입으로 부족하면 edge 를 여러 균등 분할 점으로 쪼갠다. 각 삽입
    후보는 B-W 의 cavity 를 깊게 침투해 원본 edge 를 포함하는 tet 구성 유도.

    레퍼런스: TetGen Si 2015 §4 recursive segment recovery.
    """
    V = np.asarray(V, dtype=np.float64)
    if not missing_edges:
        return EdgeRecoveryProposal(0, np.zeros((0, 3)), 0)
    splits_per_edge = max(1, int(splits_per_edge))
    pts_list: list[list[float]] = []
    for (u, v) in missing_edges:
        if len(pts_list) >= max_points:
            break
        a = V[u]; b = V[v]
        for i in range(1, splits_per_edge + 1):
            if len(pts_list) >= max_points:
                break
            t = i / (splits_per_edge + 1)
            pts_list.append((a + t * (b - a)).tolist())
    return EdgeRecoveryProposal(
        n_missing_before=len(missing_edges),
        new_points=np.asarray(pts_list, dtype=np.float64) if pts_list else np.zeros((0, 3)),
        edges_resolved_by_proposal=-1,
    )
