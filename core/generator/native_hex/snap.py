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


def _detect_surface_feature_vertices(
    surface_V: np.ndarray,
    surface_F: np.ndarray,
    feature_angle_deg: float = 45.0,
) -> np.ndarray:
    """surface STL 에서 sharp feature vertex id 목록 (corner / edge).

    인접 triangle 간 dihedral angle > threshold 인 edge 의 vertex 수집.
    """
    if surface_F.size == 0 or feature_angle_deg <= 0:
        return np.zeros(0, dtype=np.int64)
    # face unit normals
    v0 = surface_V[surface_F[:, 0]]
    v1 = surface_V[surface_F[:, 1]]
    v2 = surface_V[surface_F[:, 2]]
    n = np.cross(v1 - v0, v2 - v0)
    norms = np.linalg.norm(n, axis=1, keepdims=True)
    n = np.where(norms > 1e-30, n / np.where(norms > 1e-30, norms, 1.0), 0.0)

    # edge → face pair
    edge_map: dict[tuple[int, int], list[int]] = {}
    for fi in range(surface_F.shape[0]):
        a, b, c = int(surface_F[fi, 0]), int(surface_F[fi, 1]), int(surface_F[fi, 2])
        for x, y in ((a, b), (b, c), (c, a)):
            key = (x, y) if x < y else (y, x)
            edge_map.setdefault(key, []).append(fi)

    cos_thresh = float(np.cos(np.deg2rad(feature_angle_deg)))
    feature_set: set[int] = set()
    for (a, b), fl in edge_map.items():
        if len(fl) != 2:
            # boundary edge 도 feature 로 간주 (open mesh 에서 유용)
            feature_set.add(a); feature_set.add(b)
            continue
        cos_a = float(np.clip(np.dot(n[fl[0]], n[fl[1]]), -1.0, 1.0))
        if cos_a < cos_thresh:
            feature_set.add(a); feature_set.add(b)
    return np.array(sorted(feature_set), dtype=np.int64)


def snap_hex_boundary_to_surface(
    hex_vertices: np.ndarray,
    surface_V: np.ndarray,
    surface_F: np.ndarray,
    target_edge: float,
    *,
    max_snap_ratio: float = 0.5,
    search_radius_ratio: float = 1.5,
    preserve_features: bool = False,
    feature_angle_deg: float = 45.0,
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
        "n_feature_snapped": 0,
    }

    if len(sF) == 0 or len(hex_V) == 0:
        return hex_V, stats

    # beta66: feature vertex list + KDTree — snap 시 hex vertex 가 feature 근처
    # 에 있으면 closest-point-on-triangle 대신 nearest feature vertex 로 snap.
    feature_ids = np.zeros(0, dtype=np.int64)
    feature_tree = None
    if preserve_features:
        feature_ids = _detect_surface_feature_vertices(sV, sF, feature_angle_deg)
        if feature_ids.size > 0:
            try:
                from core.utils.kdtree import NumpyKDTree as _KT  # noqa: PLC0415
                feature_tree = _KT(sV[feature_ids])
            except Exception as exc:
                log.warning("native_hex_feature_kdtree_failed", error=str(exc))

    # Triangle centroids for coarse-nearest filter
    tri_A = sV[sF[:, 0]]
    tri_B = sV[sF[:, 1]]
    tri_C = sV[sF[:, 2]]
    tri_centroids = (tri_A + tri_B + tri_C) / 3.0

    # coarse NN via NumpyKDTree (beta28 — scipy 의존 제거)
    try:
        from core.utils.kdtree import NumpyKDTree  # noqa: PLC0415
        tree = NumpyKDTree(tri_centroids)
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

        # beta66: feature preservation — 현재 best_pt 가 feature vertex 근처
        # (cap 의 70% 이내) 라면 직접 feature vertex 로 snap.
        if feature_tree is not None:
            fd, fidx = feature_tree.query(
                np.asarray(best_pt).reshape(1, 3), k=1,
            )
            fd = float(np.asarray(fd).ravel()[0])
            fidx_i = int(np.asarray(fidx).ravel()[0])
            if fd <= 0.7 * cap and fidx_i < feature_ids.size:
                # feature vertex 좌표
                fv_coord = sV[feature_ids[fidx_i]]
                if float(np.linalg.norm(fv_coord - P)) <= cap:
                    hex_V[i] = fv_coord
                    stats["n_snapped"] += 1
                    stats["n_feature_snapped"] += 1
                    continue

        hex_V[i] = best_pt
        stats["n_snapped"] += 1

    log.info(
        "native_hex_snap_done",
        **stats, cap=cap, search_r=search_r,
    )
    return hex_V, stats


# ---------------------------------------------------------------------------
# beta94 — snap_to_surface_iterative (snappyHexMesh snap step 근사)
# ---------------------------------------------------------------------------


def _build_vertex_neighbors_from_triangles(
    n_vertices: int,
    surface_F: np.ndarray,
) -> list[list[int]]:
    """각 vertex 의 이웃 vertex 목록 (triangle adjacency). Laplacian smoothing 용."""
    nbrs: list[set[int]] = [set() for _ in range(n_vertices)]
    for tri in surface_F:
        a, b, c = int(tri[0]), int(tri[1]), int(tri[2])
        nbrs[a].add(b); nbrs[a].add(c)
        nbrs[b].add(a); nbrs[b].add(c)
        nbrs[c].add(a); nbrs[c].add(b)
    return [list(s) for s in nbrs]


def snap_to_surface_iterative(
    pts: np.ndarray,
    surface_V: np.ndarray,
    surface_F: np.ndarray,
    target_edge: float,
    *,
    n_iter: int = 5,
    max_snap_ratio: float = 0.3,
    relax: float = 0.5,
    smooth_after_snap: bool = True,
    smooth_iters: int = 2,
    feature_angle_deg: float = 45.0,
) -> tuple[np.ndarray, dict]:
    """snappyHexMesh snap step 근사 구현 (beta94).

    알고리즘:
        for iter in range(n_iter):
            1. 각 vertex 에서 nearest surface point 계산 (KDTree + closest_point_on_tri)
            2. 거리 < max_snap_ratio * target_edge 인 vertex 만 스냅 후보
            3. 후보 vertex 를 relax 비율만큼 surface 방향으로 이동:
               new_pos = old_pos + relax * (surface_pt - old_pos)
            4. (smooth_after_snap=True) 이동된 vertex 주변 non-snap vertex 에
               Laplacian smoothing smooth_iters 회 적용 (스냅 vertex 는 고정)

    Args:
        pts: (P, 3) 현재 vertex 좌표. 복사본을 반환 (in-place 아님).
        surface_V: (V, 3) 대상 STL 표면 vertex.
        surface_F: (F, 3) 대상 STL 표면 triangle.
        target_edge: 스냅 거리 상한 계산 기준 (hex cell 평균 edge length).
        n_iter: 반복 횟수 (기본 5).
        max_snap_ratio: 스냅 거리 상한 = max_snap_ratio × target_edge (기본 0.3).
        relax: 각 iter 에서 surface 쪽으로 이동 비율 0~1 (기본 0.5).
        smooth_after_snap: 스냅 후 Laplacian smoothing 적용 여부 (기본 True).
        smooth_iters: smoothing 반복 횟수 (기본 2).
        feature_angle_deg: feature vertex 감지 각도 (현재 미사용, 호환용).

    Returns:
        (snapped_pts, stats) 튜플.
        stats 포함: n_snapped_per_iter (list), final_n_snapped, max_displacement.
    """
    work_pts = np.asarray(pts, dtype=np.float64).copy()
    sV = np.asarray(surface_V, dtype=np.float64)
    sF = np.asarray(surface_F, dtype=np.int64)

    n_snapped_per_iter: list[int] = []
    max_displacement = 0.0

    cap = float(max_snap_ratio * target_edge)

    if sF.size == 0 or work_pts.size == 0 or cap <= 0.0:
        return work_pts, {
            "n_snapped_per_iter": n_snapped_per_iter,
            "final_n_snapped": 0,
            "max_displacement": 0.0,
        }

    # triangle centroids + KDTree (한 번만 구성)
    tri_A = sV[sF[:, 0]]
    tri_B = sV[sF[:, 1]]
    tri_C = sV[sF[:, 2]]
    tri_centroids = (tri_A + tri_B + tri_C) / 3.0

    # 최대 triangle 외접원 반경 (centroid ↔ vertex 최대 거리) 계산 → search_r 에 더함.
    # 이렇게 해야 centroid 가 멀어도 vertex 쪽으로 projected 되는 경우를 포착함.
    max_tri_extent = float(
        np.max(np.linalg.norm(
            tri_A - tri_centroids, axis=1,
        ))
    ) if len(tri_centroids) > 0 else 0.0

    try:
        from core.utils.kdtree import NumpyKDTree  # noqa: PLC0415
        tree = NumpyKDTree(tri_centroids)
    except Exception as exc:
        log.warning("snap_iterative_kdtree_failed", error=str(exc))
        return work_pts, {
            "n_snapped_per_iter": n_snapped_per_iter,
            "final_n_snapped": 0,
            "max_displacement": 0.0,
        }

    # search radius: cap + 최대 triangle 범위. 이로써 centroid 가 멀더라도
    # 실제로 triangle 내부의 closest_point 가 cap 이내에 있는 경우를 포착함.
    search_r = cap + max_tri_extent
    k_cand = min(4, len(tri_centroids))

    for _iter in range(n_iter):
        snapped_mask = np.zeros(len(work_pts), dtype=bool)
        snap_surface_pts = work_pts.copy()

        # 1~3. 각 vertex nearest surface point + relax 이동
        dists_coarse, nn_idx = tree.query(
            work_pts, k=k_cand, distance_upper_bound=search_r,
        )
        if k_cand == 1:
            dists_coarse = dists_coarse[:, None]
            nn_idx = nn_idx[:, None]

        for i in range(len(work_pts)):
            cand = nn_idx[i]
            cand = cand[cand < len(tri_centroids)]
            if cand.size == 0:
                continue

            P = work_pts[i]
            best_dist2 = np.inf
            best_pt = P
            for t in cand:
                pt = _closest_point_on_triangle(P, tri_A[t], tri_B[t], tri_C[t])
                d2 = float(((pt - P) ** 2).sum())
                if d2 < best_dist2:
                    best_dist2 = d2
                    best_pt = pt

            dist = float(best_dist2 ** 0.5)
            if dist > cap:
                continue

            # relax 이동
            new_pos = P + relax * (best_pt - P)
            snap_surface_pts[i] = new_pos
            snapped_mask[i] = True
            disp = float(np.linalg.norm(new_pos - P))
            if disp > max_displacement:
                max_displacement = disp

        n_snapped_this = int(snapped_mask.sum())
        n_snapped_per_iter.append(n_snapped_this)

        # snap 결과 적용
        work_pts = snap_surface_pts

        # 4. Laplacian smoothing (스냅된 vertex 는 고정, non-snap vertex 만 이동)
        if smooth_after_snap and n_snapped_this > 0 and smooth_iters > 0:
            # non-snap vertex 의 이웃 중 스냅된 vertex 가 있는 것만 smoothing
            # 간단한 구현: snapped vertex 의 1-ring non-snap vertex 에만 적용
            # 메모리 절약을 위해 KDTree 로 non-snap vertex 의 근접 이웃 탐색
            # → 간단히: 스냅된 vertex 주변 (search_r 이내) non-snap vertex 스무딩
            nbr_tree = NumpyKDTree(work_pts[snapped_mask])
            snapped_coords = work_pts[snapped_mask]
            non_snap_idx = np.where(~snapped_mask)[0]

            if len(non_snap_idx) > 0 and len(snapped_coords) > 0:
                smooth_r = cap * 3.0
                k_sm = min(6, len(snapped_coords))
                for _si in range(smooth_iters):
                    new_non_snap = work_pts[non_snap_idx].copy()
                    d_sm, nn_sm = nbr_tree.query(
                        work_pts[non_snap_idx], k=k_sm,
                        distance_upper_bound=smooth_r,
                    )
                    if k_sm == 1:
                        d_sm = d_sm[:, None]
                        nn_sm = nn_sm[:, None]
                    for j_ns, vi in enumerate(non_snap_idx):
                        near_snapped = nn_sm[j_ns]
                        near_snapped = near_snapped[near_snapped < len(snapped_coords)]
                        if near_snapped.size == 0:
                            continue
                        # 이웃 스냅 vertex 좌표 평균 방향으로 부드럽게
                        nbr_mean = snapped_coords[near_snapped].mean(axis=0)
                        new_non_snap[j_ns] = (
                            work_pts[vi] * 0.8 + nbr_mean * 0.2
                        )
                    work_pts[non_snap_idx] = new_non_snap

        if n_snapped_this == 0:
            # 더 이상 스냅할 vertex 없으면 조기 수렴
            log.info(
                "snap_iterative_converged",
                iteration=_iter, reason="n_snapped=0",
            )
            break

    final_n_snapped = int(sum(n_snapped_per_iter))
    log.info(
        "snap_iterative_done",
        n_iter_run=len(n_snapped_per_iter),
        final_n_snapped=final_n_snapped,
        max_displacement=max_displacement,
        cap=cap,
    )
    return work_pts, {
        "n_snapped_per_iter": n_snapped_per_iter,
        "final_n_snapped": final_n_snapped,
        "max_displacement": max_displacement,
    }
