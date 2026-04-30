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

    # C-PERF-25 / beta2476 — edge_map 빌드 + 분류를 numpy lexsort 로 벡터화.
    # 3 edges per face, 6 directed edges flattened.
    src = surface_F[:, [0, 1, 2]].reshape(-1).astype(np.int64)
    dst = surface_F[:, [1, 2, 0]].reshape(-1).astype(np.int64)
    fi_flat = np.repeat(
        np.arange(surface_F.shape[0], dtype=np.int64), 3,
    )
    u = np.minimum(src, dst); v = np.maximum(src, dst)
    order = np.lexsort((v, u))
    u_s = u[order]; v_s = v[order]; f_s = fi_flat[order]
    n_v = int(surface_V.shape[0])
    n_max = max(int(u_s.max()) if u_s.size > 0 else 0,
                int(v_s.max()) if v_s.size > 0 else 0,
                n_v) + 1
    key = u_s * n_max + v_s
    # group boundaries: 새 edge group 이 시작되는 index
    diff = np.r_[True, key[1:] != key[:-1]]
    starts = np.where(diff)[0]
    sizes = np.diff(np.r_[starts, len(key)])

    cos_thresh = float(np.cos(np.deg2rad(feature_angle_deg)))
    feature_set: set[int] = set()

    # boundary (size==1) edges — 두 vertex 모두 feature.
    bnd = sizes == 1
    if bnd.any():
        bnd_starts = starts[bnd]
        feature_set.update(u_s[bnd_starts].tolist())
        feature_set.update(v_s[bnd_starts].tolist())

    # dihedral (size==2) edges — face pair angle 검사.
    dih = sizes == 2
    if dih.any():
        dih_starts = starts[dih]
        f1 = f_s[dih_starts]
        f2 = f_s[dih_starts + 1]
        cos_a = np.clip((n[f1] * n[f2]).sum(axis=1), -1.0, 1.0)
        sharp = cos_a < cos_thresh
        if sharp.any():
            sharp_starts = dih_starts[sharp]
            feature_set.update(u_s[sharp_starts].tolist())
            feature_set.update(v_s[sharp_starts].tolist())

    # size > 2 (non-manifold) — 모든 vertex 를 feature 로 (기존 동작 보존).
    nm = sizes > 2
    if nm.any():
        nm_starts = starts[nm]
        feature_set.update(u_s[nm_starts].tolist())
        feature_set.update(v_s[nm_starts].tolist())

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
    """각 vertex 의 이웃 vertex 목록 (triangle adjacency). Laplacian smoothing 용.

    C-PERF-26 / beta2477 — vectorized via flat directed-edge arrays + sort-offset
    grouping + per-vertex unique slice.
    """
    if surface_F.size == 0:
        return [[] for _ in range(n_vertices)]
    src = surface_F[:, [0, 0, 1, 1, 2, 2]].reshape(-1).astype(np.int64)
    dst = surface_F[:, [1, 2, 0, 2, 0, 1]].reshape(-1).astype(np.int64)
    order = np.argsort(src, kind="stable")
    src_s = src[order]; dst_s = dst[order]
    counts = np.bincount(src_s, minlength=n_vertices)
    offsets = np.concatenate(([0], np.cumsum(counts).astype(np.int64)))
    return [
        np.unique(dst_s[offsets[i]:offsets[i + 1]]).tolist()
        for i in range(n_vertices)
    ]


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

        # C-PERF-13 / beta2436 — coarse 거리 pre-filter (대부분 vert 가 cap+ 밖).
        # KD-tree 가 search_r = cap + max_tri_extent 로 query 했으므로,
        # 가장 가까운 centroid 거리 > cap + max_tri_extent 면 surface 도 cap 밖.
        # 이 조건은 cand 가 비어 있을 때 (line 370-374) 이미 처리되지만,
        # cand 비어 있지 않아도 모든 cand 의 centroid distance > cap 이면 skip.
        for i in range(len(work_pts)):
            cand = nn_idx[i]
            cand = cand[cand < len(tri_centroids)]
            if cand.size == 0:
                continue
            # min coarse distance pre-check — centroid 거리가 cap+max_tri_extent 미만이지만
            # 만약 모두 cap+max_tri_extent 를 초과하면 (KD-tree 결과의 안전 hint) skip.
            # 이 check 는 거리만 1 number 비교 — 매우 빠름.
            cand_dists = dists_coarse[i][:cand.size]
            if (cand_dists > cap + max_tri_extent).all():
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

        # C-PERF-9 / beta2426 — early-exit: snap 횟수 < 5 또는 displacement
        # 가 cap × 0.05 이하면 다음 iter 추가 효과 미미.
        if n_snapped_this < max(5, int(0.001 * len(work_pts))):
            break
        if max_displacement < cap * 0.05:
            break

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


# ---------------------------------------------------------------------------
# WWW7 (beta2130) — feature edge snap (snappyHexMesh nFeatureSnapIter style)
# ---------------------------------------------------------------------------


def _extract_feature_edge_segments(
    surface_V: np.ndarray,
    surface_F: np.ndarray,
    feature_angle_deg: float = 30.0,
) -> np.ndarray:
    """Sharp dihedral edges → (M, 2, 3) segment endpoint array.

    Edges whose adjacent face dihedral > feature_angle_deg are "feature edges."
    Also includes boundary edges (open mesh).

    Returns: float64 array shape (M, 2, 3). Empty (0,2,3) if none found.
    """
    if surface_V.size == 0 or surface_F.size == 0:
        return np.zeros((0, 2, 3), dtype=np.float64)

    sV = np.asarray(surface_V, dtype=np.float64)
    sF = np.asarray(surface_F, dtype=np.int64)

    # face normals
    v0 = sV[sF[:, 0]]; v1 = sV[sF[:, 1]]; v2 = sV[sF[:, 2]]
    nrm = np.cross(v1 - v0, v2 - v0)
    nlen = np.linalg.norm(nrm, axis=1, keepdims=True)
    nrm = np.where(nlen > 1e-30, nrm / np.where(nlen > 1e-30, nlen, 1.0), 0.0)

    # C-PERF-14 / beta2450 — vectorized edge_map build (이전 Python loop).
    # 60k face × 3 edge = 180k entries, Python dict.setdefault 의 overhead 큼.
    # 이제 numpy lexsort 로 sorted-by-edge 배열 생성 → 그룹 boundary 만 탐색.
    n_faces = sF.shape[0]
    edges_per_face = np.stack(
        [sF[:, [0, 1]], sF[:, [1, 2]], sF[:, [2, 0]]],
        axis=1,
    ).reshape(-1, 2)  # (3*n_faces, 2)
    edges_canon = np.sort(edges_per_face, axis=1)  # canonical (min, max).
    face_ids = np.arange(n_faces, dtype=np.int64).repeat(3)  # (3*n_faces,)
    # Sort by edge for grouping.
    ord_idx = np.lexsort((edges_canon[:, 1], edges_canon[:, 0]))
    sorted_edges = edges_canon[ord_idx]
    sorted_faces = face_ids[ord_idx]
    # Find run boundaries (where edge changes).
    eq_prev = (
        np.diff(sorted_edges[:, 0]) != 0
    ) | (
        np.diff(sorted_edges[:, 1]) != 0
    )
    run_starts = np.concatenate(([0], np.where(eq_prev)[0] + 1))
    run_ends = np.concatenate((run_starts[1:], [len(sorted_edges)]))
    edge_map: dict[tuple[int, int], list[int]] = {}
    for s, e in zip(run_starts.tolist(), run_ends.tolist()):
        key = (int(sorted_edges[s, 0]), int(sorted_edges[s, 1]))
        edge_map[key] = sorted_faces[s:e].tolist()

    cos_thresh = float(np.cos(np.deg2rad(feature_angle_deg)))
    segs: list[tuple[np.ndarray, np.ndarray]] = []
    # P2.5 / beta2583 — per-segment sharpness weight.
    #   boundary edge → weight 1.5 (강제 보존).
    #   dihedral edge → 1.0 + (1.0 - cos_a) — cos_a 낮을수록 (sharp 할수록) 가중.
    #   sharpness=2.0 → 90° dihedral, sharpness=3.0 → 180° (peak).
    seg_weights: list[float] = []
    for (a, b), fl in edge_map.items():
        is_feature = False
        sharpness = 1.0
        if len(fl) == 1:
            is_feature = True  # boundary edge
            sharpness = 1.5
        elif len(fl) == 2:
            cos_a = float(np.clip(np.dot(nrm[fl[0]], nrm[fl[1]]), -1.0, 1.0))
            if cos_a < cos_thresh:
                is_feature = True
                sharpness = 1.0 + (1.0 - cos_a)
        if is_feature:
            segs.append((sV[a], sV[b]))
            seg_weights.append(sharpness)

    if not segs:
        return np.zeros((0, 2, 3), dtype=np.float64)

    seg_arr = np.array([[s[0], s[1]] for s in segs], dtype=np.float64)
    # Stash weights as attribute on returned array. snap_to_feature_edges
    # 가 _seg_weight 속성으로 access. ndarray 자체에 attr 부여 불가 →
    # contiguous structured ndarray 대신 flag 처럼 설정 시도.
    try:
        seg_arr_view = seg_arr.view()
        seg_arr_view.setflags(write=False)
    except Exception:
        pass
    # Carry weights via attribute on segs object using a subclass.
    class _SegArrWithWeights(np.ndarray):
        def __new__(cls, src: np.ndarray, weights: np.ndarray) -> "_SegArrWithWeights":
            obj = np.asarray(src).view(cls)
            obj._seg_weight = weights  # type: ignore[attr-defined]
            return obj

        def __array_finalize__(self, obj: object | None) -> None:
            if obj is None:
                return
            self._seg_weight = getattr(obj, "_seg_weight", None)  # type: ignore[attr-defined]

    return _SegArrWithWeights(seg_arr, np.asarray(seg_weights, dtype=np.float64))


def _closest_point_on_segment(
    P: np.ndarray, A: np.ndarray, B: np.ndarray,
) -> tuple[np.ndarray, float]:
    """Closest point on line segment AB to point P. Returns (pt, dist)."""
    AB = B - A
    len2 = float(AB @ AB)
    if len2 < 1e-30:
        d = float(np.linalg.norm(P - A))
        return A.copy(), d
    t = float(np.clip((P - A) @ AB / len2, 0.0, 1.0))
    pt = A + t * AB
    return pt, float(np.linalg.norm(P - pt))


def snap_to_feature_edges(
    hex_pts: np.ndarray,
    hex_cells: np.ndarray,
    surface_V: np.ndarray,
    surface_F: np.ndarray,
    *,
    max_dist: float | None = None,
    top_k: int = 200,
    feature_angle_deg: float = 30.0,
) -> tuple[np.ndarray, dict]:
    """WWW7 — snap worst-aligned hex verts onto feature edges.

    Algorithm (snappyHexMesh nFeatureSnapIter style):
        1. Extract feature edges from surface (dihedral > feature_angle_deg).
        2. For each hex vert, find nearest feature edge & closest point.
        3. Select top_k verts with smallest distance to their nearest feature edge.
        4. Move each candidate only if it does not worsen incident cell skewness.

    Args:
        hex_pts: (N, 3) hex mesh vertices.
        hex_cells: (C, 8) hex cell vertex indices.
        surface_V / surface_F: input surface for feature edge extraction.
        max_dist: snap distance threshold. Default = 0.01 * bbox_diag.
        top_k: maximum number of vertices to snap (worst-distance first).
        feature_angle_deg: dihedral threshold for feature edge detection.

    Returns:
        (new_hex_pts, stats) where stats has n_snapped, n_rejected_quality, n_no_feature.
    """
    import os  # noqa: PLC0415
    if os.environ.get("AUTO_TESSELL_WWW7_OFF", "").strip().lower() in ("1", "true", "yes"):
        return np.asarray(hex_pts, dtype=np.float64).copy(), {
            "n_snapped": 0, "n_rejected_quality": 0, "n_no_feature": 0, "skipped": "env_off",
        }

    work = np.asarray(hex_pts, dtype=np.float64).copy()
    cells = np.asarray(hex_cells, dtype=np.int64)

    stats: dict = {"n_snapped": 0, "n_rejected_quality": 0, "n_no_feature": 0}

    if work.shape[0] < 100:
        stats["skipped"] = "too_few_verts"
        return work, stats

    # Step 1 — extract feature edges
    segs = _extract_feature_edge_segments(surface_V, surface_F, feature_angle_deg)
    if segs.shape[0] == 0:
        stats["n_no_feature"] = int(work.shape[0])
        stats["skipped"] = "no_feature_edges"
        return work, stats

    # bbox_diag for default max_dist
    bmin = work.min(axis=0); bmax = work.max(axis=0)
    bbox_diag = float(np.linalg.norm(bmax - bmin)) + 1e-30
    if max_dist is None or max_dist <= 0.0:
        max_dist = 0.01 * bbox_diag

    # Step 2 — for each vert, find nearest feature edge via segment midpoints KDTree
    seg_A = segs[:, 0, :]  # (M, 3)
    seg_B = segs[:, 1, :]  # (M, 3)
    seg_mids = (seg_A + seg_B) / 2.0

    # coarse filter: k nearest segment midpoints
    k_coarse = min(4, segs.shape[0])
    try:
        from core.utils.kdtree import NumpyKDTree  # noqa: PLC0415
        mid_tree = NumpyKDTree(seg_mids)
    except Exception as exc:
        log.warning("www7_kdtree_failed", error=str(exc))
        return work, stats

    # max seg half-length for search radius
    half_lens = np.linalg.norm(seg_B - seg_A, axis=1) / 2.0
    max_half = float(half_lens.max()) if half_lens.size > 0 else 0.0
    search_r = max_dist + max_half + 1e-8

    dists_coarse, nn_idx = mid_tree.query(work, k=k_coarse, distance_upper_bound=search_r)
    if k_coarse == 1:
        dists_coarse = dists_coarse[:, None]
        nn_idx = nn_idx[:, None]

    n_verts = work.shape[0]
    best_dist = np.full(n_verts, np.inf)
    best_snap = np.empty((n_verts, 3), dtype=np.float64)
    # P2.5 / beta2583 — per-vert chosen seg index 추적해 weight 회수.
    best_seg_idx = np.full(n_verts, -1, dtype=np.int64)

    for i in range(n_verts):
        cand_segs = nn_idx[i]
        cand_segs = cand_segs[cand_segs < segs.shape[0]]
        if cand_segs.size == 0:
            continue
        P = work[i]
        bd2 = np.inf
        bp = None
        bsi = -1
        for si in cand_segs:
            pt, d = _closest_point_on_segment(P, seg_A[si], seg_B[si])
            if d < bd2:
                bd2 = d
                bp = pt
                bsi = int(si)
        if bp is not None and bd2 <= max_dist:
            best_dist[i] = bd2
            best_snap[i] = bp
            best_seg_idx[i] = bsi

    # Step 3 — select top_k candidates (smallest dist, dist < max_dist).
    # P2.5 / beta2583 — sharpness-weighted score: score = dist / weight.
    #   sharper edge → higher weight → 작은 score → 우선 채택.
    eligible = np.where(best_dist < max_dist)[0]
    if eligible.size == 0:
        stats["n_no_feature"] = n_verts
        return work, stats

    seg_weights_attr = getattr(segs, "_seg_weight", None)
    if seg_weights_attr is not None and len(seg_weights_attr) == segs.shape[0]:
        _w = np.asarray(seg_weights_attr, dtype=np.float64)
        score_eligible = best_dist[eligible] / np.maximum(_w[best_seg_idx[eligible]], 1e-30)
    else:
        score_eligible = best_dist[eligible]

    if eligible.size > top_k:
        order = np.argsort(score_eligible)
        eligible = eligible[order[:top_k]]

    # Step 4 — build vert → incident cells map for quality guard.
    # C-PERF-27 / beta2478 — vectorize via flat sort + bincount-offset slicing.
    if cells.shape[0] == 0:
        vert_cells: list[list[int]] = [[] for _ in range(n_verts)]
    else:
        flat_v_vc = cells.reshape(-1).astype(np.int64)
        flat_c_vc = np.repeat(np.arange(cells.shape[0], dtype=np.int64), 8)
        order_vc = np.argsort(flat_v_vc, kind="stable")
        sorted_v_vc = flat_v_vc[order_vc]
        sorted_c_vc = flat_c_vc[order_vc]
        counts_vc = np.bincount(sorted_v_vc, minlength=n_verts)
        offs_vc = np.concatenate(([0], np.cumsum(counts_vc).astype(np.int64)))
        vert_cells = [
            sorted_c_vc[offs_vc[i]:offs_vc[i + 1]].tolist()
            for i in range(n_verts)
        ]

    def _hex_skewness_cells(pts: np.ndarray, cids: list[int]) -> float:
        """Approximate max skewness over a set of hex cells (centroid-based)."""
        if not cids:
            return 0.0
        max_sk = 0.0
        for ci in cids:
            verts = pts[cells[ci]]  # (8, 3)
            cen = verts.mean(axis=0)
            # Face skewness: for each of 6 hex faces compute face centroid deviation
            for face_local in _HEX_FACES_LOCAL:
                fv = verts[list(face_local)]
                fc = fv.mean(axis=0)
                ec = cen  # cell centroid
                # approximate: skewness ≈ |fc - ec| / cell_size
                face_diag = float(np.linalg.norm(fv[2] - fv[0]))
                if face_diag < 1e-30:
                    continue
                sk = float(np.linalg.norm(fc - ec)) / (face_diag + 1e-30)
                if sk > max_sk:
                    max_sk = sk
        return max_sk

    _HEX_FACES_LOCAL = (
        (0, 3, 2, 1), (4, 5, 6, 7), (0, 1, 5, 4),
        (3, 7, 6, 2), (0, 4, 7, 3), (1, 2, 6, 5),
    )

    for vi in eligible:
        inc = vert_cells[int(vi)]
        if not inc:
            continue
        prev_sk = _hex_skewness_cells(work, inc)
        orig = work[vi].copy()
        work[vi] = best_snap[vi]
        new_sk = _hex_skewness_cells(work, inc)
        if new_sk > prev_sk + 1e-6:
            work[vi] = orig  # revert
            stats["n_rejected_quality"] += 1
        else:
            stats["n_snapped"] += 1

    log.info(
        "native_hex_www7_feature_snap",
        n_feature_segs=int(segs.shape[0]),
        n_eligible=int(eligible.size),
        **{k: v for k, v in stats.items()},
        max_dist=round(max_dist, 6),
    )
    return work, stats
