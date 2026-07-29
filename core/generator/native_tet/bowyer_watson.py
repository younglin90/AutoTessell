"""Round 35 — Bowyer-Watson incremental Delaunay insertion.

Full re-Delaunay 대신 신규 점 p 를 기존 tet mesh 에 점진 삽입:

    1. "bad tets" = p 가 circumsphere 내부인 tet 의 집합 (cavity).
    2. cavity 의 boundary face 를 수집.
    3. cavity 제거 + 각 boundary face 를 p 와 연결해 새 tet 생성.

평균 O(log T) per insertion (점 찾기 + 확장). 한 번에 K 점 추가 시 O(K log T)
대비 full re-Delaunay 의 O((N+K) log(N+K)) 보다 훨씬 빠름.

레퍼런스 (standard textbook algorithm, 1980s):
    - Bowyer 1981, "Computing Dirichlet Tessellations".
    - Watson 1981, "Computing the n-dimensional Delaunay Tessellation with
      Application to Voronoi Polytopes".
    - Shewchuk 1998, "Tetrahedral Mesh Generation by Delaunay Refinement".

본 구현은 standard algorithm 의 Python 재구현. 특정 라이브러리 코드 복제 없음.
"""
from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

import numpy as np


@dataclass
class BWInsertResult:
    n_inserted: int
    n_cavity_total: int
    n_new_tets_total: int


def _in_circumsphere(
    p: np.ndarray, a: np.ndarray, b: np.ndarray, c: np.ndarray, d: np.ndarray,
    *, tol: float = 1e-14,
) -> bool:
    """p 가 tet abcd 의 circumsphere 내부인지.

    Shewchuk §4.3 — positive oriented tet 기준 5×5 determinant sign.
    """
    ax, ay, az = a - p
    bx, by, bz = b - p
    cx, cy, cz = c - p
    dx, dy, dz = d - p

    alift = ax * ax + ay * ay + az * az
    blift = bx * bx + by * by + bz * bz
    clift = cx * cx + cy * cy + cz * cz
    dlift = dx * dx + dy * dy + dz * dz

    # 3x3 sub-determinants.
    def _det3(r0, r1, r2, s0, s1, s2, t0, t1, t2) -> float:
        return (
            r0 * (s1 * t2 - s2 * t1)
            - r1 * (s0 * t2 - s2 * t0)
            + r2 * (s0 * t1 - s1 * t0)
        )

    det = (
        alift * _det3(bx, by, bz, cx, cy, cz, dx, dy, dz)
        - blift * _det3(ax, ay, az, cx, cy, cz, dx, dy, dz)
        + clift * _det3(ax, ay, az, bx, by, bz, dx, dy, dz)
        - dlift * _det3(ax, ay, az, bx, by, bz, cx, cy, cz)
    )

    # tet orientation 에 따라 sign 반전. positive oriented 에서 p 내부 → det > 0,
    # negative oriented 에서는 det < 0 이 내부. 부호 무관 robust 체크:
    orient = float(np.dot(b - a, np.cross(c - a, d - a)))
    if orient > 0:
        return det > tol
    elif orient < 0:
        return det < -tol
    return False


def _tet_circumsphere_batch(
    pts: np.ndarray, tets: np.ndarray, p: np.ndarray,
) -> np.ndarray:
    """N 개 tet 각각에 대해 p 가 circumsphere 내부인지 bool array."""
    tets = np.asarray(tets, dtype=np.int64)
    if tets.size == 0:
        return np.zeros(0, dtype=bool)
    A = pts[tets[:, 0]] - p
    B = pts[tets[:, 1]] - p
    C = pts[tets[:, 2]] - p
    D = pts[tets[:, 3]] - p

    al = np.einsum("ij,ij->i", A, A)
    bl = np.einsum("ij,ij->i", B, B)
    cl = np.einsum("ij,ij->i", C, C)
    dl = np.einsum("ij,ij->i", D, D)

    # 3x3 det helpers.
    def det3(M):
        return (
            M[:, 0, 0] * (M[:, 1, 1] * M[:, 2, 2] - M[:, 1, 2] * M[:, 2, 1])
            - M[:, 0, 1] * (M[:, 1, 0] * M[:, 2, 2] - M[:, 1, 2] * M[:, 2, 0])
            + M[:, 0, 2] * (M[:, 1, 0] * M[:, 2, 1] - M[:, 1, 1] * M[:, 2, 0])
        )

    M_bcd = np.stack([B, C, D], axis=1)
    M_acd = np.stack([A, C, D], axis=1)
    M_abd = np.stack([A, B, D], axis=1)
    M_abc = np.stack([A, B, C], axis=1)

    det = (
        al * det3(M_bcd)
        - bl * det3(M_acd)
        + cl * det3(M_abd)
        - dl * det3(M_abc)
    )

    # per-tet orientation 에 따라 부호 반전.
    AA = pts[tets[:, 0]]
    BB = pts[tets[:, 1]]
    CC = pts[tets[:, 2]]
    DD = pts[tets[:, 3]]
    orient = np.einsum("ij,ij->i", BB - AA, np.cross(CC - AA, DD - AA))
    # 통일된 부호 (orient 와 det 의 곱이 양수) 이면 내부.
    return (orient * det) > 1e-14


def _boundary_faces_of_cavity(
    tets: np.ndarray, cavity_mask: np.ndarray,
) -> list[tuple[int, int, int]]:
    """cavity 의 boundary face = cavity tet 에만 속한 face.

    내부 face (cavity 내 2 tet 공유) 는 제외.
    C-PERF-83 / beta2534 — packed int key + np.unique count 로 벡터화.
    """
    tets = np.asarray(tets, dtype=np.int64)
    cavity_mask = np.asarray(cavity_mask, dtype=bool)
    cav = tets[cavity_mask]
    if cav.size == 0:
        return []
    faces = np.stack([
        cav[:, [0, 1, 2]], cav[:, [0, 1, 3]],
        cav[:, [0, 2, 3]], cav[:, [1, 2, 3]],
    ], axis=1).reshape(-1, 3)
    fs = np.sort(faces, axis=1)
    M = int(fs.max()) + 1
    keys = fs[:, 0] * M * M + fs[:, 1] * M + fs[:, 2]
    _, inv, counts = np.unique(keys, return_inverse=True, return_counts=True)
    bnd_idx = np.where(counts[inv] == 1)[0]
    bnd = fs[bnd_idx]
    return [(int(t[0]), int(t[1]), int(t[2])) for t in bnd]


def bowyer_watson_insert(
    pts: np.ndarray,
    tets: np.ndarray,
    new_points: np.ndarray,
    *,
    max_cavity_size: int = 500,
    protected_edges: set[tuple[int, int]] | None = None,
    protected_faces: Sequence[Sequence[int]] | None = None,
) -> tuple[np.ndarray, np.ndarray, BWInsertResult]:
    """신규 점들을 순차적으로 incremental insertion.

    각 점 p:
      1. cavity = {ti : p ∈ circumsphere(tet_ti)}.
      2. boundary = cavity 의 외곽 face.
      3. cavity tet 제거, boundary face 에 p 연결해 새 tet 추가.

    Args:
        pts: (N, 3) — 기존 점 + 새 점 뒤에 붙임.
        tets: (T, 4) — 기존 Delaunay.
        new_points: (K, 3) — 삽입할 점들.
        max_cavity_size: cavity 크기 상한 — 초과 시 해당 점 skip (degenerate
          방지).
        protected_faces: 이미 direct tet face 로 회복된 입력 surface face.
          후보가 이 key 를 정확한 owner-consistent subdivision 으로 유지하지
          못하면 point insertion 전체를 revert 한다. 아직 없는 source face 는
          이 helper 가 거짓 보존 주장으로 취급하지 않는다.

    Returns:
        (new_pts, new_tets, result).
    """
    pts_list = np.asarray(pts, dtype=np.float64).tolist()
    tets_cur = np.asarray(tets, dtype=np.int64).copy()
    new_points = np.asarray(new_points, dtype=np.float64)

    n_inserted = 0
    n_cavity_total = 0
    n_new_total = 0

    # Round 60: tet adjacency 구축 — 매 점 삽입 전 갱신. beta940 (R87/R88):
    # Python dict 대신 numpy argsort 기반으로 O(T log T) 벡터 빌드.
    def _tet_neighbors(T: np.ndarray) -> list[list[int]]:
        if T.shape[0] == 0:
            return []
        # 각 tet 의 4 face (정렬된 triplet).
        t = T
        faces = np.stack([
            t[:, [0, 1, 2]], t[:, [0, 1, 3]],
            t[:, [0, 2, 3]], t[:, [1, 2, 3]],
        ], axis=1)   # (T, 4, 3)
        faces_sorted = np.sort(faces, axis=2)
        flat = faces_sorted.reshape(-1, 3)          # (4T, 3)
        tet_of_face = np.repeat(np.arange(T.shape[0], dtype=np.int64), 4)
        # lexsort by (c, b, a).
        order = np.lexsort((flat[:, 2], flat[:, 1], flat[:, 0]))
        sf = flat[order]
        st = tet_of_face[order]
        # 인접 쌍 중 동일 face.
        eq = np.all(sf[:-1] == sf[1:], axis=1)
        pair_i = np.where(eq)[0]
        a_ids = st[pair_i]
        b_ids = st[pair_i + 1]
        # C-PERF-42 / beta2493 — flat sort + bincount-offset 으로 nbrs 빌드.
        n_tets = int(T.shape[0])
        if a_ids.size == 0:
            return [[] for _ in range(n_tets)]
        # 각 (a,b) pair 는 양 방향 (a→b, b→a) 으로 분해.
        src = np.concatenate([a_ids, b_ids])
        dst = np.concatenate([b_ids, a_ids])
        order_n = np.argsort(src, kind="stable")
        src_s = src[order_n]; dst_s = dst[order_n]
        counts_n = np.bincount(src_s, minlength=n_tets)
        offs_n = np.concatenate(([0], np.cumsum(counts_n).astype(np.int64)))
        return [
            dst_s[offs_n[i]:offs_n[i + 1]].tolist()
            for i in range(n_tets)
        ]

    def _single_circumsphere_test(T: np.ndarray, ti: int, p: np.ndarray, pts_arr) -> bool:
        a = pts_arr[T[ti, 0]]; b = pts_arr[T[ti, 1]]
        c = pts_arr[T[ti, 2]]; d = pts_arr[T[ti, 3]]
        return _in_circumsphere(p, a, b, c, d)

    for k in range(new_points.shape[0]):
        p = new_points[k]
        cur_pts = np.asarray(pts_list, dtype=np.float64)
        if tets_cur.shape[0] == 0:
            break

        # seed tet 찾기: 가장 가까운 centroid.
        centroids = cur_pts[tets_cur].mean(axis=1)
        seed = int(np.argmin(np.linalg.norm(centroids - p, axis=1)))

        # flood: seed 부터 BFS, circumsphere 포함 tet 만 확장.
        nbrs = _tet_neighbors(tets_cur)
        mask = np.zeros(tets_cur.shape[0], dtype=bool)
        if _single_circumsphere_test(tets_cur, seed, p, cur_pts):
            mask[seed] = True
            queue = [seed]
            while queue:
                ti = queue.pop()
                for nb in nbrs[ti]:
                    if not mask[nb] and _single_circumsphere_test(tets_cur, nb, p, cur_pts):
                        mask[nb] = True
                        queue.append(nb)
        n_cav = int(mask.sum())
        if n_cav == 0:
            continue
        if n_cav > max_cavity_size:
            continue

        # Round 58: cavity 가 protected edge 를 내부 (boundary 가 아닌) 로
        # 삼키면 삽입 거부. 외부 면에 protected edge 가 남아 있으면 OK.
        if protected_edges:
            cavity_ids = np.where(mask)[0]
            # cavity 내부 edge 집합.
            interior_pair_counts: dict[tuple[int, int], int] = {}
            for ti in cavity_ids:
                a, b, c, d = (int(x) for x in tets_cur[ti])
                for u, v in ((a, b), (a, c), (a, d), (b, c), (b, d), (c, d)):
                    k = (u, v) if u < v else (v, u)
                    interior_pair_counts[k] = interior_pair_counts.get(k, 0) + 1
            # boundary 외곽 face 의 edge set.
            b_faces = _boundary_faces_of_cavity(tets_cur, mask)
            boundary_edges: set[tuple[int, int]] = set()
            for fk in b_faces:
                a_, b_, c_ = fk
                for u_, v_ in ((a_, b_), (a_, c_), (b_, c_)):
                    boundary_edges.add((u_, v_) if u_ < v_ else (v_, u_))
            # protected edge 가 cavity interior 에 속하고 boundary 에 없으면 거부.
            reject = False
            for pe in protected_edges:
                if pe in interior_pair_counts and pe not in boundary_edges:
                    reject = True
                    break
            if reject:
                continue

        boundary = _boundary_faces_of_cavity(tets_cur, mask)
        if not boundary:
            continue

        # 점 추가.
        new_pid = len(pts_list)
        pts_list.append(p.tolist())

        # cavity 제거.
        keep_mask = ~mask
        kept = tets_cur[keep_mask]

        # 새 tet 생성: 각 boundary face + p.
        new_tets_arr = np.array(
            [(f[0], f[1], f[2], new_pid) for f in boundary],
            dtype=np.int64,
        )

        # volume sign 검사: 일부 face orientation 이 음수 부피를 줄 수 있음 —
        # 이 경우 face 의 v1, v2 swap.
        A = np.asarray(pts_list)[new_tets_arr[:, 0]]
        B = np.asarray(pts_list)[new_tets_arr[:, 1]]
        C = np.asarray(pts_list)[new_tets_arr[:, 2]]
        D = np.asarray(pts_list)[new_tets_arr[:, 3]]
        vol6 = np.einsum("ij,ij->i", B - A, np.cross(C - A, D - A))
        flip = vol6 < 0
        # flip 이면 face orientation 바꿔 부피 양수화.
        tmp = new_tets_arr[flip, 1].copy()
        new_tets_arr[flip, 1] = new_tets_arr[flip, 2]
        new_tets_arr[flip, 2] = tmp

        candidate_tets = np.vstack([kept, new_tets_arr])
        if protected_faces is not None and len(protected_faces) > 0:
            from core.generator.native_tet.duwang_constraint_subdivision_l1 import (
                audit_constraint_face_subdivision_l1,
            )

            before_keys = {
                tuple(sorted(int(tet[index]) for index in range(4) if index != omitted))
                for tet in tets_cur
                for omitted in range(4)
            }
            direct_faces = tuple(
                face
                for face in protected_faces
                if tuple(sorted(int(vertex) for vertex in face)) in before_keys
            )
            if direct_faces:
                protection = audit_constraint_face_subdivision_l1(
                    pts_list, tets_cur.tolist(), candidate_tets.tolist(), direct_faces
                )
                if not protection.accepted:
                    pts_list.pop()
                    continue

        tets_cur = candidate_tets

        n_inserted += 1
        n_cavity_total += n_cav
        n_new_total += int(new_tets_arr.shape[0])

    return (
        np.asarray(pts_list, dtype=np.float64),
        tets_cur,
        BWInsertResult(
            n_inserted=n_inserted,
            n_cavity_total=n_cavity_total,
            n_new_tets_total=n_new_total,
        ),
    )
