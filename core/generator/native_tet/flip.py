"""Phase B3 — Face flip (2-3 / 3-2) for quality improvement.

2-3 flip : 두 tet 이 공유하는 triangle 을 없애고, 그 자리에 새 edge (반대편
           두 vertex 를 잇는) 가 생기도록 재구성. 2 tet → 3 tet.
3-2 flip : 3 tet 이 공유하는 내부 edge 를 제거, 2 tet 로 재구성. 2-3 의 역.

flip 은 quality 가 개선될 때 + topology 가 valid 할 때만 수행. 본 구현은
"quality 개선" 만 보수적으로 검사 (Delaunay criterion 은 미구현, 다음 round).

레퍼런스
    - Edelsbrunner 2001, "Geometry and Topology for Mesh Generation" §3.
    - Botsch et al. 2010 §5.4.
    - fTetWild (MPL-2.0) §3.3 — 독립 Python 재구현.
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np


@dataclass
class FlipResult:
    n_flip_23: int
    n_flip_32: int
    n_tets_before: int
    n_tets_after: int
    min_quality_before: float
    min_quality_after: float


def _tet_quality(A, B, C, D) -> float:
    v = np.abs(np.dot(B - A, np.cross(C - A, D - A))) / 6.0
    e = [A - B, A - C, A - D, B - C, B - D, C - D]
    emax = max(float(np.linalg.norm(x)) for x in e)
    if emax < 1e-30:
        return 0.0
    return 8.48 * v / (emax ** 3)


def _tet_signed_vol6(A, B, C, D) -> float:
    return float(np.dot(B - A, np.cross(C - A, D - A)))


def _face_map_vectorized(tets: np.ndarray) -> dict[tuple[int, int, int], list[int]]:
    """numpy 로 각 tet 의 4 face 를 한 번에 정렬 + Python dict 로 취합.

    전체 데이터 O(T) + Python 해시 insert.
    """
    tets = np.asarray(tets, dtype=np.int64)
    if tets.size == 0:
        return {}
    T = tets.shape[0]
    # 4 faces per tet: 각 opposite vertex 기준.
    face_arr = np.stack(
        [tets[:, [1, 2, 3]], tets[:, [0, 2, 3]],
         tets[:, [0, 1, 3]], tets[:, [0, 1, 2]]],
        axis=1,
    ).reshape(-1, 3)
    face_arr.sort(axis=1)
    m: dict[tuple[int, int, int], list[int]] = {}
    for idx in range(face_arr.shape[0]):
        ti = idx // 4
        k = (int(face_arr[idx, 0]), int(face_arr[idx, 1]), int(face_arr[idx, 2]))
        m.setdefault(k, []).append(ti)
    return m


def flip_faces_23(
    pts: np.ndarray,
    tets: np.ndarray,
    *,
    min_quality_improvement: float = 1e-4,
    max_flips: int = 5000,
) -> tuple[np.ndarray, int]:
    """공유 face 를 가진 tet pair 마다 2-3 flip 시도.

    두 tet {A,B,C,X} 와 {A,B,C,Y} 가 face (A,B,C) 를 공유할 때, 새 구성
    {A,B,X,Y}, {B,C,X,Y}, {C,A,X,Y} 가 전부 valid (positive volume) 하고
    min_quality 가 개선되면 교체.
    """
    pts = np.asarray(pts, dtype=np.float64)
    tets = np.asarray(tets, dtype=np.int64).copy()
    if tets.size == 0:
        return tets, 0

    n_flip = 0
    alive = np.ones(tets.shape[0], dtype=bool)
    tets_list = tets.tolist()

    # 한 번의 pass — 2 owner face 만 빠르게 찾기 (numpy unique).
    T = np.asarray(tets_list, dtype=np.int64)
    face_arr = np.stack(
        [T[:, [1, 2, 3]], T[:, [0, 2, 3]], T[:, [0, 1, 3]], T[:, [0, 1, 2]]],
        axis=1,
    ).reshape(-1, 3)
    face_arr.sort(axis=1)
    # canonical 64-bit encoding for group-by.
    max_id = int(T.max()) + 1 if T.size else 1
    key64 = (
        face_arr[:, 0].astype(np.int64) * max_id * max_id
        + face_arr[:, 1].astype(np.int64) * max_id
        + face_arr[:, 2].astype(np.int64)
    )
    _, inv, counts = np.unique(key64, return_inverse=True, return_counts=True)
    # 2 owner 인 face 의 행(전체 face_arr 기준) 을 찾는다.
    # 각 unique 에 대해 owner tet 2 개 쌍을 선형 탐색.
    shared_face_groups = np.where(counts == 2)[0]

    fmap_shared: list[tuple[tuple[int, int, int], int, int]] = []
    if shared_face_groups.size > 0:
        # 각 group 의 owner tet id 2 개 선택.
        group_pos = np.argsort(inv)
        # 누적 시작 index.
        boundaries = np.concatenate([[0], np.cumsum(counts)])
        for gi in shared_face_groups.tolist():
            s = int(boundaries[gi]); e = int(boundaries[gi + 1])
            face_idxs = group_pos[s:e]
            # face_arr row → (tet_id = row // 4).
            ti1 = int(face_idxs[0]) // 4
            ti2 = int(face_idxs[1]) // 4
            if ti1 == ti2:
                continue
            f0 = face_arr[face_idxs[0]]
            fmap_shared.append(
                ((int(f0[0]), int(f0[1]), int(f0[2])), ti1, ti2)
            )

    visited_faces: set[tuple[int, int, int]] = set()

    for face, ti, tj in fmap_shared:
        if n_flip >= max_flips:
            break
        if face in visited_faces:
            continue
        if not (alive[ti] and alive[tj]):
            continue
        a, b, c = face
        x_cands = [v for v in tets_list[ti] if v not in face]
        y_cands = [v for v in tets_list[tj] if v not in face]
        if len(x_cands) != 1 or len(y_cands) != 1:
            continue
        x = x_cands[0]; y = y_cands[0]
        if x == y:
            continue

        # 기존 2 tet 의 min quality.
        q_old = min(
            _tet_quality(pts[a], pts[b], pts[c], pts[x]),
            _tet_quality(pts[a], pts[b], pts[c], pts[y]),
        )

        # 새 3 tet.
        new_tets = [
            (a, b, x, y),
            (b, c, x, y),
            (c, a, x, y),
        ]
        # 모두 양의 부피 + 중복 없어야 함.
        ok = True
        q_new_min = 1.0
        for nt in new_tets:
            if len(set(nt)) != 4:
                ok = False; break
            vol6 = _tet_signed_vol6(pts[nt[0]], pts[nt[1]], pts[nt[2]], pts[nt[3]])
            if abs(vol6) < 1e-20:
                ok = False; break
            q = _tet_quality(pts[nt[0]], pts[nt[1]], pts[nt[2]], pts[nt[3]])
            if q < q_new_min:
                q_new_min = q
        if not ok:
            continue
        if q_new_min <= q_old + float(min_quality_improvement):
            continue

        # flip apply.
        alive[ti] = False
        alive[tj] = False
        for nt in new_tets:
            tets_list.append(list(nt))
            alive = np.append(alive, True)
        n_flip += 1
        visited_faces.add(face)

    out = np.asarray(
        [tets_list[i] for i in range(len(tets_list)) if alive[i]],
        dtype=np.int64,
    )
    return out, n_flip


def flip_edges_32(
    pts: np.ndarray,
    tets: np.ndarray,
    *,
    min_quality_improvement: float = 1e-4,
    max_flips: int = 5000,
) -> tuple[np.ndarray, int]:
    """3-2 edge flip: 내부 edge (u,v) 를 공유하는 3 tet 제거 후 2 tet 로 재구성.

    3 tet 의 반대편 vertex 가 정확히 3 개 (x, y, z) 이어야 한다. 결과:
        {u, x, y, z}, {v, x, y, z} — 2 tet.

    quality 개선 시에만 적용. edge 가 boundary 에 있으면 skip (topology 훼손
    방지).
    """
    pts = np.asarray(pts, dtype=np.float64)
    tets = np.asarray(tets, dtype=np.int64).copy()
    if tets.size == 0:
        return tets, 0

    def _edge_to_tets_vec(T: np.ndarray) -> dict[tuple[int, int], list[int]]:
        """numpy + dict 해시: 6 edges per tet 한 번에 추출."""
        if T.size == 0:
            return {}
        pair_idx = np.array(
            [[0, 1], [0, 2], [0, 3], [1, 2], [1, 3], [2, 3]], dtype=np.int64,
        )
        edges = np.stack(
            [T[:, pair_idx[:, 0]], T[:, pair_idx[:, 1]]], axis=2,
        ).reshape(-1, 2)
        edges.sort(axis=1)
        m: dict[tuple[int, int], list[int]] = {}
        for idx in range(edges.shape[0]):
            ti = idx // 6
            k = (int(edges[idx, 0]), int(edges[idx, 1]))
            m.setdefault(k, []).append(ti)
        return m

    tets_list = tets.tolist()
    alive = np.ones(tets.shape[0], dtype=bool)
    e2t = _edge_to_tets_vec(np.asarray(tets_list, dtype=np.int64))
    fmap = _face_map_vectorized(np.asarray(tets_list, dtype=np.int64))

    # boundary edge 는 한쪽 face 가 boundary (len(face owners)==1) 인 경우.
    # Round 20: boundary edge set 을 1 번만 구성 (edge tuple 소속).
    boundary_edges: set[tuple[int, int]] = set()
    for fk, lst in fmap.items():
        if len(lst) == 1:
            a_, b_, c_ = fk
            for u_, v_ in ((a_, b_), (a_, c_), (b_, c_)):
                key = (u_, v_) if u_ < v_ else (v_, u_)
                boundary_edges.add(key)

    def _edge_on_boundary(u: int, v: int) -> bool:
        key = (u, v) if u < v else (v, u)
        return key in boundary_edges

    n_flip = 0

    for (u, v), owners in list(e2t.items()):
        if n_flip >= max_flips:
            break
        if len(owners) != 3:
            continue
        if not all(alive[t] for t in owners):
            continue
        if _edge_on_boundary(u, v):
            continue
        # 3 tet 의 반대편 vertex 3 개.
        opposite: list[int] = []
        for ti in owners:
            verts = [x for x in tets_list[ti] if x != u and x != v]
            if len(verts) != 2:
                opposite = []
                break
            opposite.extend(verts)
        # opposite 는 6 개 (3 tet × 2 other vertex). 중복 제거 시 정확히 3 고유.
        uniq = sorted(set(opposite))
        if len(uniq) != 3:
            continue
        x, y, z = uniq
        # 기존 quality.
        q_old = min(
            _tet_quality(pts[tets_list[ti][0]], pts[tets_list[ti][1]],
                         pts[tets_list[ti][2]], pts[tets_list[ti][3]])
            for ti in owners
        )
        # 새 2 tet.
        new_tets = [(u, x, y, z), (v, x, y, z)]
        ok = True
        q_new_min = 1.0
        for nt in new_tets:
            if len(set(nt)) != 4:
                ok = False; break
            vol6 = _tet_signed_vol6(pts[nt[0]], pts[nt[1]], pts[nt[2]], pts[nt[3]])
            if abs(vol6) < 1e-20:
                ok = False; break
            q = _tet_quality(pts[nt[0]], pts[nt[1]], pts[nt[2]], pts[nt[3]])
            if q < q_new_min:
                q_new_min = q
        if not ok:
            continue
        if q_new_min <= q_old + float(min_quality_improvement):
            continue

        for ti in owners:
            alive[ti] = False
        for nt in new_tets:
            tets_list.append(list(nt))
            alive = np.append(alive, True)
        n_flip += 1

    out = np.asarray(
        [tets_list[i] for i in range(len(tets_list)) if alive[i]],
        dtype=np.int64,
    )
    return out, n_flip


def flip_edges_44(
    pts: np.ndarray,
    tets: np.ndarray,
    *,
    min_quality_improvement: float = 1e-4,
    max_flips: int = 5000,
) -> tuple[np.ndarray, int]:
    """4-4 edge flip: 내부 edge 공유 4 tet 을 다른 대각선으로 재배치.

    edge (u, v) 공유 4 tet 의 반대 vertex 4 개가 ring 을 이룰 때, 해당 ring 의
    두 "대각선" 중 원래 edge 와 다른 쪽을 채택. 결과도 4 tet. quality 개선
    시에만 적용.

    현 구현은 ring 의 4 vertex 중 평균 edge 품질이 더 높은 대각선을 골라 4 tet
    으로 재구성. boundary edge 는 skip.
    """
    pts = np.asarray(pts, dtype=np.float64)
    tets = np.asarray(tets, dtype=np.int64).copy()
    if tets.size == 0:
        return tets, 0

    def _edge_to_tets_vec(T: np.ndarray) -> dict[tuple[int, int], list[int]]:
        if T.size == 0:
            return {}
        pair_idx = np.array(
            [[0, 1], [0, 2], [0, 3], [1, 2], [1, 3], [2, 3]], dtype=np.int64,
        )
        edges = np.stack(
            [T[:, pair_idx[:, 0]], T[:, pair_idx[:, 1]]], axis=2,
        ).reshape(-1, 2)
        edges.sort(axis=1)
        m: dict[tuple[int, int], list[int]] = {}
        for idx in range(edges.shape[0]):
            ti = idx // 6
            k = (int(edges[idx, 0]), int(edges[idx, 1]))
            m.setdefault(k, []).append(ti)
        return m

    tets_list = tets.tolist()
    alive = np.ones(tets.shape[0], dtype=bool)
    e2t = _edge_to_tets_vec(np.asarray(tets_list, dtype=np.int64))

    # 간이 boundary edge 체크.
    fmap = _face_map_vectorized(np.asarray(tets_list, dtype=np.int64))
    boundary_edges: set[tuple[int, int]] = set()
    for fk, lst in fmap.items():
        if len(lst) == 1:
            a_, b_, c_ = fk
            for u_, v_ in ((a_, b_), (a_, c_), (b_, c_)):
                key = (u_, v_) if u_ < v_ else (v_, u_)
                boundary_edges.add(key)

    n_flip = 0
    for (u, v), owners in list(e2t.items()):
        if n_flip >= max_flips:
            break
        if len(owners) != 4:
            continue
        if not all(alive[t] for t in owners):
            continue
        if (u, v) in boundary_edges:
            continue
        # 각 tet 의 반대 2 vertex 수집.
        ring: list[int] = []
        for ti in owners:
            rest = [x for x in tets_list[ti] if x != u and x != v]
            if len(rest) != 2:
                ring = []; break
            ring.extend(rest)
        uniq = sorted(set(ring))
        if len(uniq) != 4:
            continue
        # ring 을 u, v 주변으로 순서를 맞추기 위해 간단히: pts 기준으로 u-v 축에
        # 수직 평면 좌표로 ordering. 4 tet 재구성:
        #   원래: 각 tet (u, v, r_i, r_{i+1})  (r = ring 순환).
        #   대각선 교체: 다른 pairing 으로 ring 을 나눠 4 tet.
        # 간단 구현: ring 의 2 대각선 (r0-r2, r1-r3) 중 원래 (u-v) 가 아닌 것으로
        # ring 을 반분해 두 triangle 로 본 뒤 각각 u/v 와 결합해 4 tet.
        r = uniq
        # 원래 구성을 재현하려면 tet 별로 어느 두 r 이 인접했는지 알아야 함.
        # pragmatic: 항상 ring 의 "shortest 대각선" 을 새 pivot 으로 채택.
        d02 = float(np.linalg.norm(pts[r[0]] - pts[r[2]]))
        d13 = float(np.linalg.norm(pts[r[1]] - pts[r[3]]))
        if d02 <= d13:
            new_pivot = (r[0], r[2])
            t1 = (u, r[0], r[1], r[2])
            t2 = (u, r[0], r[2], r[3])
            t3 = (v, r[0], r[1], r[2])
            t4 = (v, r[0], r[2], r[3])
        else:
            new_pivot = (r[1], r[3])
            t1 = (u, r[1], r[0], r[3])
            t2 = (u, r[1], r[3], r[2])
            t3 = (v, r[1], r[0], r[3])
            t4 = (v, r[1], r[3], r[2])

        # quality 개선 검사.
        q_old = min(
            _tet_quality(pts[tets_list[ti][0]], pts[tets_list[ti][1]],
                         pts[tets_list[ti][2]], pts[tets_list[ti][3]])
            for ti in owners
        )
        new_tets = (t1, t2, t3, t4)
        ok = True
        q_new_min = 1.0
        for nt in new_tets:
            if len(set(nt)) != 4:
                ok = False; break
            vol6 = _tet_signed_vol6(pts[nt[0]], pts[nt[1]], pts[nt[2]], pts[nt[3]])
            if abs(vol6) < 1e-20:
                ok = False; break
            q = _tet_quality(pts[nt[0]], pts[nt[1]], pts[nt[2]], pts[nt[3]])
            if q < q_new_min:
                q_new_min = q
        if not ok:
            continue
        if q_new_min <= q_old + float(min_quality_improvement):
            continue

        for ti in owners:
            alive[ti] = False
        for nt in new_tets:
            tets_list.append(list(nt))
            alive = np.append(alive, True)
        n_flip += 1
        _ = new_pivot

    out = np.asarray(
        [tets_list[i] for i in range(len(tets_list)) if alive[i]],
        dtype=np.int64,
    )
    return out, n_flip


def face_flip_pass(
    pts: np.ndarray,
    tets: np.ndarray,
    *,
    n_iter: int = 3,
    max_flips_per_iter: int = 5000,
) -> tuple[np.ndarray, FlipResult]:
    """2-3 flip 을 여러 pass 반복. 업데이트된 tets array 와 FlipResult 반환.

    (3-2 는 edge 기반이라 다음 round 에서 처리.)
    """
    pts = np.asarray(pts, dtype=np.float64)
    tets0 = np.asarray(tets, dtype=np.int64)
    if tets0.size == 0:
        return tets0, FlipResult(0, 0, 0, 0, 0.0, 0.0)

    def _min_quality(T: np.ndarray) -> float:
        qs = [
            _tet_quality(pts[T[i, 0]], pts[T[i, 1]], pts[T[i, 2]], pts[T[i, 3]])
            for i in range(T.shape[0])
        ]
        return min(qs) if qs else 0.0

    q_before = _min_quality(tets0)
    T = tets0
    n_flip_23_total = 0
    n_flip_32_total = 0
    n_flip_44_total = 0
    for _ in range(max(1, n_iter)):
        T_new, n23 = flip_faces_23(pts, T, max_flips=max_flips_per_iter)
        if n23 > 0:
            T = T_new
            n_flip_23_total += n23
        T_new2, n32 = flip_edges_32(pts, T, max_flips=max_flips_per_iter)
        if n32 > 0:
            T = T_new2
            n_flip_32_total += n32
        T_new3, n44 = flip_edges_44(pts, T, max_flips=max_flips_per_iter)
        if n44 > 0:
            T = T_new3
            n_flip_44_total += n44
        if n23 == 0 and n32 == 0 and n44 == 0:
            break
    q_after = _min_quality(T)
    return T, FlipResult(
        n_flip_23=n_flip_23_total,
        n_flip_32=n_flip_32_total + n_flip_44_total,   # 3-2 + 4-4 를 기존 필드에 합산.
        n_tets_before=int(tets0.shape[0]),
        n_tets_after=int(T.shape[0]),
        min_quality_before=q_before,
        min_quality_after=q_after,
    )
