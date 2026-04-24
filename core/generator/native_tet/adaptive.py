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

    # angle defect = 2π - sum(incident triangle angles). sphere 상 곡률에 비례.
    # 간이 Gaussian 곡률 근사.
    total_angle = np.zeros(n, dtype=np.float64)

    def _angle(p0, p1, p2):
        e1 = p1 - p0
        e2 = p2 - p0
        n1 = np.linalg.norm(e1)
        n2 = np.linalg.norm(e2)
        if n1 < 1e-30 or n2 < 1e-30:
            return 0.0
        c = float(np.dot(e1, e2)) / (n1 * n2)
        c = max(-1.0, min(1.0, c))
        return float(np.arccos(c))

    for tri in F:
        a, b, c = (int(x) for x in tri)
        pa, pb, pc = V[a], V[b], V[c]
        total_angle[a] += _angle(pa, pb, pc)
        total_angle[b] += _angle(pb, pa, pc)
        total_angle[c] += _angle(pc, pa, pb)

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
