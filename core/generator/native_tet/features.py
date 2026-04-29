"""Phase A1 — 입력 표면에서 sharp edge 와 feature vertex 검출.

알고리즘 레퍼런스
    - Botsch et al. 2010, "Polygon Mesh Processing" Chapter 6.
    - fTetWild (Hu et al. 2020, MPL-2.0) 의 feature preservation 전략 참고
      (논문 §3.4). 본 모듈은 독립 Python 재구현이며 원본 C++ 코드를 복제하지
      않는다.

입력 표면 triangle 의 edge 별 dihedral angle 을 계산, 지정 임계 이상이면
feature edge 로 분류. feature edge 의 양 끝 vertex 는 "locked" — 이후 smoothing
/ edge flip 에서 이동 금지 대상.
"""
from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np


@dataclass
class FeatureInfo:
    """Sharp edge / corner 정보."""

    feature_edges: np.ndarray = field(default_factory=lambda: np.zeros((0, 2), dtype=np.int64))
    """(E, 2) array — feature edge 의 vertex index 쌍 (i<j)."""

    locked_vertices: np.ndarray = field(default_factory=lambda: np.zeros(0, dtype=np.int64))
    """feature edge 에 붙은 vertex index 의 sorted unique array."""

    corner_vertices: np.ndarray = field(default_factory=lambda: np.zeros(0, dtype=np.int64))
    """3 개 이상의 feature edge 가 만나는 corner vertex."""

    def as_protected_edges(self) -> set[tuple[int, int]]:
        """beta1180 (R98) — feature edge 를 CDT constraint set 으로 반환.

        B-W 삽입 / collapse / flip 등에서 `protected_edges` kwarg 에 직접 전달.
        """
        out: set[tuple[int, int]] = set()
        for uv in self.feature_edges.tolist():
            u, v = int(uv[0]), int(uv[1])
            out.add((u, v) if u < v else (v, u))
        return out


def detect_features(
    V: np.ndarray,
    F: np.ndarray,
    *,
    feature_angle_deg: float = 30.0,
) -> FeatureInfo:
    """입력 표면 triangle 에서 sharp feature 추출.

    Args:
        V: (n, 3) vertex 좌표.
        F: (m, 3) triangle index.
        feature_angle_deg: 인접 triangle 의 dihedral 이 (180° - 이 값) 미만이면
            feature edge. 즉 "fold angle" 기준. 30° → dihedral < 150°.

    Returns:
        FeatureInfo.
    """
    V = np.asarray(V, dtype=np.float64)
    F = np.asarray(F, dtype=np.int64)
    if F.shape[0] == 0:
        return FeatureInfo()

    # 1) triangle normal.
    e1 = V[F[:, 1]] - V[F[:, 0]]
    e2 = V[F[:, 2]] - V[F[:, 0]]
    n = np.cross(e1, e2)
    n_norm = np.linalg.norm(n, axis=1, keepdims=True)
    n = np.where(n_norm > 1e-30, n / np.where(n_norm > 0, n_norm, 1.0), n)

    # 2) edge → 공유 triangle 맵.
    # C-PERF-46 / beta2497 — vectorize via lexsort + group-boundary.
    if F.size == 0:
        edge_tri: dict[tuple[int, int], list[int]] = {}
    else:
        src_et = F[:, [0, 1, 2]].reshape(-1).astype(np.int64)
        dst_et = F[:, [1, 2, 0]].reshape(-1).astype(np.int64)
        ti_et = np.repeat(np.arange(F.shape[0], dtype=np.int64), 3)
        u_et = np.minimum(src_et, dst_et)
        v_et = np.maximum(src_et, dst_et)
        order_et = np.lexsort((v_et, u_et))
        u_s_et = u_et[order_et]
        v_s_et = v_et[order_et]
        ti_s_et = ti_et[order_et]
        diff_et = np.r_[True, (u_s_et[1:] != u_s_et[:-1]) | (v_s_et[1:] != v_s_et[:-1])]
        starts_et = np.where(diff_et)[0]
        ends_et = np.r_[starts_et[1:], len(u_s_et)]
        edge_tri = {}
        for s, e in zip(starts_et.tolist(), ends_et.tolist()):
            k = (int(u_s_et[s]), int(v_s_et[s]))
            edge_tri[k] = ti_s_et[s:e].tolist()

    # 3) edge 별 dihedral angle.
    cos_thresh = float(np.cos(np.deg2rad(180.0 - feature_angle_deg)))
    feature_edges: list[tuple[int, int]] = []
    for (u, v), tris in edge_tri.items():
        if len(tris) != 2:
            # boundary (1 개) 또는 non-manifold (3 이상) → feature 로 간주.
            feature_edges.append((u, v))
            continue
        t0, t1 = tris
        dot = float(np.dot(n[t0], n[t1]))
        # dot = cos(angle between normals). 두 face 가 같은 방향이면 dot≈1,
        # 반대 (날카로운 fold) 이면 dot 작거나 음수. fold_angle = acos(dot).
        # feature: 두 face 가 이룬 dihedral 의 fold > feature_angle_deg.
        # cos(fold) < cos(feature_angle_deg) 이면 feature. 부호를 잘 챙겨야 함.
        # 두 normal 이 같은 쪽 (convex) 이면 dot=1, dihedral 이 180°.
        # 두 normal 이 반대 (sharp fold) 이면 dot 이 -1 근처.
        # fold = 180 - dihedral = acos(dot)
        # feature condition: fold > feature_angle_deg
        #                   → dot < cos(feature_angle_deg)
        cos_feature = float(np.cos(np.deg2rad(feature_angle_deg)))
        if dot < cos_feature:
            feature_edges.append((u, v))
        # cos_thresh 는 향후 확장용 (현재 미사용).
        _ = cos_thresh

    if not feature_edges:
        return FeatureInfo()

    feat_arr = np.asarray(sorted(feature_edges), dtype=np.int64)

    # 4) locked vertex set.
    locked = np.unique(feat_arr.ravel())

    # 5) corner: feature edge 가 3 개 이상 만나는 vertex.
    counts = np.zeros(V.shape[0], dtype=np.int64)
    for u, v in feat_arr:
        counts[u] += 1
        counts[v] += 1
    corners = np.where(counts >= 3)[0].astype(np.int64)

    return FeatureInfo(
        feature_edges=feat_arr,
        locked_vertices=locked,
        corner_vertices=corners,
    )
