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
    d: dict[tuple[int, int], float] = {}
    for t in tets:
        a, b, c, dd = (int(x) for x in t)
        for u, v in ((a, b), (a, c), (a, dd), (b, c), (b, dd), (c, dd)):
            k = (u, v) if u < v else (v, u)
            if k not in d:
                d[k] = float(np.linalg.norm(pts[u] - pts[v]))
    return d


def split_long_edges(
    pts: np.ndarray,
    tets: np.ndarray,
    *,
    target_edge: float,
    ratio: float = 4.0 / 3.0,
    max_splits: int = 5000,
) -> tuple[np.ndarray, np.ndarray, int]:
    """edge length > ratio × target_edge 인 edge 를 중점 split.

    Round 8 최적화: edge→tet 맵 단 1 번 빌드 후 증분 갱신.

    Returns:
        (new_pts, new_tets, n_split).
    """
    pts = np.asarray(pts, dtype=np.float64).copy()
    tets = np.asarray(tets, dtype=np.int64).copy()
    if tets.size == 0:
        return pts, tets, 0

    thresh = ratio * float(target_edge)
    lens = _edge_lengths(pts, tets)

    long_edges = sorted(
        (k for k, L in lens.items() if L > thresh),
        key=lambda k: -lens[k],
    )
    if not long_edges:
        return pts, tets, 0

    # 1 번만 빌드. 이후 새 tet 추가/삭제 시 직접 갱신.
    e2t: dict[tuple[int, int], set[int]] = {}
    for i in range(tets.shape[0]):
        a, b, c, d = (int(x) for x in tets[i])
        for u0, v0 in ((a, b), (a, c), (a, d), (b, c), (b, d), (c, d)):
            k = (u0, v0) if u0 < v0 else (v0, u0)
            e2t.setdefault(k, set()).add(i)

    n_split = 0
    pts_list = pts.tolist()
    tets_list: list[list[int]] = [list(x) for x in tets.tolist()]
    removed_tets: set[int] = set()

    def _remove_tet(ti: int) -> None:
        if ti in removed_tets:
            return
        removed_tets.add(ti)
        a, b, c, d = tets_list[ti]
        for u0, v0 in ((a, b), (a, c), (a, d), (b, c), (b, d), (c, d)):
            k = (u0, v0) if u0 < v0 else (v0, u0)
            s = e2t.get(k)
            if s is not None:
                s.discard(ti)

    def _add_tet(nt: list[int]) -> int:
        new_id = len(tets_list)
        tets_list.append(nt)
        a, b, c, d = nt
        for u0, v0 in ((a, b), (a, c), (a, d), (b, c), (b, d), (c, d)):
            k = (u0, v0) if u0 < v0 else (v0, u0)
            e2t.setdefault(k, set()).add(new_id)
        return new_id

    for (u, v) in long_edges:
        if n_split >= max_splits:
            break
        cur_len = float(
            np.linalg.norm(
                np.asarray(pts_list[u]) - np.asarray(pts_list[v]),
            )
        )
        if cur_len <= thresh:
            continue
        mid = (np.asarray(pts_list[u]) + np.asarray(pts_list[v])) / 2.0
        mid_id = len(pts_list)
        pts_list.append(mid.tolist())
        key = (u, v) if u < v else (v, u)
        owners = list(e2t.get(key, set()))
        for ti in owners:
            if ti in removed_tets:
                continue
            a, b, c, d = tets_list[ti]
            others = [x for x in (a, b, c, d) if x != u and x != v]
            if len(others) != 2:
                continue
            o1, o2 = others
            _remove_tet(ti)
            _add_tet([u, mid_id, o1, o2])
            _add_tet([v, mid_id, o1, o2])
            n_split += 1

    if not removed_tets and n_split == 0:
        return pts, tets, 0

    keep = [i for i in range(len(tets_list)) if i not in removed_tets]
    new_tets = np.asarray([tets_list[i] for i in keep], dtype=np.int64)
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

    # 반복적으로 짧은 edge 하나씩 처리 (greedy).
    for _ in range(max_collapses):
        # 현재 edge 길이 재계산.
        current = tets[alive]
        if current.size == 0:
            break
        lens = _edge_lengths(pts, current)
        short = [k for k, L in lens.items() if L < thresh]
        if not short:
            break
        # 가장 짧은 것 부터.
        short.sort(key=lambda k: lens[k])
        done = False
        for (u, v) in short:
            u_locked = u in locked_set
            v_locked = v in locked_set
            if u_locked and v_locked:
                continue
            keeper, victim = (u, v) if v_locked or (not u_locked and u < v) else (v, u)
            # 가능한지 사전 검사: victim 의 인접 tet 중 keeper 도 포함하지 않는
            # tet 에 대해 merge 후 volume sign 이 뒤집히면 skip.
            vic_tet_ids = [
                ti for ti in range(tets.shape[0])
                if alive[ti] and victim in tets[ti].tolist()
            ]
            ok = True
            for ti in vic_tet_ids:
                a, b, c, d = tets[ti].tolist()
                if keeper in (a, b, c, d):
                    # edge 공유 tet — merge 로 degenerate 됨, 제거 대상.
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
            # 수행: keeper 이동 옵션 = midpoint (둘 다 unlocked 일 때), 아니면 keeper 유지.
            if not u_locked and not v_locked:
                pts[keeper] = 0.5 * (pts[u] + pts[v])
            # merge 적용.
            for ti in vic_tet_ids:
                a, b, c, d = tets[ti].tolist()
                if keeper in (a, b, c, d):
                    alive[ti] = False
                    continue
                for idx in range(4):
                    if tets[ti, idx] == victim:
                        tets[ti, idx] = keeper
            n_collapse += 1
            done = True
            break
        if not done:
            break

    new_tets = tets[alive]
    # 미사용 vertex 는 그대로 둠 (인덱스 안정성). mesher 상위에서 정리.
    return pts, new_tets, n_collapse
