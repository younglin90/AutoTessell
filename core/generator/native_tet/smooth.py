"""Phase A4 (bonus) — 경계 고정 interior Laplacian smoothing.

Interior vertex 만 1-링 neighbor centroid 로 점진 이동. Surface vertex 와
feature-locked vertex 는 이동하지 않음. 1-3 iteration 으로 큰 품질 개선.

레퍼런스
    - Botsch et al. 2010, "Polygon Mesh Processing" §6.5 (Laplacian smoothing).
    - fTetWild (MPL-2.0) §3.3 vertex smooth 의 interior-only 변형.
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np


@dataclass
class SmoothResult:
    n_iter: int
    n_interior_moved: int
    max_displacement: float


def smooth_interior(
    pts: np.ndarray,
    tets: np.ndarray,
    *,
    locked_vertex_ids: np.ndarray,
    n_iter: int = 2,
    relax: float = 0.5,
) -> SmoothResult:
    """pts 를 in-place 로 업데이트. locked 외 vertex 만 이동.

    Args:
        pts: (N, 3). In-place 수정.
        tets: (T, 4).
        locked_vertex_ids: 고정 vertex index array. surface vertex + feature
            locked 를 모두 포함해야 한다.
        n_iter: smoothing 반복 횟수.
        relax: 한 번에 centroid 로 이동할 비율 (0=움직임 없음, 1=완전 centroid).

    Returns:
        SmoothResult.
    """
    pts = np.asarray(pts, dtype=np.float64)
    tets = np.asarray(tets, dtype=np.int64)
    n = pts.shape[0]
    locked_mask = np.zeros(n, dtype=bool)
    if locked_vertex_ids is not None and len(locked_vertex_ids) > 0:
        locked_mask[np.asarray(locked_vertex_ids, dtype=np.int64)] = True

    # 1-ring neighbor list (tet edge 기준).
    nbr: list[set[int]] = [set() for _ in range(n)]
    for t in tets:
        a, b, c, d = int(t[0]), int(t[1]), int(t[2]), int(t[3])
        for u, v in ((a, b), (a, c), (a, d), (b, c), (b, d), (c, d)):
            nbr[u].add(v)
            nbr[v].add(u)

    max_disp = 0.0
    n_moved = 0
    for _ in range(max(0, int(n_iter))):
        new_pts = pts.copy()
        for i in range(n):
            if locked_mask[i] or not nbr[i]:
                continue
            nb = np.fromiter(nbr[i], dtype=np.int64)
            centroid = pts[nb].mean(axis=0)
            new = pts[i] + relax * (centroid - pts[i])
            disp = float(np.linalg.norm(new - pts[i]))
            if disp > max_disp:
                max_disp = disp
            new_pts[i] = new
            n_moved += 1
        pts[:] = new_pts

    return SmoothResult(
        n_iter=int(n_iter),
        n_interior_moved=int(n_moved),
        max_displacement=float(max_disp),
    )
