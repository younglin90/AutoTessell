"""native_hex boundary snap — hex 경계 vertex 를 STL surface 에 projection.

v0.4.0-beta22 추가. uniform grid 로 생성된 hex 메쉬는 stair-step boundary 를 갖는다.
fine quality 에서는 boundary 근처의 hex vertex 를 표면 삼각형의 closest point 로
projection 해 Hausdorff 거리를 개선한다.

알고리즘:
    1. boundary hex vertex 후보 = grid vertex 중 "표면 근방" 인 것.
       (cKDTree 로 triangle 중심점과의 nearest 거리 계산 → tol 이내만 선택).
    2. 각 후보 vertex 에 대해 nearest triangle 의 **closest point on triangle**
       계산 (barycentric clamp). 이 점이 projection 결과.
    3. projection 거리 > ``max_snap_ratio * target_edge`` 이면 **skip**
       (너무 멀면 hex skewness 폭발 위험).

안전 장치:
    - 거리 cap (기본 0.5 × target_edge): hex 가 자기 자신 경계를 넘어가지 않도록.
    - 모든 vertex 처리 → per-cell checkMesh 는 수행 안 함 (단순 vertex 이동이라
      cell topology 불변, volume 양수는 cap 으로 담보).
"""
from __future__ import annotations

import numpy as np

from core.utils.logging import get_logger

log = get_logger(__name__)


def _closest_point_on_triangle(
    P: np.ndarray, A: np.ndarray, B: np.ndarray, C: np.ndarray,
) -> np.ndarray:
    """단일 점 P 를 삼각형 (A, B, C) 의 가장 가까운 점으로 clamp.

    Ericson, "Real-Time Collision Detection" Ch.5.1.5 의 barycentric clamp.
    모두 shape (3,) numpy array.
    """
    ab = B - A
    ac = C - A
    ap = P - A

    d1 = float(ab @ ap); d2 = float(ac @ ap)
    if d1 <= 0.0 and d2 <= 0.0:
        return A  # vertex A region

    bp = P - B
    d3 = float(ab @ bp); d4 = float(ac @ bp)
    if d3 >= 0.0 and d4 <= d3:
        return B  # vertex B region

    vc = d1 * d4 - d3 * d2
    if vc <= 0.0 and d1 >= 0.0 and d3 <= 0.0:
        v = d1 / (d1 - d3)
        return A + v * ab  # edge AB region

    cp = P - C
    d5 = float(ab @ cp); d6 = float(ac @ cp)
    if d6 >= 0.0 and d5 <= d6:
        return C  # vertex C region

    vb = d5 * d2 - d1 * d6
    if vb <= 0.0 and d2 >= 0.0 and d6 <= 0.0:
        w = d2 / (d2 - d6)
        return A + w * ac  # edge AC region

    va = d3 * d6 - d5 * d4
    if va <= 0.0 and (d4 - d3) >= 0.0 and (d5 - d6) >= 0.0:
        w = (d4 - d3) / ((d4 - d3) + (d5 - d6))
        return B + w * (C - B)  # edge BC region

    denom = 1.0 / (va + vb + vc)
    v = vb * denom; w = vc * denom
    return A + ab * v + ac * w  # interior


def snap_hex_boundary_to_surface(
    hex_vertices: np.ndarray,
    surface_V: np.ndarray,
    surface_F: np.ndarray,
    target_edge: float,
    *,
    max_snap_ratio: float = 0.5,
    search_radius_ratio: float = 1.5,
) -> tuple[np.ndarray, dict[str, int]]:
    """hex 메쉬 vertex 를 STL surface 로 projection (beta22).

    hex cell topology 를 변경하지 않고 vertex 좌표만 수정 → cell 수 / face 수 /
    owner-neighbour 관계 불변.

    Args:
        hex_vertices: (N, 3) float — 현재 hex 메쉬 vertex 좌표 (in-place 수정 안 함).
        surface_V: (M, 3) 입력 STL vertex.
        surface_F: (K, 3) 입력 STL triangle 인덱스.
        target_edge: hex cell 의 평균 edge 길이. snap 거리 cap 계산 기준.
        max_snap_ratio: projection 거리가 ``target_edge × max_snap_ratio`` 를 넘으면
            해당 vertex 는 건너뜀 (skewness 방지). 기본 0.5.
        search_radius_ratio: triangle 중심으로부터의 탐색 반경. 이보다 먼 vertex
            는 애초에 projection 후보에서 제외. 기본 1.5 × target_edge.

    Returns:
        (snapped_vertices, stats) — snapped 은 입력 복사본 + 수정. stats 는
        ``{"n_snapped", "n_skipped_far", "n_skipped_beyond_cap", "n_candidates"}``.
    """
    hex_V = np.asarray(hex_vertices, dtype=np.float64).copy()
    sV = np.asarray(surface_V, dtype=np.float64)
    sF = np.asarray(surface_F, dtype=np.int64)

    stats = {
        "n_snapped": 0,
        "n_skipped_far": 0,
        "n_skipped_beyond_cap": 0,
        "n_candidates": int(len(hex_V)),
    }

    if len(sF) == 0 or len(hex_V) == 0:
        return hex_V, stats

    # Triangle centroids for coarse-nearest filter
    tri_A = sV[sF[:, 0]]
    tri_B = sV[sF[:, 1]]
    tri_C = sV[sF[:, 2]]
    tri_centroids = (tri_A + tri_B + tri_C) / 3.0

    # coarse NN via cKDTree (interop-fine)
    try:
        from scipy.spatial import cKDTree  # noqa: PLC0415
        tree = cKDTree(tri_centroids)
    except Exception as exc:
        log.warning("native_hex_snap_kdtree_failed", error=str(exc))
        return hex_V, stats

    search_r = float(search_radius_ratio * target_edge)
    cap = float(max_snap_ratio * target_edge)

    # 각 hex vertex 에 대해 k=4 candidates 를 받고, 그중 closest point on triangle
    # 최소 거리를 취하면 더 정확. k=1 로 시작하면 vertex 가 triangle 모서리 걸쳐 있을 때
    # 잘못된 nearest triangle 선택 가능. k=4 로 안정화.
    k = min(4, len(tri_centroids))
    dists_coarse, nn_idx = tree.query(hex_V, k=k, distance_upper_bound=search_r)
    if k == 1:
        dists_coarse = dists_coarse[:, None]
        nn_idx = nn_idx[:, None]

    for i in range(len(hex_V)):
        # dist_upper_bound 를 넘은 query 는 idx = len(tri_centroids), dist = inf
        cand = nn_idx[i]
        cand = cand[cand < len(tri_centroids)]
        if cand.size == 0:
            stats["n_skipped_far"] += 1
            continue

        P = hex_V[i]
        best_dist2 = np.inf
        best_pt = None
        for t in cand:
            pt = _closest_point_on_triangle(P, tri_A[t], tri_B[t], tri_C[t])
            d2 = float(((pt - P) ** 2).sum())
            if d2 < best_dist2:
                best_dist2 = d2
                best_pt = pt

        if best_pt is None:
            stats["n_skipped_far"] += 1
            continue

        dist = float(best_dist2 ** 0.5)
        if dist > cap:
            stats["n_skipped_beyond_cap"] += 1
            continue

        hex_V[i] = best_pt
        stats["n_snapped"] += 1

    log.info(
        "native_hex_snap_done",
        **stats, cap=cap, search_r=search_r,
    )
    return hex_V, stats
