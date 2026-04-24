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


def _vertex_normal_from_faces(
    V: np.ndarray, F: np.ndarray,
) -> np.ndarray:
    """surface vertex 별 법선 = 인접 triangle area-weighted normal 평균.

    Returns: (V.shape[0], 3) unit normal (degenerate 인 경우 0).
    """
    V = np.asarray(V, dtype=np.float64)
    F = np.asarray(F, dtype=np.int64)
    N = np.zeros_like(V)
    if F.size == 0:
        return N
    e1 = V[F[:, 1]] - V[F[:, 0]]
    e2 = V[F[:, 2]] - V[F[:, 0]]
    face_n = np.cross(e1, e2)   # area-weighted
    for i in range(F.shape[0]):
        for vi in F[i]:
            N[vi] += face_n[i]
    norms = np.linalg.norm(N, axis=1, keepdims=True)
    safe = norms[:, 0] > 1e-30
    out = np.zeros_like(N)
    out[safe] = N[safe] / norms[safe]
    return out


def smooth_tangent_surface(
    pts: np.ndarray,
    tets: np.ndarray,
    surface_vertex_ids: np.ndarray,
    vertex_normals: np.ndarray,
    *,
    feature_locked_ids: np.ndarray | None = None,
    n_iter: int = 1,
    relax: float = 0.3,
) -> SmoothResult:
    """surface vertex 를 tangent plane 내에서만 이동.

    각 iteration 에서:
      new_pos = pos + relax * (centroid - pos)
      new_pos -= ((new_pos - pos) · n) * n     (법선 성분 제거)

    feature_locked_ids 에 속하면 고정 (sharp edge / corner 보존).
    """
    pts = np.asarray(pts, dtype=np.float64)
    tets = np.asarray(tets, dtype=np.int64)
    surf = np.asarray(surface_vertex_ids, dtype=np.int64).ravel()
    vn = np.asarray(vertex_normals, dtype=np.float64)

    locked = np.zeros(pts.shape[0], dtype=bool)
    if feature_locked_ids is not None:
        locked[np.asarray(feature_locked_ids, dtype=np.int64)] = True

    # surface vertex 의 1-ring (tet edge 기준).
    nbr: dict[int, set[int]] = {int(i): set() for i in surf}
    surf_set = set(int(x) for x in surf)
    for t in tets:
        a, b, c, d = int(t[0]), int(t[1]), int(t[2]), int(t[3])
        for u, v in ((a, b), (a, c), (a, d), (b, c), (b, d), (c, d)):
            if u in surf_set:
                nbr[u].add(v)
            if v in surf_set:
                nbr[v].add(u)

    max_disp = 0.0
    moved = 0
    for _ in range(max(0, int(n_iter))):
        new_pts = pts.copy()
        for i in surf:
            ii = int(i)
            if locked[ii] or not nbr[ii]:
                continue
            nb = np.fromiter(nbr[ii], dtype=np.int64)
            centroid = pts[nb].mean(axis=0)
            delta = centroid - pts[ii]
            # 법선 성분 제거 (tangent plane 유지).
            n = vn[ii]
            nn = float(np.linalg.norm(n))
            if nn > 1e-30:
                n = n / nn
                delta = delta - float(np.dot(delta, n)) * n
            new = pts[ii] + relax * delta
            disp = float(np.linalg.norm(new - pts[ii]))
            if disp > max_disp:
                max_disp = disp
            new_pts[ii] = new
            moved += 1
        pts[:] = new_pts

    return SmoothResult(
        n_iter=int(n_iter),
        n_interior_moved=int(moved),
        max_displacement=float(max_disp),
    )
