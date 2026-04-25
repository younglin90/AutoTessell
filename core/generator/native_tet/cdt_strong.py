"""T1 — Constrained Delaunay 강화: surface edge midpoint forced insertion.

cube / cylinder 같은 형상에서는 단순 Delaunay 결과가 surface 대각선을 종종
빠뜨린다. 본 모듈은 강제 전략을 취한다:

    1) 입력 surface edge 중 현재 tet mesh 에서 missing 인 것을 추출.
    2) 각 missing edge 의 midpoint 를 신규 point 로 추가.
    3) (입력 surface vertex + 기존 internal points + 신규 midpoints) 로
       전체 re-Delaunay.
    4) 결과의 missing 재계산. 줄어들면 채택.
    5) 더 이상 줄어들지 않을 때까지 반복.

re-Delaunay 가 비싸지만 cube/cylinder 같이 vertex 수 작은 입력에선 매우 효과적.
대형 mesh 는 chunked_delaunay 로 자동 fallback (mesher 통합 시).
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np


@dataclass
class StrongCDTResult:
    iterations: int
    n_inserted: int
    ratio_before: float
    ratio_after: float
    n_missing_before: int
    n_missing_after: int


def strong_cdt_recovery(
    pts: np.ndarray, tets: np.ndarray,
    V_surf: np.ndarray, F_surf: np.ndarray,
    *,
    max_iter: int = 4,
    points_budget: int = 500,
) -> tuple[np.ndarray, np.ndarray, StrongCDTResult]:
    """missing surface edge midpoint 강제 삽입 + 전체 re-Delaunay.

    Args:
        pts: 현재 tet 의 모든 점 (surface vertex 포함).
        tets: 현재 tet 배열.
        V_surf, F_surf: 입력 surface (canonical vertex indexing — pts 의
            앞부분이 V_surf 와 동일 좌표 가정).
        max_iter: midpoint 삽입 + re-Delaunay 반복 한도.
        points_budget: 한 번 iteration 에서 추가할 midpoint 상한.

    Returns:
        (new_pts, new_tets, info).
    """
    from scipy.spatial import Delaunay
    from core.generator.native_tet.cdt_check import (
        check_edge_recovery, cdt_ratio,
    )

    pts = np.asarray(pts, dtype=np.float64)
    tets = np.asarray(tets, dtype=np.int64)

    r0 = check_edge_recovery(F_surf, tets)
    n_before = r0.n_missing
    ratio_before = cdt_ratio(r0)
    if n_before == 0:
        return pts, tets, StrongCDTResult(
            0, 0, ratio_before, ratio_before, 0, 0,
        )

    cur_pts = pts.copy()
    cur_tets = tets.copy()
    n_inserted = 0
    iters = 0

    for it in range(int(max_iter)):
        r_cur = check_edge_recovery(F_surf, cur_tets)
        if r_cur.n_missing == 0:
            break

        # 각 missing edge 에 대해 [1/3, 1/2, 2/3] 3 점 삽입 — edge 분할
        # 후 sub-edge 가 회복되도록.
        candidates: list[list[float]] = []
        for (u, v) in r_cur.missing_edges[:points_budget]:
            a = V_surf[u]; b = V_surf[v]
            for t in (1.0 / 3.0, 0.5, 2.0 / 3.0):
                p = a + t * (b - a)
                d = np.linalg.norm(cur_pts - p, axis=1).min() \
                    if cur_pts.shape[0] else 1.0
                if d > 1e-6:
                    candidates.append(p.tolist())
            if len(candidates) >= int(points_budget):
                break

        if not candidates:
            break

        new_pts = np.vstack([cur_pts, np.asarray(candidates, dtype=np.float64)])
        try:
            D = Delaunay(new_pts)
            new_tets = np.asarray(D.simplices, dtype=np.int64)
        except Exception:
            break

        r_after = check_edge_recovery(F_surf, new_tets)
        if r_after.n_missing <= r_cur.n_missing:
            # missing edge 자체는 같지만 sub-edge 단위로 보면 분할 후 더 회복
            # 가능성. 단조 보장 위해 strict <.
            if r_after.n_missing == r_cur.n_missing:
                # subdivision 후에도 missing 이 안 줄면 종료.
                break
            cur_pts = new_pts
            cur_tets = new_tets
            n_inserted += len(candidates)
            iters = it + 1
        else:
            break  # 악화: revert.

    r_final = check_edge_recovery(F_surf, cur_tets)
    return cur_pts, cur_tets, StrongCDTResult(
        iterations=int(iters),
        n_inserted=int(n_inserted),
        ratio_before=float(ratio_before),
        ratio_after=float(cdt_ratio(r_final)),
        n_missing_before=int(n_before),
        n_missing_after=int(r_final.n_missing),
    )
