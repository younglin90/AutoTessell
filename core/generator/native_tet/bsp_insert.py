"""Phase F — BSP-style constrained triangle insertion.

fTetWild 의 핵심 아이디어 (Hu et al. 2020, MPL-2.0): 입력 triangle 이 현재 tet
mesh 의 facet 으로 나타나지 않으면, triangle 의 평면으로 intersected tet 들을
subdivide 해서 triangle 이 강제로 tet facet set 에 포함되도록 만든다.

완전한 BSP 는 매우 복잡하므로 본 모듈은 **pragmatic subset** 구현:
    1. missing triangle 을 plane 으로 근사.
    2. plane 과 교차 (crossing) 하는 tet 들에 대해, plane 과 tet 의 각 edge
       교차점을 새 vertex 로 추가.
    3. subdivide: 교차된 tet 을 여러 개의 작은 tet 으로 분할, 새 vertex 가
       입력 triangle 위에 오도록.

실패 시 (교차 없음 / 분할 불가능) fallback 으로 barycenter seed 전략 유지.

레퍼런스
    - Hu et al. 2020 (fTetWild, MPL-2.0) §3.2 "Triangle Insertion".
    - Si 2015, "TetGen: A Delaunay-Based Quality Tetrahedral Mesh Generator"
      §4 boundary recovery.
    - Shewchuk 1998, "Tetrahedral Mesh Generation by Delaunay Refinement".

모두 독립 Python 재구현. 원본 C++ 소스 복제 없음.
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np


@dataclass
class BSPInsertResult:
    n_missing_before: int
    n_missing_after: int
    n_inserted_points: int
    n_subdivided_tets: int


def _plane_from_triangle(V: np.ndarray, tri: np.ndarray) -> tuple[np.ndarray, float]:
    """triangle 의 plane (normal, offset) 반환. plane: n·x = d."""
    a, b, c = V[tri[0]], V[tri[1]], V[tri[2]]
    n = np.cross(b - a, c - a)
    nn = float(np.linalg.norm(n))
    if nn < 1e-30:
        return np.zeros(3), 0.0
    n = n / nn
    d = float(np.dot(n, a))
    return n, d


def _edge_plane_intersection(
    p0: np.ndarray, p1: np.ndarray, n: np.ndarray, d: float,
) -> np.ndarray | None:
    """edge (p0, p1) 와 plane 의 교점. plane 이 edge 를 가로지르는 경우만 반환."""
    s0 = float(np.dot(n, p0)) - d
    s1 = float(np.dot(n, p1)) - d
    if s0 * s1 >= 0:
        return None
    t = s0 / (s0 - s1)
    return p0 + t * (p1 - p0)


def _point_in_triangle(
    p: np.ndarray, a: np.ndarray, b: np.ndarray, c: np.ndarray,
    tol: float = 1e-9,
) -> bool:
    """p 가 triangle abc 내부 (혹은 경계) 에 있는지 barycentric 체크.

    p 는 triangle 평면 위의 점이어야 정확.
    """
    v0 = c - a
    v1 = b - a
    v2 = p - a
    dot00 = float(np.dot(v0, v0))
    dot01 = float(np.dot(v0, v1))
    dot02 = float(np.dot(v0, v2))
    dot11 = float(np.dot(v1, v1))
    dot12 = float(np.dot(v1, v2))
    denom = dot00 * dot11 - dot01 * dot01
    if abs(denom) < 1e-30:
        return False
    inv = 1.0 / denom
    u = (dot11 * dot02 - dot01 * dot12) * inv
    v = (dot00 * dot12 - dot01 * dot02) * inv
    return (u >= -tol) and (v >= -tol) and (u + v <= 1.0 + tol)


def _tet_facet_keys(tets: np.ndarray) -> set[tuple[int, int, int]]:
    keys: set[tuple[int, int, int]] = set()
    for t in tets:
        a, b, c, d = int(t[0]), int(t[1]), int(t[2]), int(t[3])
        for tri in ((a, b, c), (a, b, d), (a, c, d), (b, c, d)):
            keys.add(tuple(sorted(tri)))  # type: ignore[arg-type]
    return keys


def bsp_insert_triangles_batch(
    pts: np.ndarray,
    tets: np.ndarray,
    V_surf: np.ndarray,
    F_surf: np.ndarray,
    missing_indices: np.ndarray,
    *,
    max_inserts: int = 500,
) -> tuple[np.ndarray, np.ndarray, BSPInsertResult]:
    """beta1320 (P4) — vectorized BSP triangle insertion.

    기존 bsp_insert_triangles 의 Python 이중 loop 를 numpy 로 치환:
        1) 모든 missing triangle 에 대해 plane (n, d) 배치 계산.
        2) 각 (triangle, tet) 쌍에 대해 signed distance batch.
        3) tet 의 6 edge × 각 triangle 에 대해 plane intersection batch.
        4) triangle 내부 inside test (barycentric) batch.

    단순화: 모든 missing triangle × 모든 alive tet 전수 평가. missing 이 작고
    tet 수 중규모 (≤100k) 에서 ~10-50× 가속.
    """
    pts = np.asarray(pts, dtype=np.float64).copy()
    tets = np.asarray(tets, dtype=np.int64).copy()
    V_surf = np.asarray(V_surf, dtype=np.float64)
    F_surf = np.asarray(F_surf, dtype=np.int64)
    missing_indices = np.asarray(missing_indices, dtype=np.int64).ravel()

    n_missing_before = int(missing_indices.size)
    if n_missing_before == 0 or tets.size == 0:
        return pts, tets, BSPInsertResult(0, 0, 0, 0)

    # plane: n_tri (M, 3), d_tri (M,).
    tri = F_surf[missing_indices]                 # (M, 3)
    A = V_surf[tri[:, 0]]
    B = V_surf[tri[:, 1]]
    C = V_surf[tri[:, 2]]
    n_tri = np.cross(B - A, C - A)                # (M, 3)
    d_tri = np.einsum("ij,ij->i", n_tri, A)       # (M,)
    tri_ok = np.linalg.norm(n_tri, axis=1) > 1e-20

    # tet 의 4 vertex coord.
    vv = pts[tets]                                # (T, 4, 3)
    T = tets.shape[0]
    M = tri.shape[0]

    alive = np.ones(T, dtype=bool)
    pts_list = pts.tolist()
    n_inserted = 0
    n_subdivided = 0

    # signed dist: d[i, t, k] = n_i · v_{t,k} - d_i.
    # (M, T, 4) — 메모리 제한: M*T*4 가 너무 크면 chunk.
    chunk = max(1, min(M, max(1, 200_000 // max(T, 1))))

    pair_idx = np.array(
        [[0, 1], [0, 2], [0, 3], [1, 2], [1, 3], [2, 3]], dtype=np.int64,
    )

    new_pts_global: list[np.ndarray] = []
    subdivide_set: set[int] = set()

    for chunk_start in range(0, M, chunk):
        chunk_end = min(M, chunk_start + chunk)
        sel = np.arange(chunk_start, chunk_end)
        sel = sel[tri_ok[sel]]
        if sel.size == 0:
            continue
        n_c = n_tri[sel]                          # (m, 3)
        d_c = d_tri[sel]                          # (m,)

        # (m, T, 4) signed distance.
        sd = np.einsum("ij,tkj->itk", n_c, vv) - d_c[:, None, None]
        pos = (sd > 1e-12).sum(axis=2)           # (m, T)
        neg = (sd < -1e-12).sum(axis=2)
        crosses = (pos > 0) & (neg > 0)          # (m, T)

        for li, i_global in enumerate(sel.tolist()):
            if n_inserted >= max_inserts:
                break
            if not crosses[li].any():
                continue
            tet_ids = np.where(crosses[li] & alive)[0]
            if tet_ids.size == 0:
                continue
            # 6 edge × tet_ids 의 plane intersection.
            for (i0, i1) in pair_idx.tolist():
                v0 = vv[tet_ids, i0]             # (k, 3)
                v1 = vv[tet_ids, i1]
                s0 = sd[li, tet_ids, i0]
                s1 = sd[li, tet_ids, i1]
                denom = s0 - s1
                ok = np.abs(denom) > 1e-20
                if not ok.any():
                    continue
                t = np.where(ok, s0 / np.where(ok, denom, 1.0), 0.0)
                cross_mask = ok & (s0 * s1 < 0)
                if not cross_mask.any():
                    continue
                P = v0 + t[:, None] * (v1 - v0)
                # barycentric inside test wrt triangle i_global.
                Ai = A[i_global]; Bi = B[i_global]; Ci = C[i_global]
                v_ab = Bi - Ai; v_ac = Ci - Ai
                v_ap = P - Ai
                dot00 = float(np.dot(v_ac, v_ac))
                dot01 = float(np.dot(v_ac, v_ab))
                dot11 = float(np.dot(v_ab, v_ab))
                dot02 = v_ap @ v_ac
                dot12 = v_ap @ v_ab
                inv = 1.0 / max(dot00 * dot11 - dot01 * dot01, 1e-30)
                u = (dot11 * dot02 - dot01 * dot12) * inv
                vb = (dot00 * dot12 - dot01 * dot02) * inv
                inside = cross_mask & (u >= -1e-9) & (vb >= -1e-9) & (u + vb <= 1 + 1e-9)
                if not inside.any():
                    continue
                for idx in np.where(inside)[0].tolist():
                    if n_inserted >= max_inserts:
                        break
                    pt = P[idx]
                    # 근접 중복 제거 (O(new_pts_global)).
                    dup = False
                    for existing in new_pts_global[-20:]:
                        if float(np.linalg.norm(existing - pt)) < 1e-9:
                            dup = True
                            break
                    if dup:
                        continue
                    new_pts_global.append(pt)
                    pts_list.append(pt.tolist())
                    n_inserted += 1
                    subdivide_set.add(int(tet_ids[idx]))

    for ti in subdivide_set:
        if alive[ti]:
            alive[ti] = False
            n_subdivided += 1

    out_tets = tets[alive]
    out_pts = np.asarray(pts_list, dtype=np.float64)
    return out_pts, out_tets, BSPInsertResult(
        n_missing_before=n_missing_before,
        n_missing_after=-1,
        n_inserted_points=int(n_inserted),
        n_subdivided_tets=int(n_subdivided),
    )


def bsp_insert_triangles(
    pts: np.ndarray,
    tets: np.ndarray,
    V_surf: np.ndarray,
    F_surf: np.ndarray,
    missing_indices: np.ndarray,
    *,
    max_inserts: int = 500,
) -> tuple[np.ndarray, np.ndarray, BSPInsertResult]:
    """missing surface triangle 에 대해 tet subdivide 기반 insertion.

    Args:
        pts: (N, 3) Delaunay 용 점 (surface vertex 가 [0, V_surf.shape[0]) 로 배치).
        tets: (T, 4) 현재 tet.
        V_surf: 원본 surface vertex (pts 의 첫 부분과 동일 좌표).
        F_surf: 원본 surface triangle.
        missing_indices: F_surf 의 missing triangle index.
        max_inserts: triangle 당 최대 신규 vertex 개수 상한.

    Returns:
        (new_pts, new_tets, result).
    """
    pts = np.asarray(pts, dtype=np.float64).copy()
    tets = np.asarray(tets, dtype=np.int64).copy()
    V_surf = np.asarray(V_surf, dtype=np.float64)
    F_surf = np.asarray(F_surf, dtype=np.int64)
    missing_indices = np.asarray(missing_indices, dtype=np.int64).ravel()

    n_missing_before = int(missing_indices.size)
    n_inserted = 0
    n_subdivided = 0

    if n_missing_before == 0 or tets.size == 0:
        return pts, tets, BSPInsertResult(0, 0, 0, 0)

    pts_list = pts.tolist()
    tets_list = tets.tolist()
    alive = np.ones(tets.shape[0], dtype=bool)

    for tri_idx in missing_indices:
        if n_inserted >= max_inserts:
            break
        tri = F_surf[int(tri_idx)]
        n_plane, d_plane = _plane_from_triangle(V_surf, tri)
        if float(np.linalg.norm(n_plane)) < 1e-20:
            continue

        a_tri = V_surf[tri[0]]
        b_tri = V_surf[tri[1]]
        c_tri = V_surf[tri[2]]

        # alive tet 중 plane 교차하는 것 찾기 → 각 edge 교차점을 계산, triangle
        # 내부 점만 추가.
        new_points_this_tri: list[list[float]] = []
        subdivide_targets: list[int] = []

        for ti in range(len(tets_list)):
            if not alive[ti]:
                continue
            a, b, c, dd = tets_list[ti]
            tv = [
                np.asarray(pts_list[a]),
                np.asarray(pts_list[b]),
                np.asarray(pts_list[c]),
                np.asarray(pts_list[dd]),
            ]
            # signed distance to plane.
            signs = [float(np.dot(n_plane, v)) - d_plane for v in tv]
            pos = sum(1 for s in signs if s > 1e-12)
            neg = sum(1 for s in signs if s < -1e-12)
            if pos == 0 or neg == 0:
                continue   # 평면이 tet 을 가로지르지 않음.

            # 6 edges 의 plane 교차.
            edges = [(0, 1), (0, 2), (0, 3), (1, 2), (1, 3), (2, 3)]
            added_for_this_tet = 0
            for (i0, i1) in edges:
                ip = _edge_plane_intersection(
                    tv[i0], tv[i1], n_plane, d_plane,
                )
                if ip is None:
                    continue
                # triangle 내부만 채택.
                if not _point_in_triangle(ip, a_tri, b_tri, c_tri):
                    continue
                new_points_this_tri.append(list(ip))
                added_for_this_tet += 1

            if added_for_this_tet > 0:
                subdivide_targets.append(ti)

        if not new_points_this_tri:
            continue

        # 신규 점 추가. 중복 근접 점은 제거.
        added_ids: list[int] = []
        for npt in new_points_this_tri:
            is_dup = False
            for existing_id in added_ids:
                if np.linalg.norm(
                    np.asarray(pts_list[existing_id]) - np.asarray(npt)
                ) < 1e-9:
                    is_dup = True
                    break
            if is_dup:
                continue
            new_id = len(pts_list)
            pts_list.append(list(npt))
            added_ids.append(new_id)
            n_inserted += 1

        # subdivide: 영향받은 tet 을 삭제. 새 tet 은 추가하지 않음 — 상위에서
        # 전체 re-Delaunay 실행해 새 점들과 기존 점으로 tet 재구성.
        for ti in subdivide_targets:
            if alive[ti]:
                alive[ti] = False
                n_subdivided += 1

    out_tets = np.asarray(
        [tets_list[i] for i in range(len(tets_list)) if alive[i]],
        dtype=np.int64,
    )
    out_pts = np.asarray(pts_list, dtype=np.float64)

    # missing 재평가는 caller 가 re-Delaunay 이후에 수행.
    result = BSPInsertResult(
        n_missing_before=n_missing_before,
        n_missing_after=-1,   # caller 가 채움.
        n_inserted_points=int(n_inserted),
        n_subdivided_tets=int(n_subdivided),
    )
    return out_pts, out_tets, result
