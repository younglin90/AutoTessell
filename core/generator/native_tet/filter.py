"""Phase A2 — Boundary-aware sliver filter.

기존 mesher.py 는 모든 tet 에 대해 `q ≥ q_thresh` 일괄 적용 → 경계 근처 얇은
tet 도 잘려나가 구멍 / 들쭉날쭉한 표면 발생. 이 모듈은 경계 tet 에는 관대한
임계, 내부 tet 에는 엄격한 임계를 적용. 경계 triangle 이 손실되면 해당 tet 은
강제 유지.

레퍼런스
    - fTetWild (Hu et al. 2020, MPL-2.0) §3.3 quality stop criterion 의 기본
      아이디어 — boundary-preserving sliver handling. Python 독립 재구현.
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np


@dataclass
class FilterResult:
    keep_mask: np.ndarray           # (T,) bool
    n_dropped: int
    n_boundary_protected: int
    n_interior_dropped: int
    q_thresh_boundary: float
    q_thresh_interior: float


def _tet_shape_quality(points_per_tet: np.ndarray) -> np.ndarray:
    """tet 별 shape quality ∈ [0, 1]. 정사면체 ≈ 1, sliver ≈ 0.

    q = 8.48 * V / edge_max^3  (Parthasarathy & Graichen & Hathaway 1994 변형).
    """
    v = points_per_tet   # (T, 4, 3)
    e01 = np.linalg.norm(v[:, 1] - v[:, 0], axis=1)
    e02 = np.linalg.norm(v[:, 2] - v[:, 0], axis=1)
    e03 = np.linalg.norm(v[:, 3] - v[:, 0], axis=1)
    e12 = np.linalg.norm(v[:, 2] - v[:, 1], axis=1)
    e13 = np.linalg.norm(v[:, 3] - v[:, 1], axis=1)
    e23 = np.linalg.norm(v[:, 3] - v[:, 2], axis=1)
    edge_max = np.maximum.reduce([e01, e02, e03, e12, e13, e23])
    vol = np.abs(
        np.einsum(
            "ij,ij->i",
            v[:, 1] - v[:, 0],
            np.cross(v[:, 2] - v[:, 0], v[:, 3] - v[:, 0]),
        )
    ) / 6.0
    safe = edge_max > 1e-30
    q = np.zeros_like(edge_max)
    q[safe] = 8.48 * vol[safe] / (edge_max[safe] ** 3)
    return q


def filter_slivers(
    tets: np.ndarray,
    pts: np.ndarray,
    inside_mask: np.ndarray,
    *,
    n_surface_vertices: int,
    q_threshold_interior: float = 0.05,
    q_threshold_boundary: float = 0.005,
    protect_boundary_faces: bool = True,
) -> FilterResult:
    """inside tet 중 sliver 를 boundary-aware 로 제거.

    Args:
        tets: (T, 4) tet vertex index.
        pts: (N, 3) 점 좌표. 인덱스 [0, n_surface_vertices) 은 surface vertex.
        inside_mask: (T,) bool — centroid 가 안쪽인 tet.
        n_surface_vertices: surface vertex 개수. tets 의 index 가 이 값 미만이면
            해당 vertex 는 경계에 있음.
        q_threshold_interior: 내부 tet sliver 기준 (기존 기본 0.05).
        q_threshold_boundary: 경계 tet (≥1 surface vertex) 관대 기준.
            기본 0.005 — 실질적 "탈락시키지 않음".
        protect_boundary_faces: True 면 제거 후 surface triangle 이 더이상 어떤
            tet 의 face 에 포함되지 않게 되는 경우 해당 tet 되살림.

    Returns:
        FilterResult.
    """
    tets = np.asarray(tets, dtype=np.int64)
    pts = np.asarray(pts, dtype=np.float64)
    inside_mask = np.asarray(inside_mask, dtype=bool)
    if tets.shape[0] == 0:
        return FilterResult(
            keep_mask=np.zeros(0, dtype=bool),
            n_dropped=0, n_boundary_protected=0, n_interior_dropped=0,
            q_thresh_boundary=q_threshold_boundary,
            q_thresh_interior=q_threshold_interior,
        )

    v = pts[tets]
    q = _tet_shape_quality(v)

    # tet 이 surface vertex 를 하나라도 포함하면 boundary-tet.
    has_surf = (tets < n_surface_vertices).any(axis=1)

    thr = np.where(
        has_surf,
        float(q_threshold_boundary),
        float(q_threshold_interior),
    )
    keep = inside_mask & (q >= thr)

    n_boundary_protected = 0
    if protect_boundary_faces and not keep.all():
        # 제거 후 각 surface vertex 가 최소 1 개 tet 에 포함되는지 확인.
        # 그렇지 않으면 해당 vertex 에 인접했던 가장 quality 높은 dropped tet 을
        # 되살려 hole 방지.
        # C-PERF-82 / beta2533 — vectorize: kept tets × 4 verts → mask 일괄.
        covered = np.zeros(n_surface_vertices, dtype=bool)
        if keep.any():
            kept_verts = tets[keep].ravel()
            surf_kept = kept_verts[kept_verts < n_surface_vertices]
            if surf_kept.size > 0:
                covered[surf_kept] = True
        missing = np.where(~covered)[0]
        if missing.size > 0:
            dropped_idx = np.where(inside_mask & ~keep)[0]
            # dropped 를 quality desc 로 정렬.
            order = np.argsort(-q[dropped_idx])
            dropped_sorted = dropped_idx[order]
            missing_set = set(missing.tolist())
            for t_idx in dropped_sorted:
                if not missing_set:
                    break
                covers = [
                    int(v_idx) for v_idx in tets[t_idx]
                    if int(v_idx) < n_surface_vertices and int(v_idx) in missing_set
                ]
                if covers:
                    keep[t_idx] = True
                    n_boundary_protected += 1
                    for v_idx in covers:
                        missing_set.discard(v_idx)

    dropped_total = int(inside_mask.sum() - keep.sum())
    interior_dropped = int((~has_surf & inside_mask & ~keep).sum())

    return FilterResult(
        keep_mask=keep,
        n_dropped=dropped_total,
        n_boundary_protected=n_boundary_protected,
        n_interior_dropped=interior_dropped,
        q_thresh_boundary=float(q_threshold_boundary),
        q_thresh_interior=float(q_threshold_interior),
    )
