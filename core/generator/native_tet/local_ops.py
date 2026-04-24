"""Phase B2 — Edge split / edge collapse.

tet mesh 위에서 target edge length 기반 local operation.

  - Edge split : 너무 긴 edge 의 중점을 새 vertex 로 추가, 인접 tet 들을 1→2
                 분할. 너무 큰 cell 해소.
  - Edge collapse : 너무 짧은 edge 양 끝 vertex 를 merge, 인접 tet 제거. sliver
                    / 작은 cell 해소. locked vertex (surface/feature) 는 merge
                    대상에서 제외.

레퍼런스
    - Botsch et al. 2010, §6.3 remeshing (edge split/collapse 수식).
    - fTetWild (MPL-2.0) §3.3 local ops — 독립 Python 재구현.
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np


@dataclass
class LocalOpResult:
    n_split: int
    n_collapse: int
    n_points_before: int
    n_points_after: int
    n_tets_before: int
    n_tets_after: int


def _edge_lengths(pts: np.ndarray, tets: np.ndarray) -> dict[tuple[int, int], float]:
    """vectorized: tet 배열 → unique edge list + length. dict 로 반환."""
    tets = np.asarray(tets, dtype=np.int64)
    if tets.size == 0:
        return {}
    # 6 edges per tet.
    pairs = np.stack(
        [
            tets[:, [0, 1]], tets[:, [0, 2]], tets[:, [0, 3]],
            tets[:, [1, 2]], tets[:, [1, 3]], tets[:, [2, 3]],
        ],
        axis=1,
    ).reshape(-1, 2)
    # canonical (min, max).
    pairs.sort(axis=1)
    # unique.
    struct = np.ascontiguousarray(pairs).view(
        np.dtype((np.void, pairs.dtype.itemsize * 2))
    )
    _, idx = np.unique(struct, return_index=True)
    uniq = pairs[idx]
    lens = np.linalg.norm(pts[uniq[:, 0]] - pts[uniq[:, 1]], axis=1)
    return {
        (int(uniq[i, 0]), int(uniq[i, 1])): float(lens[i])
        for i in range(uniq.shape[0])
    }


def split_long_edges(
    pts: np.ndarray,
    tets: np.ndarray,
    *,
    target_edge: float,
    ratio: float = 4.0 / 3.0,
    max_splits: int = 5000,
) -> tuple[np.ndarray, np.ndarray, int]:
    """edge length > ratio × target_edge 인 edge 를 중점 split.

    Round 16 bulk vectorized: long edge 를 한꺼번에 처리.

    각 tet 에 대해 6 edge 중 "가장 긴 것 중 split 대상" 만 1 개 골라 1→2
    subdivide. 즉 1 iteration 에서 같은 tet 은 최대 1 번만 split. 품질은
    살짝 떨어지지만 반복 호출로 수렴.
    """
    pts = np.asarray(pts, dtype=np.float64)
    tets = np.asarray(tets, dtype=np.int64)
    if tets.size == 0:
        return pts.copy(), tets.copy(), 0

    thresh = float(ratio) * float(target_edge)

    # 각 tet 의 6 edge 길이 계산 (벡터).
    pair_idx = np.array(
        [[0, 1], [0, 2], [0, 3], [1, 2], [1, 3], [2, 3]], dtype=np.int64,
    )
    vpts = pts[tets]   # (T, 4, 3)
    e_lens = np.linalg.norm(
        vpts[:, pair_idx[:, 1]] - vpts[:, pair_idx[:, 0]], axis=2,
    )   # (T, 6)
    e_max = e_lens.max(axis=1)   # (T,)
    need = e_max > thresh
    if not need.any():
        return pts.copy(), tets.copy(), 0

    # 각 tet 에서 가장 긴 edge 의 local idx (0..5).
    longest = e_lens.argmax(axis=1)
    # 해당 edge 의 2 local vertex idx.
    iA = pair_idx[longest, 0]
    iB = pair_idx[longest, 1]
    # 전역 vertex id.
    vA = tets[np.arange(tets.shape[0]), iA]
    vB = tets[np.arange(tets.shape[0]), iB]

    # split 대상 tet indices.
    tgt = np.where(need)[0]
    if tgt.size > int(max_splits):
        # 가장 긴 것부터 cap.
        order = np.argsort(-e_max[tgt])[: int(max_splits)]
        tgt = tgt[order]

    # 각 edge (vA[ti], vB[ti]) 의 유니크 (canonical 정렬) set → midpoint 1 번만 생성.
    a_sorted = np.minimum(vA[tgt], vB[tgt])
    b_sorted = np.maximum(vA[tgt], vB[tgt])
    edge_keys = np.stack([a_sorted, b_sorted], axis=1)  # (N, 2)

    # Python dict 로 edge → mid_id.
    mid_map: dict[tuple[int, int], int] = {}
    pts_list = pts.tolist()
    for i in range(edge_keys.shape[0]):
        k = (int(edge_keys[i, 0]), int(edge_keys[i, 1]))
        if k not in mid_map:
            new_id = len(pts_list)
            mid = (pts[k[0]] + pts[k[1]]) / 2.0
            pts_list.append(mid.tolist())
            mid_map[k] = new_id

    tets_list: list[list[int]] = [list(x) for x in tets.tolist()]
    alive = np.ones(tets.shape[0], dtype=bool)
    n_split = 0

    for idx, ti in enumerate(tgt.tolist()):
        if not alive[ti]:
            continue
        a, b, c, d = tets_list[ti]
        u = int(vA[ti])
        v = int(vB[ti])
        others = [x for x in (a, b, c, d) if x != u and x != v]
        if len(others) != 2:
            continue
        o1, o2 = others
        k = (min(u, v), max(u, v))
        mid_id = mid_map[k]
        alive[ti] = False
        tets_list.append([u, mid_id, o1, o2])
        tets_list.append([v, mid_id, o1, o2])
        alive = np.append(alive, [True, True])
        n_split += 1

    if n_split == 0:
        return pts.copy(), tets.copy(), 0

    new_tets = np.asarray(
        [tets_list[i] for i in range(len(tets_list)) if alive[i]],
        dtype=np.int64,
    )
    new_pts = np.asarray(pts_list, dtype=np.float64)
    return new_pts, new_tets, n_split


def collapse_short_edges(
    pts: np.ndarray,
    tets: np.ndarray,
    *,
    target_edge: float,
    ratio: float = 4.0 / 5.0,
    locked_vertices: np.ndarray | None = None,
    max_collapses: int = 5000,
) -> tuple[np.ndarray, np.ndarray, int]:
    """edge length < ratio × target_edge 인 edge 양 끝을 merge (u,v → u).

    Round 9 최적화: vertex→tets 맵을 1 번 빌드 후 증분 갱신.

    제약:
      - 둘 중 하나가 locked 이면 locked 쪽을 유지, 아니면 작은 id 유지.
      - 둘 다 locked 이면 skip.
      - collapse 가 inverted tet 을 만들면 skip (volume sign 체크).
    """
    pts = np.asarray(pts, dtype=np.float64).copy()
    tets = np.asarray(tets, dtype=np.int64).copy()
    if tets.size == 0:
        return pts, tets, 0

    locked_set = set()
    if locked_vertices is not None:
        locked_set = set(int(x) for x in np.asarray(locked_vertices).ravel())

    thresh = ratio * float(target_edge)

    def _tet_vol6(A, B, C, D) -> float:
        return float(np.dot(B - A, np.cross(C - A, D - A)))

    n_collapse = 0
    alive = np.ones(tets.shape[0], dtype=bool)

    # vertex → tet id set. 매번 재계산 대신 증분 갱신.
    v2t: dict[int, set[int]] = {}
    for ti in range(tets.shape[0]):
        for vi in tets[ti]:
            v2t.setdefault(int(vi), set()).add(ti)

    for _ in range(max_collapses):
        current = tets[alive]
        if current.size == 0:
            break
        lens = _edge_lengths(pts, current)
        short = [k for k, L in lens.items() if L < thresh]
        if not short:
            break
        # 가장 짧은 edge 부터 (심플 그리디). Round 13 quality-priority 는 반려:
        # O(E × tets_per_edge) 가 실험 결과 5-STL bench 에서 timeout. 길이 정렬만
        # 유지하고 cap (max_collapses_per_iter) + rollback (cell_drop_ratio) 으로
        # 안전 확보.
        short.sort(key=lambda k: lens[k])
        done = False
        for (u, v) in short:
            u_locked = u in locked_set
            v_locked = v in locked_set
            if u_locked and v_locked:
                continue
            keeper, victim = (u, v) if v_locked or (not u_locked and u < v) else (v, u)
            vic_tet_ids = [
                ti for ti in v2t.get(victim, set()) if alive[ti]
            ]
            ok = True
            for ti in vic_tet_ids:
                a, b, c, d = tets[ti].tolist()
                if keeper in (a, b, c, d):
                    continue
                new_tet = [keeper if x == victim else x for x in (a, b, c, d)]
                if len(set(new_tet)) < 4:
                    ok = False
                    break
                A = pts[new_tet[0]]
                B = pts[new_tet[1]]
                C = pts[new_tet[2]]
                D = pts[new_tet[3]]
                v_old6 = _tet_vol6(pts[a], pts[b], pts[c], pts[d])
                v_new6 = _tet_vol6(A, B, C, D)
                if v_old6 * v_new6 <= 0:
                    ok = False
                    break
            if not ok:
                continue
            if not u_locked and not v_locked:
                pts[keeper] = 0.5 * (pts[u] + pts[v])
            for ti in vic_tet_ids:
                a, b, c, d = tets[ti].tolist()
                if keeper in (a, b, c, d):
                    # edge 공유 tet 삭제 + v2t 갱신.
                    alive[ti] = False
                    for vi in (a, b, c, d):
                        s = v2t.get(int(vi))
                        if s is not None:
                            s.discard(ti)
                    continue
                for idx in range(4):
                    if tets[ti, idx] == victim:
                        tets[ti, idx] = keeper
                # v2t 에서 victim 제거, keeper 추가.
                s_vic = v2t.get(victim)
                if s_vic is not None:
                    s_vic.discard(ti)
                v2t.setdefault(keeper, set()).add(ti)
            n_collapse += 1
            done = True
            break
        if not done:
            break

    new_tets = tets[alive]
    return pts, new_tets, n_collapse
