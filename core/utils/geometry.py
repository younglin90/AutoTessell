"""공용 geometric 유틸 — numpy 기반, 외부 라이브러리 의존 없음.

현재 제공:
    inside_winding_number(query, V, F) — +x ray-casting 기반 inside/outside 판정.
        Möller-Trumbore triangle intersection + y/z bbox prefilter 로 대형 surface
        에서 빠르게 동작. native_tet / native_hex / native_poly 3 엔진이 공유한다.

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
    Q = np.asarray(query, dtype=np.float64)
    N = Q.shape[0]
    if N == 0 or F.size == 0:
        return np.zeros(N, dtype=bool)

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
        for li in range(B):
            cand = np.where(mask_qf[li])[0]
            if cand.size == 0:
                continue
            tv = qs[li] - v0[cand]
            u = (tv * pvec[cand]).sum(axis=1) * inv_det[cand]
            qvec = np.cross(tv, edge1[cand])
            v = (qvec * d).sum(axis=1) * inv_det[cand]
            t = (edge2[cand] * qvec).sum(axis=1) * inv_det[cand]
            hit = (u >= 0) & (v >= 0) & (u + v <= 1) & (t > 1e-9)
            if int(hit.sum()) % 2 == 1:
                inside[qi + li] = True
    return inside
