"""공용 geometric 유틸 — numpy 기반, 외부 라이브러리 의존 없음.

현재 제공:
    inside_winding_number(query, V, F) — +x ray-casting 기반 inside/outside 판정.
        Möller-Trumbore triangle intersection + y/z bbox prefilter 로 대형 surface
        에서 빠르게 동작. native_tet / native_hex / native_poly 3 엔진이 공유한다.

    inside_generalized_winding_number(query, V, F) — Jacobson 2013 §3 동등.
        triangle 별 solid angle 합 / 4π. self-intersecting / non-manifold 입력
        에서도 robust. ray-casting 보다 ~3× 느리나 hard mesh 에서 정확도 ↑.

v0.4.0-beta9 기준 추출. 이후 triangle areas, normals 등 공통 계산이 추가될 예정.
"""
from __future__ import annotations

import numpy as np


def inside_winding_number(
    query: np.ndarray, V: np.ndarray, F: np.ndarray,
) -> np.ndarray:
    """+x 방향 ray-casting 기반 inside 판정.

    각 query 점에서 +x 방향 ray 를 쏘아 (V, F) 삼각형 mesh 와의 교차 수를 세고,
    홀수 = inside, 짝수 = outside. 대형 mesh 성능을 위해 y/z bbox prefilter 로
    candidate face 를 미리 축소한 뒤 Möller-Trumbore 교차 판정을 수행.

    Args:
        query: (N, 3) 판정할 점들.
        V: (Nv, 3) triangle mesh vertex 좌표.
        F: (Nf, 3) triangle vertex index (0-based).

    Returns:
        (N,) bool array — True = inside surface.
    """
    Q = np.asarray(query, dtype=np.float64).copy()
    N = Q.shape[0]
    if N == 0 or F.size == 0:
        return np.zeros(N, dtype=bool)

    # Ray casting is ambiguous when the ray passes exactly through a triangle
    # edge/vertex.  Axis-aligned cube STLs are a common case: centroids with
    # y == z hit the diagonal shared by the two triangles on the +x face and
    # get double-counted as outside.  Cast from a deterministically jittered
    # copy of the query point so the geometric point is unchanged at mesh scale
    # but exact edge hits are avoided.
    bbox_diag = float(np.linalg.norm(np.asarray(V, dtype=np.float64).max(axis=0) - np.asarray(V, dtype=np.float64).min(axis=0)))
    jitter = max(bbox_diag * 1e-10, 1e-12)
    Q[:, 1] += jitter * 0.754877666
    Q[:, 2] += jitter * 0.569840291

    v0 = V[F[:, 0]]; v1 = V[F[:, 1]]; v2 = V[F[:, 2]]
    edge1 = v1 - v0
    edge2 = v2 - v0
    d = np.array([1.0, 0.0, 0.0])
    pvec = np.cross(d, edge2)
    det = (edge1 * pvec).sum(axis=1)
    safe = np.abs(det) > 1e-12
    inv_det = np.zeros_like(det)
    np.divide(1.0, det, where=safe, out=inv_det)

    face_y = np.stack([v0[:, 1], v1[:, 1], v2[:, 1]], axis=1)
    face_z = np.stack([v0[:, 2], v1[:, 2], v2[:, 2]], axis=1)
    face_y_min = face_y.min(axis=1); face_y_max = face_y.max(axis=1)
    face_z_min = face_z.min(axis=1); face_z_max = face_z.max(axis=1)
    face_x_max = np.maximum.reduce([v0[:, 0], v1[:, 0], v2[:, 0]])

    inside = np.zeros(N, dtype=bool)
    batch = 64
    # C-PERF-29 / beta2480 — vectorize per-query Möller-Trumbore by flattening
    # all (query, face) AABB-candidate pairs into 1D arrays + np.add.at hit count.
    for qi in range(0, N, batch):
        qs = Q[qi:qi + batch]
        B = qs.shape[0]
        qy = qs[:, 1:2]; qz = qs[:, 2:3]; qx = qs[:, 0:1]
        mask_qf = (
            (qy >= face_y_min[None, :]) & (qy <= face_y_max[None, :])
            & (qz >= face_z_min[None, :]) & (qz <= face_z_max[None, :])
            & (face_x_max[None, :] >= (qx - 1e-9))
        )
        if not mask_qf.any():
            continue
        li_arr, fi_arr = np.where(mask_qf)
        if li_arr.size == 0:
            continue
        tv = qs[li_arr] - v0[fi_arr]
        u_arr = (tv * pvec[fi_arr]).sum(axis=1) * inv_det[fi_arr]
        qvec = np.cross(tv, edge1[fi_arr])
        v_arr = (qvec * d).sum(axis=1) * inv_det[fi_arr]
        t_arr = (edge2[fi_arr] * qvec).sum(axis=1) * inv_det[fi_arr]
        hit_arr = (u_arr >= 0) & (v_arr >= 0) & (u_arr + v_arr <= 1) & (t_arr > 1e-9)
        hit_count = np.zeros(B, dtype=np.int64)
        np.add.at(hit_count, li_arr, hit_arr.astype(np.int64))
        inside[qi:qi + B] = (hit_count % 2 == 1)
    return inside


def inside_generalized_winding_number(
    query: np.ndarray, V: np.ndarray, F: np.ndarray,
    *, threshold: float = 0.5,
) -> np.ndarray:
    """C-QUAL-3 / beta2390 — Jacobson 2013 §3 generalized winding number.

    Self-intersecting / non-manifold mesh 에서도 robust. 각 query 점 p 에 대해
    surface 의 모든 triangle 의 solid angle 부호 합 / (4π) 을 계산.
    값이 threshold (0.5) 초과면 inside.

    SOTA fTetWild §3.5 가 이 식을 사용. ray-casting 보다 ~3× 느리지만
    self-intersecting 입력에서 inside 판정 정확.

    Args:
        query: (N, 3) 판정 점.
        V: (Nv, 3) surface vertex.
        F: (Nf, 3) triangle index.
        threshold: 0.5 default — solid_angle_sum > threshold = inside.

    Returns:
        (N,) bool array.
    """
    Q = np.asarray(query, dtype=np.float64)
    N = Q.shape[0]
    if N == 0 or F.size == 0:
        return np.zeros(N, dtype=bool)

    v0 = V[F[:, 0]]
    v1 = V[F[:, 1]]
    v2 = V[F[:, 2]]

    inside = np.zeros(N, dtype=bool)
    # Van Oosterom-Strackee 1983 식 (벡터화).
    # Ω = 2 atan2(|a · (b × c)|, |a||b||c| + (a·b)|c| + (b·c)|a| + (c·a)|b|)
    # with sign from triple product.
    # C-PERF-30 / beta2481 — per-query loop 제거: (B, Nf, 3) broadcast 로
    # 한 batch 의 모든 (query, face) 쌍을 1-shot 처리.
    batch = 32
    Nf = int(F.shape[0])
    for qi in range(0, N, batch):
        qs = Q[qi:qi + batch]                                    # (B, 3)
        B = qs.shape[0]
        a = v0[None, :, :] - qs[:, None, :]                       # (B, Nf, 3)
        b = v1[None, :, :] - qs[:, None, :]
        c = v2[None, :, :] - qs[:, None, :]
        la = np.linalg.norm(a, axis=2)                            # (B, Nf)
        lb = np.linalg.norm(b, axis=2)
        lc = np.linalg.norm(c, axis=2)
        tri = np.einsum("bfi,bfi->bf", a, np.cross(b, c))         # (B, Nf)
        ab = np.einsum("bfi,bfi->bf", a, b)                       # (B, Nf)
        bc = np.einsum("bfi,bfi->bf", b, c)
        ca = np.einsum("bfi,bfi->bf", c, a)
        denom = la * lb * lc + ab * lc + bc * la + ca * lb        # (B, Nf)
        omega = 2.0 * np.arctan2(tri, denom + 1e-30)              # (B, Nf)
        w = omega.sum(axis=1) / (4.0 * np.pi)                     # (B,)
        inside[qi:qi + B] = np.abs(w) > threshold
    return inside
