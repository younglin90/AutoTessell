"""Round 67 — Targeted edge flip for CDT recovery.

Missing surface edge (u, v) 가 존재할 때, u 와 v 를 동시에 포함하는 tet 쌍의
"잘못된 대각선" 을 뒤집어 (u, v) 를 edge 로 생성. standard 2-3 flip 과 달리
quality 가 아닌 "edge (u, v) 가 결과에 존재" 를 기준으로 선택.

레퍼런스
    - Shewchuk 1998, "Tetrahedral Mesh Generation by Delaunay Refinement".
    - Si 2015 TetGen §4 edge recovery via flips.
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np


@dataclass
class TargetedFlipResult:
    n_edges_attempted: int
    n_edges_recovered: int


def _find_tets_containing_both(tets: np.ndarray, u: int, v: int) -> list[int]:
    """u 와 v 를 동시에 포함한 tet id 리스트."""
    mask = ((tets == u).any(axis=1)) & ((tets == v).any(axis=1))
    return np.where(mask)[0].tolist()


def _has_edge(tets: np.ndarray, u: int, v: int) -> bool:
    """현재 tet 배열에 edge (u, v) 가 존재하는지."""
    return bool(((tets == u).any(axis=1) & (tets == v).any(axis=1)).any())


def _edge_in_any_tet_set(tets_list: list[list[int]], u: int, v: int) -> bool:
    for t in tets_list:
        if u in t and v in t:
            return True
    return False


def recover_edges_via_flip(
    pts: np.ndarray,
    tets: np.ndarray,
    missing_edges: list[tuple[int, int]],
    *,
    max_attempts: int = 200,
) -> tuple[np.ndarray, TargetedFlipResult]:
    """각 missing edge 에 대해 2-3 flip 을 시도해 edge 생성.

    전략: edge (u, v) 가 없고, u 와 v 가 각각 포함된 "인접 2 tet (공유 face 존재)"
    쌍이 있다면, 해당 face 를 뒤집어 2-3 flip 수행. 새 edge 가 u-v 가 되도록.

    현재 구현은 간이 — 공유 face 가 (a, b, c) 이고 두 tet 이 (a,b,c,u) /
    (a,b,c,v) 이면 정확히 2-3 flip 이 edge (u, v) 를 만든다.
    """
    pts = np.asarray(pts, dtype=np.float64)
    tets_arr = np.asarray(tets, dtype=np.int64).copy()
    n_attempts = 0
    n_recovered = 0

    for (u, v) in missing_edges[:max_attempts]:
        n_attempts += 1
        if _has_edge(tets_arr, u, v):
            n_recovered += 1
            continue
        # u 포함 tet 중 v 와 face 공유 가능한 쌍 탐색.
        u_tets = np.where((tets_arr == u).any(axis=1))[0]
        found = False
        for tu in u_tets:
            # tu 의 각 face 중 v 를 포함한 두 tet 이 있는지.
            tu_verts = set(int(x) for x in tets_arr[tu])
            face_verts = tu_verts - {u}
            if len(face_verts) != 3:
                continue
            # face 가 (a, b, c) 이면 상대 tet 은 (a, b, c, v).
            face_sorted = tuple(sorted(face_verts))
            fa, fb, fc = face_sorted
            # (fa, fb, fc, v) tet 검색.
            target = sorted([fa, fb, fc, v])
            for tv in range(tets_arr.shape[0]):
                if tv == tu:
                    continue
                if sorted(tets_arr[tv].tolist()) == target:
                    # 2-3 flip: 제거 tu, tv. 신규 3 tet: (a,b,u,v),(b,c,u,v),(c,a,u,v).
                    new_rows = np.array(
                        [[fa, fb, u, v], [fb, fc, u, v], [fc, fa, u, v]],
                        dtype=np.int64,
                    )
                    # 기존 두 tet 제거.
                    keep_mask = np.ones(tets_arr.shape[0], dtype=bool)
                    keep_mask[tu] = False
                    keep_mask[tv] = False
                    tets_arr = np.vstack([tets_arr[keep_mask], new_rows])
                    n_recovered += 1
                    found = True
                    break
            if found:
                break

    return tets_arr, TargetedFlipResult(
        n_edges_attempted=n_attempts,
        n_edges_recovered=n_recovered,
    )
