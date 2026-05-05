"""Phase E2 — Curvature-based adaptive target edge length.

uniform target_edge_length 대신 vertex 별 sizing field 를 제공:
  - 평평한 영역: 큰 edge length (거친 메쉬로 셀 수 절약).
  - 곡률 높은 영역: 작은 edge length (feature 보존).

구현: 각 vertex 에 대해 1-ring edge 의 dihedral / surface 곡률 근사를 계산.

레퍼런스
    - Botsch et al. 2010 §6.6 "Adaptive Remeshing".
    - fTetWild (MPL-2.0) §3.1 sizing field. 독립 Python 재구현.
"""
from __future__ import annotations

import numpy as np


def curvature_sizing(
    V: np.ndarray,
    F: np.ndarray,
    *,
    target_edge: float,
    min_ratio: float = 0.25,
    max_ratio: float = 2.0,
    curvature_gain: float = 2.0,
) -> np.ndarray:
    """per-vertex target edge length 반환.

    Args:
        V: (n, 3) vertex 좌표.
        F: (m, 3) triangle.
        target_edge: base edge length.
        min_ratio / max_ratio: 결과 범위 [target × min, target × max].
        curvature_gain: 곡률이 클수록 edge 를 줄이는 민감도. 클수록 feature
            영역이 더 세밀해진다.

    Returns:
        (n,) float — 각 vertex 의 권장 edge length.
    """
    V = np.asarray(V, dtype=np.float64)
    F = np.asarray(F, dtype=np.int64)
    n = V.shape[0]
    out = np.full(n, float(target_edge), dtype=np.float64)
    if F.shape[0] == 0:
        return out

    # beta960 (R91): Python loop 제거 — per-vertex angle defect 을 완전
    # 벡터 (np.add.at scatter-add).
    total_angle = np.zeros(n, dtype=np.float64)
    A = V[F[:, 0]]; B = V[F[:, 1]]; C = V[F[:, 2]]

    def _corner_angle(P, Q, R):
        e1 = Q - P; e2 = R - P
        n1 = np.linalg.norm(e1, axis=1)
        n2 = np.linalg.norm(e2, axis=1)
        denom = np.where((n1 > 1e-30) & (n2 > 1e-30), n1 * n2, 1.0)
        c = np.einsum("ij,ij->i", e1, e2) / denom
        c = np.clip(c, -1.0, 1.0)
        ang = np.arccos(c)
        ang[(n1 < 1e-30) | (n2 < 1e-30)] = 0.0
        return ang

    ang_a = _corner_angle(A, B, C)
    ang_b = _corner_angle(B, A, C)
    ang_c = _corner_angle(C, A, B)
    np.add.at(total_angle, F[:, 0], ang_a)
    np.add.at(total_angle, F[:, 1], ang_b)
    np.add.at(total_angle, F[:, 2], ang_c)

    defect = 2.0 * np.pi - total_angle   # 볼록 영역 > 0, 평면 = 0.
    # 절댓값 기준으로 스케일.
    absdef = np.abs(defect)
    # normalize: max defect 을 기준으로 0~1.
    mx = float(absdef.max()) if n > 0 else 0.0
    if mx < 1e-30:
        return out
    norm = absdef / mx

    # target_edge × (1 - gain × norm) + clamp.
    scale = 1.0 - float(curvature_gain) * norm * 0.5
    scale = np.clip(scale, float(min_ratio), float(max_ratio))
    out = float(target_edge) * scale
    return out


def gradient_limited_sizing(
    per_vertex: np.ndarray,
    edges: np.ndarray,
    *,
    max_ratio: float = 1.5,
    max_iter: int = 10,
) -> np.ndarray:
    """beta1010 (R114) — adjacent vertex 간 sizing 비율을 `max_ratio` 이내로.

    fTetWild §3.2 gradation control. edge 양 끝 sizing 차이가 너무 크면
    작은 쪽을 올려 점진 변화.
    """
    s = np.asarray(per_vertex, dtype=np.float64).copy()
    E = np.asarray(edges, dtype=np.int64)
    if s.size == 0 or E.size == 0:
        return s
    r = float(max_ratio)
    u = E[:, 0]; v = E[:, 1]
    for _ in range(int(max_iter)):
        su = s[u]; sv = s[v]
        cap_u = sv * r
        cap_v = su * r
        new_su = np.minimum(su, cap_u)
        new_sv = np.minimum(sv, cap_v)
        # scatter minimum.
        np.minimum.at(s, u, new_su)
        np.minimum.at(s, v, new_sv)
        if np.allclose(s[u], su) and np.allclose(s[v], sv):
            break
    return s


def distance_based_sizing(
    V: np.ndarray,
    V_surface: np.ndarray,
    *,
    target_edge: float,
    near_ratio: float = 0.5,
    far_ratio: float = 2.0,
    transition: float = 1.0,
) -> np.ndarray:
    """beta1020 (R117) — 표면 근접 vertex 는 작은 edge, 내부 깊은 곳은 큰 edge.

    transition: bbox-diag 단위 상대 거리.
    """
    V = np.asarray(V, dtype=np.float64)
    if V.shape[0] == 0:
        return np.zeros(0, dtype=np.float64)
    try:
        from scipy.spatial import cKDTree  # noqa: PLC0415
        tree = cKDTree(np.asarray(V_surface, dtype=np.float64))
        d, _ = tree.query(V, k=1)
    except Exception:
        d = np.linalg.norm(V[:, None] - np.asarray(V_surface)[None], axis=2).min(axis=1)
    bbox = np.ptp(V, axis=0)
    diag = float(np.linalg.norm(bbox))
    t = np.clip(d / (float(transition) * diag + 1e-30), 0.0, 1.0)
    scale = float(near_ratio) + (float(far_ratio) - float(near_ratio)) * t
    return float(target_edge) * scale


def sizing_callback_eval(
    V: np.ndarray,
    sizing_cb,
    *,
    fallback: float = 1.0,
) -> np.ndarray:
    """beta1030 (R115) — user sizing_cb(xyz)->scalar 를 per-vertex 로 평가.

    cb 가 None 이면 uniform fallback.
    """
    V = np.asarray(V, dtype=np.float64)
    if sizing_cb is None:
        return np.full(V.shape[0], float(fallback), dtype=np.float64)
    try:
        arr = np.asarray(sizing_cb(V), dtype=np.float64)
        if arr.shape == ():
            arr = np.full(V.shape[0], float(arr), dtype=np.float64)
        return arr
    except Exception:
        out = np.empty(V.shape[0], dtype=np.float64)
        for i in range(V.shape[0]):
            try:
                out[i] = float(sizing_cb(V[i]))
            except Exception:
                out[i] = float(fallback)
        return out


def curvature_and_hausdorff_sizing(
    V: np.ndarray, F: np.ndarray,
    V_input: np.ndarray,
    *,
    target_edge: float,
    curvature_gain: float = 2.0,
    hausdorff_weight: float = 0.5,
    min_ratio: float = 0.2,
    max_ratio: float = 2.0,
) -> np.ndarray:
    """beta1220 (R122) — 곡률 + 거리 동시 반영 sizing.

    per-vertex target = target_edge × combine(curvature_scale, hausdorff_scale).
    hausdorff_scale = ratio based on 표면까지의 상대 거리.
    """
    V = np.asarray(V, dtype=np.float64)
    curv_scale = curvature_sizing(
        V, F, target_edge=target_edge,
        curvature_gain=curvature_gain,
        min_ratio=min_ratio, max_ratio=max_ratio,
    ) / max(float(target_edge), 1e-30)
    try:
        from scipy.spatial import cKDTree  # noqa: PLC0415
        tree = cKDTree(np.asarray(V_input, dtype=np.float64))
        d, _ = tree.query(V, k=1)
    except Exception:
        d = np.zeros(V.shape[0])
    diag = float(np.linalg.norm(np.ptp(V, axis=0))) + 1e-30
    haus_scale = np.clip(d / diag, 0.0, 1.0)
    haus_scale = 1.0 + float(hausdorff_weight) * haus_scale
    combined = curv_scale * haus_scale
    combined = np.clip(combined, float(min_ratio), float(max_ratio))
    return float(target_edge) * combined


def feature_aware_sizing(
    V: np.ndarray, feature_vertices: np.ndarray,
    *,
    target_edge: float,
    feature_ratio: float = 0.5,
    falloff_radius: float = 0.1,
) -> np.ndarray:
    """beta1230 (R123) — feature edge 근방 vertex 를 더 조밀하게.

    distance-to-feature 기반 smooth ramp: near → feature_ratio, far → 1.0.
    """
    V = np.asarray(V, dtype=np.float64)
    n = V.shape[0]
    if n == 0:
        return np.zeros(0, dtype=np.float64)
    if feature_vertices is None or len(feature_vertices) == 0:
        return np.full(n, float(target_edge), dtype=np.float64)
    try:
        from scipy.spatial import cKDTree  # noqa: PLC0415
        tree = cKDTree(V[np.asarray(feature_vertices, dtype=np.int64)])
        d, _ = tree.query(V, k=1)
    except Exception:
        d = np.zeros(n)
    diag = float(np.linalg.norm(np.ptp(V, axis=0))) + 1e-30
    r = float(falloff_radius) * diag
    t = np.clip(d / max(r, 1e-30), 0.0, 1.0)
    scale = float(feature_ratio) + (1.0 - float(feature_ratio)) * t
    return float(target_edge) * scale


def per_vertex_target_to_edge_target(
    per_vertex: np.ndarray,
    edges: np.ndarray,
) -> np.ndarray:
    """per-vertex target → per-edge target (= min of two endpoints)."""
    per_vertex = np.asarray(per_vertex, dtype=np.float64)
    edges = np.asarray(edges, dtype=np.int64)
    a = per_vertex[edges[:, 0]]
    b = per_vertex[edges[:, 1]]
    return np.minimum(a, b)
