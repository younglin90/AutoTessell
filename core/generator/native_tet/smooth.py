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


def _build_edge_rows(tets: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """tet edge 로부터 (row, col) index 배열 생성 (양방향, 중복 허용).

    Smoothing 의 1-ring neighbor sum 을 np.add.at 로 vectorize 하기 위함.
    """
    tets = np.asarray(tets, dtype=np.int64)
    if tets.size == 0:
        return np.zeros(0, dtype=np.int64), np.zeros(0, dtype=np.int64)
    pairs = np.stack(
        [
            tets[:, [0, 1]], tets[:, [0, 2]], tets[:, [0, 3]],
            tets[:, [1, 2]], tets[:, [1, 3]], tets[:, [2, 3]],
        ],
        axis=1,
    ).reshape(-1, 2)
    # 양방향.
    rev = pairs[:, ::-1]
    both = np.concatenate([pairs, rev], axis=0)
    # 중복 제거 (한 edge 가 여러 tet 에 공유되면 중복됨).
    # np.unique on rows.
    struc = np.ascontiguousarray(both).view(
        np.dtype((np.void, both.dtype.itemsize * both.shape[1]))
    )
    _, idx = np.unique(struc, return_index=True)
    uniq = both[idx]
    return uniq[:, 0], uniq[:, 1]


def smooth_interior(
    pts: np.ndarray,
    tets: np.ndarray,
    *,
    locked_vertex_ids: np.ndarray,
    n_iter: int = 2,
    relax: float = 0.5,
) -> SmoothResult:
    """pts 를 in-place 로 업데이트. locked 외 vertex 만 이동.

    Vectorized: 1-ring neighbor centroid 를 np.add.at 로 O(E) per iter.
    """
    pts = np.asarray(pts, dtype=np.float64)
    tets = np.asarray(tets, dtype=np.int64)
    n = pts.shape[0]
    locked_mask = np.zeros(n, dtype=bool)
    if locked_vertex_ids is not None and len(locked_vertex_ids) > 0:
        locked_mask[np.asarray(locked_vertex_ids, dtype=np.int64)] = True

    rows, cols = _build_edge_rows(tets)

    max_disp = 0.0
    n_moved = 0
    for _ in range(max(0, int(n_iter))):
        sum_nbr = np.zeros_like(pts)
        count = np.zeros(n, dtype=np.int64)
        np.add.at(sum_nbr, rows, pts[cols])
        np.add.at(count, rows, 1)
        valid = (count > 0) & (~locked_mask)
        new_pts = pts.copy()
        if valid.any():
            centroid = np.zeros_like(pts)
            centroid[valid] = sum_nbr[valid] / count[valid, None]
            delta = centroid[valid] - pts[valid]
            step = relax * delta
            new_pts[valid] = pts[valid] + step
            max_d = float(np.linalg.norm(step, axis=1).max()) if step.size else 0.0
            if max_d > max_disp:
                max_disp = max_d
            n_moved += int(valid.sum())
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

    rows, cols = _build_edge_rows(tets)
    # surface vertex mask.
    surf_mask = np.zeros(pts.shape[0], dtype=bool)
    surf_mask[surf] = True

    max_disp = 0.0
    moved = 0
    for _ in range(max(0, int(n_iter))):
        sum_nbr = np.zeros_like(pts)
        count = np.zeros(pts.shape[0], dtype=np.int64)
        np.add.at(sum_nbr, rows, pts[cols])
        np.add.at(count, rows, 1)
        valid = surf_mask & (count > 0) & (~locked)
        if not valid.any():
            break
        centroid = np.zeros_like(pts)
        centroid[valid] = sum_nbr[valid] / count[valid, None]
        delta = centroid[valid] - pts[valid]
        # 법선 성분 제거 (tangent plane 유지).
        nv = vn[valid]
        norms = np.linalg.norm(nv, axis=1, keepdims=True)
        safe = norms[:, 0] > 1e-30
        unit_n = np.zeros_like(nv)
        unit_n[safe] = nv[safe] / norms[safe]
        dot_vn = np.einsum("ij,ij->i", delta, unit_n)[:, None]
        tangent_delta = delta - dot_vn * unit_n
        step = relax * tangent_delta
        new_pts = pts.copy()
        new_pts[valid] = pts[valid] + step
        max_d = float(np.linalg.norm(step, axis=1).max()) if step.size else 0.0
        if max_d > max_disp:
            max_disp = max_d
        moved += int(valid.sum())
        pts[:] = new_pts

    return SmoothResult(
        n_iter=int(n_iter),
        n_interior_moved=int(moved),
        max_displacement=float(max_disp),
    )
