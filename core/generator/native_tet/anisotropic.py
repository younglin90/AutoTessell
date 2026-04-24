"""Round 37 — Anisotropic sizing metric tensor.

per-vertex 3×3 SPD metric `M_i` 를 정의하고 edge length 를 metric 공간에서
측정 (√((p-q)ᵀ M_avg (p-q))). 곡률이 큰 방향을 짧은 edge 로 유도.

Metric 구성:
    - 곡률 기반 principal-direction 설정.
    - 굴곡 없는 방향은 base edge length (큰 값), 굴곡 있는 방향은 작게.
    - 현재는 SIMPLE axis-aligned 형태로 시작 (x/y/z 세 방향 독립 스케일).
    - 향후 curvature tensor (shape operator) eigen-decomp 기반으로 확장.

레퍼런스
    - Loseille & Alauzet 2011, "Continuous mesh framework Part I/II".
    - Frey & George 2008, "Mesh Generation: Application to Finite Elements".
    - fTetWild (MPL-2.0) 의 sizing 은 scalar only; 본 모듈은 추가 기능.

독립 Python 재구현. 원본 C++ 미복제.
"""
from __future__ import annotations

import numpy as np


def axis_aligned_metric(
    V: np.ndarray,
    base_edge: float,
    *,
    scale_x: float = 1.0,
    scale_y: float = 1.0,
    scale_z: float = 1.0,
) -> np.ndarray:
    """per-vertex axis-aligned SPD metric. 단순하게 xyz 각 방향 독립 스케일.

    edge length in this metric = √(Σ (e_k / (base × scale_k))²).

    Args:
        V: (n, 3).
        base_edge: 기본 edge length.
        scale_x/y/z: 해당 축에서의 target edge length 배수. < 1 = 더 짧게.

    Returns:
        (n, 3, 3) SPD tensors (대각 성분만 사용).
    """
    V = np.asarray(V, dtype=np.float64)
    n = V.shape[0]
    diag = 1.0 / (base_edge * np.array(
        [scale_x, scale_y, scale_z], dtype=np.float64
    )) ** 2
    M = np.zeros((n, 3, 3), dtype=np.float64)
    M[:, 0, 0] = diag[0]
    M[:, 1, 1] = diag[1]
    M[:, 2, 2] = diag[2]
    return M


def curvature_aligned_metric(
    V: np.ndarray,
    F: np.ndarray,
    base_edge: float,
    *,
    aniso_ratio: float = 0.5,
) -> np.ndarray:
    """곡률이 큰 방향으로 짧은 edge 를 요구하는 metric.

    각 surface vertex 의 vertex normal 을 principal direction 으로 취급.
    normal 방향으로 base_edge, 접면 방향으로 base_edge × aniso_ratio (짧게).

    Args:
        V, F: surface mesh.
        base_edge: 기본 edge length.
        aniso_ratio: tangent 방향 편집 length 배수 (< 1 이면 더 짧게).

    Returns:
        (V.shape[0], 3, 3) SPD metrics.
    """
    V = np.asarray(V, dtype=np.float64)
    F = np.asarray(F, dtype=np.int64)
    n = V.shape[0]
    # vertex normal (area-weighted).
    if F.shape[0] > 0:
        e1 = V[F[:, 1]] - V[F[:, 0]]
        e2 = V[F[:, 2]] - V[F[:, 0]]
        face_n = np.cross(e1, e2)
        vn = np.zeros_like(V)
        for i in range(F.shape[0]):
            for vi in F[i]:
                vn[vi] += face_n[i]
        norms = np.linalg.norm(vn, axis=1, keepdims=True)
        safe = norms[:, 0] > 1e-30
        unit = np.zeros_like(vn)
        unit[safe] = vn[safe] / norms[safe]
    else:
        unit = np.zeros_like(V)

    M = np.zeros((n, 3, 3), dtype=np.float64)
    h_n = base_edge
    h_t = base_edge * aniso_ratio

    for i in range(n):
        nv = unit[i]
        if np.linalg.norm(nv) < 0.5:
            # isotropic.
            M[i] = np.eye(3) * (1.0 / h_n**2)
            continue
        # 접면에 수직인 기본 basis 구성 (Gram-Schmidt).
        helper = np.array([1.0, 0.0, 0.0]) if abs(nv[0]) < 0.9 else np.array([0.0, 1.0, 0.0])
        t1 = helper - np.dot(helper, nv) * nv
        t1 /= np.linalg.norm(t1) + 1e-30
        t2 = np.cross(nv, t1)

        basis = np.stack([nv, t1, t2], axis=1)   # 3x3
        eig = np.diag([1.0 / h_n**2, 1.0 / h_t**2, 1.0 / h_t**2])
        M[i] = basis @ eig @ basis.T

    return M


def edge_length_metric(
    p: np.ndarray, q: np.ndarray, Mp: np.ndarray, Mq: np.ndarray,
) -> float:
    """두 vertex 사이 metric-aware edge length.

    formula: √((p-q)ᵀ ((Mp + Mq)/2) (p-q)).
    """
    d = p - q
    M = 0.5 * (Mp + Mq)
    return float(np.sqrt(d @ M @ d))


def log_euclidean_average(
    M1: np.ndarray, M2: np.ndarray,
) -> np.ndarray:
    """beta1200 (R119) — log-Euclidean metric 평균.

    M_avg = exp(0.5 · (log(M1) + log(M2))).

    symmetric PD 텐서는 직접 평균하면 보간이 왜곡되지만 log 공간 평균은
    invariant 유지. Arsigny et al. 2006.

    Args:
        M1, M2: (3, 3) 혹은 (N, 3, 3) SPD.
    """
    def _safe_log(M):
        # eigen-decomp → log eigen → 복원.
        w, V = np.linalg.eigh(M)
        w = np.where(w > 1e-30, w, 1e-30)
        return np.einsum(
            "...ij,...j,...kj->...ik",
            V, np.log(w), V,
        )

    def _safe_exp(M):
        w, V = np.linalg.eigh(M)
        return np.einsum(
            "...ij,...j,...kj->...ik",
            V, np.exp(w), V,
        )

    return _safe_exp(0.5 * (_safe_log(M1) + _safe_log(M2)))


def edge_lengths_metric_batch(
    pts: np.ndarray, M: np.ndarray, edges: np.ndarray,
) -> np.ndarray:
    """edges (E, 2) 의 metric length 를 배치로."""
    pts = np.asarray(pts, dtype=np.float64)
    edges = np.asarray(edges, dtype=np.int64)
    if edges.size == 0:
        return np.zeros(0)
    d = pts[edges[:, 0]] - pts[edges[:, 1]]
    Mavg = 0.5 * (M[edges[:, 0]] + M[edges[:, 1]])
    # length² = dᵀ Mavg d
    l2 = np.einsum("ij,ijk,ik->i", d, Mavg, d)
    return np.sqrt(np.maximum(l2, 0.0))
