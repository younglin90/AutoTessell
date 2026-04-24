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
    quality_guard: bool = False,
) -> SmoothResult:
    """pts 를 in-place 로 업데이트. locked 외 vertex 만 이동.

    Vectorized: 1-ring neighbor centroid 를 np.add.at 로 O(E) per iter.

    quality_guard=True: 각 iteration 이후 min tet quality 가 하락하면 이전
    상태로 revert. 작은 메쉬에서 over-smoothing 으로 인한 품질 저하 방지.
    """
    pts = np.asarray(pts, dtype=np.float64)
    tets = np.asarray(tets, dtype=np.int64)
    n = pts.shape[0]
    locked_mask = np.zeros(n, dtype=bool)
    if locked_vertex_ids is not None and len(locked_vertex_ids) > 0:
        locked_mask[np.asarray(locked_vertex_ids, dtype=np.int64)] = True

    rows, cols = _build_edge_rows(tets)

    def _min_q(P: np.ndarray) -> float:
        if tets.size == 0:
            return 1.0
        v = P[tets]
        e = np.stack(
            [v[:, 1] - v[:, 0], v[:, 2] - v[:, 0], v[:, 3] - v[:, 0],
             v[:, 2] - v[:, 1], v[:, 3] - v[:, 1], v[:, 3] - v[:, 2]],
            axis=1,
        )
        emax = np.linalg.norm(e, axis=2).max(axis=1)
        vol = np.abs(np.einsum(
            "ij,ij->i",
            v[:, 1] - v[:, 0],
            np.cross(v[:, 2] - v[:, 0], v[:, 3] - v[:, 0]),
        )) / 6.0
        safe = emax > 1e-30
        q = np.zeros_like(emax)
        q[safe] = 8.48 * vol[safe] / (emax[safe] ** 3)
        return float(q.min()) if q.size else 1.0

    max_disp = 0.0
    n_moved = 0
    for _ in range(max(0, int(n_iter))):
        prev_snapshot = pts.copy() if quality_guard else None
        prev_minq = _min_q(pts) if quality_guard else 0.0

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

        if quality_guard:
            new_minq = _min_q(pts)
            # min_q 가 유의미하게 (>5%) 하락하면 revert.
            if prev_minq > 1e-6 and new_minq < prev_minq * 0.95:
                pts[:] = prev_snapshot   # type: ignore[arg-type]
                break

    return SmoothResult(
        n_iter=int(n_iter),
        n_interior_moved=int(n_moved),
        max_displacement=float(max_disp),
    )


def smooth_interior_metric(
    pts: np.ndarray,
    tets: np.ndarray,
    metric: np.ndarray,
    *,
    locked_vertex_ids: np.ndarray,
    n_iter: int = 1,
    relax: float = 0.4,
) -> tuple["SmoothResult", np.ndarray]:
    """beta1210 (R121) — metric-aware Laplacian smoothing.

    각 interior vertex 의 1-ring 이동 방향을 metric-weighted centroid 로.
    neighbor weight = exp(-d_M(p, q)) 근사 (가까운 metric 이웃에 큰 가중).
    """
    pts = np.asarray(pts, dtype=np.float64).copy()
    tets = np.asarray(tets, dtype=np.int64)
    n = pts.shape[0]
    locked_mask = np.zeros(n, dtype=bool)
    if locked_vertex_ids is not None and len(locked_vertex_ids) > 0:
        locked_mask[np.asarray(locked_vertex_ids, dtype=np.int64)] = True

    rows, cols = _build_edge_rows(tets)
    if rows.size == 0:
        return SmoothResult(0, 0, 0.0), pts

    max_disp = 0.0
    moved = 0
    for _ in range(max(0, int(n_iter))):
        d = pts[rows] - pts[cols]
        Mavg = 0.5 * (metric[rows] + metric[cols])
        d2 = np.einsum("ij,ijk,ik->i", d, Mavg, d)
        w = np.exp(-np.sqrt(np.maximum(d2, 0.0)))
        sum_wq = np.zeros_like(pts)
        sum_w = np.zeros(n, dtype=np.float64)
        np.add.at(sum_wq, rows, pts[cols] * w[:, None])
        np.add.at(sum_w, rows, w)
        valid = (sum_w > 1e-30) & (~locked_mask)
        if not valid.any():
            break
        target = np.zeros_like(pts)
        target[valid] = sum_wq[valid] / sum_w[valid, None]
        step = float(relax) * (target[valid] - pts[valid])
        pts[valid] = pts[valid] + step
        md = float(np.linalg.norm(step, axis=1).max()) if step.size else 0.0
        if md > max_disp:
            max_disp = md
        moved += int(valid.sum())

    return SmoothResult(
        n_iter=int(n_iter), n_interior_moved=int(moved),
        max_displacement=float(max_disp),
    ), pts


def smooth_odt(
    pts: np.ndarray,
    tets: np.ndarray,
    *,
    locked_vertex_ids: np.ndarray,
    n_iter: int = 1,
    relax: float = 0.7,
) -> SmoothResult:
    """beta1070 (R104) — Optimal Delaunay Triangulation (ODT) smoothing.

    각 interior vertex 를 1-ring tet 의 volume-weighted circumcenter 평균
    위치로 이동. Chen & Xu 2004.

    구현: 각 tet 의 외심 C_t, 부피 V_t 계산. vertex i 의 new position =
    Σ V_t·C_t / Σ V_t  (t ∈ 1-ring).

    Laplacian 보다 ~10-30% 더 좋은 min_dihedral 경향 (tetwild 경험).
    """
    pts = np.asarray(pts, dtype=np.float64).copy()
    tets = np.asarray(tets, dtype=np.int64)
    n = pts.shape[0]
    if tets.size == 0:
        return SmoothResult(0, 0, 0.0)
    locked_mask = np.zeros(n, dtype=bool)
    if locked_vertex_ids is not None and len(locked_vertex_ids) > 0:
        locked_mask[np.asarray(locked_vertex_ids, dtype=np.int64)] = True

    def _circumcenter_and_vol(v0, v1, v2, v3):
        # Ericson 2005 — tet circumcenter.
        A = np.stack([v1 - v0, v2 - v0, v3 - v0], axis=1)   # (T,3,3)
        b = 0.5 * np.stack([
            np.einsum("ij,ij->i", v1 - v0, v1 - v0),
            np.einsum("ij,ij->i", v2 - v0, v2 - v0),
            np.einsum("ij,ij->i", v3 - v0, v3 - v0),
        ], axis=1)[..., None]   # (T,3,1)
        # solve per-tet A · x = b.
        det = np.linalg.det(A)
        safe = np.abs(det) > 1e-20
        x = np.zeros_like(b)
        if safe.any():
            x[safe] = np.linalg.solve(A[safe], b[safe])
        center = v0 + x[..., 0]
        vol = np.abs(det) / 6.0
        return center, vol

    max_disp = 0.0
    moved = 0
    for _ in range(max(0, int(n_iter))):
        v = pts[tets]
        C, W = _circumcenter_and_vol(v[:, 0], v[:, 1], v[:, 2], v[:, 3])
        sum_wc = np.zeros_like(pts)
        sum_w = np.zeros(n, dtype=np.float64)
        for k in range(4):
            np.add.at(sum_wc, tets[:, k], W[:, None] * C)
            np.add.at(sum_w, tets[:, k], W)
        valid = (sum_w > 1e-30) & (~locked_mask)
        if not valid.any():
            break
        target = np.zeros_like(pts)
        target[valid] = sum_wc[valid] / sum_w[valid, None]
        step = float(relax) * (target[valid] - pts[valid])
        pts[valid] = pts[valid] + step
        max_d = float(np.linalg.norm(step, axis=1).max()) if step.size else 0.0
        if max_d > max_disp:
            max_disp = max_d
        moved += int(valid.sum())

    return SmoothResult(
        n_iter=int(n_iter),
        n_interior_moved=int(moved),
        max_displacement=float(max_disp),
    ), pts


def smooth_cvt(
    pts: np.ndarray,
    tets: np.ndarray,
    *,
    locked_vertex_ids: np.ndarray,
    n_iter: int = 1,
    relax: float = 0.5,
) -> tuple[SmoothResult, np.ndarray]:
    """beta1080 (R105) — Centroidal Voronoi Tessellation 유사 relaxation.

    interior vertex 를 1-ring tet centroid 의 volume-weighted 평균으로.
    Du, Faber, Gunzburger 1999.
    """
    pts = np.asarray(pts, dtype=np.float64).copy()
    tets = np.asarray(tets, dtype=np.int64)
    n = pts.shape[0]
    if tets.size == 0:
        return SmoothResult(0, 0, 0.0), pts
    locked_mask = np.zeros(n, dtype=bool)
    if locked_vertex_ids is not None and len(locked_vertex_ids) > 0:
        locked_mask[np.asarray(locked_vertex_ids, dtype=np.int64)] = True

    max_disp = 0.0
    moved = 0
    for _ in range(max(0, int(n_iter))):
        v = pts[tets]
        centroid = v.mean(axis=1)
        vol6 = np.abs(np.einsum(
            "ij,ij->i",
            v[:, 1] - v[:, 0],
            np.cross(v[:, 2] - v[:, 0], v[:, 3] - v[:, 0]),
        ))
        sum_wc = np.zeros_like(pts)
        sum_w = np.zeros(n, dtype=np.float64)
        for k in range(4):
            np.add.at(sum_wc, tets[:, k], vol6[:, None] * centroid)
            np.add.at(sum_w, tets[:, k], vol6)
        valid = (sum_w > 1e-30) & (~locked_mask)
        if not valid.any():
            break
        target = np.zeros_like(pts)
        target[valid] = sum_wc[valid] / sum_w[valid, None]
        step = float(relax) * (target[valid] - pts[valid])
        pts[valid] = pts[valid] + step
        max_d = float(np.linalg.norm(step, axis=1).max()) if step.size else 0.0
        if max_d > max_disp:
            max_disp = max_d
        moved += int(valid.sum())

    return SmoothResult(
        n_iter=int(n_iter),
        n_interior_moved=int(moved),
        max_displacement=float(max_disp),
    ), pts


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
    # beta1060 (R106 보조): Python nested loop → np.add.at scatter-add.
    np.add.at(N, F[:, 0], face_n)
    np.add.at(N, F[:, 1], face_n)
    np.add.at(N, F[:, 2], face_n)
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
