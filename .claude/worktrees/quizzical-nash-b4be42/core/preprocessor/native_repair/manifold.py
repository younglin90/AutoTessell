"""Non-manifold edge 해결 (3+ face 공유 edge 에서 일부 face 제거)."""
from __future__ import annotations

import numpy as np


def _build_edge_face_map(F: np.ndarray, active: np.ndarray) -> dict[int, list[int]]:
    """active face 들의 undirected edge → face index 매핑을 numpy 로 벡터화 구축.

    각 삼각형 3 edge 를 (min, max) 정렬 후 lexsort 로 그룹화.
    Returns dict keyed by flat int (e0*max_v + e1) → list of fi.
    """
    active_idx = np.where(active)[0]
    if active_idx.size == 0:
        return {}
    Fa = F[active_idx]          # (M, 3)
    # 3 edges per face: (0,1), (1,2), (2,0)
    e0 = np.stack([Fa[:, 0], Fa[:, 1], Fa[:, 2]], axis=0)  # (3, M)
    e1 = np.stack([Fa[:, 1], Fa[:, 2], Fa[:, 0]], axis=0)
    ea = np.minimum(e0, e1).ravel()          # (3M,)
    eb = np.maximum(e0, e1).ravel()          # (3M,)
    fi_rep = np.tile(active_idx, 3)          # (3M,) face indices

    max_v = int(F.max()) + 1
    keys = ea.astype(np.int64) * max_v + eb.astype(np.int64)
    order = np.argsort(keys, kind="stable")
    keys_s = keys[order]
    fi_s = fi_rep[order]

    edge_map: dict[int, list[int]] = {}
    starts = np.where(np.diff(keys_s, prepend=keys_s[0] - 1))[0]
    ends = np.append(starts[1:], len(keys_s))
    for s, e in zip(starts, ends):
        k = int(keys_s[s])
        edge_map[k] = fi_s[s:e].tolist()
    return edge_map


def remove_non_manifold_faces(faces: np.ndarray) -> tuple[np.ndarray, int]:
    """edge 가 3 이상 face 를 공유하는 경우 한 쪽 face 를 제거해 edge-manifold 로 복원.

    Heuristic: edge 당 여분 face 를 "face 인덱스가 가장 큰 것" 으로 반복 제거.
    (더 정교한 접근은 face 를 쌍으로 매칭해 최적의 pair 유지하는 matching 문제.)

    Returns:
        (new_faces, n_removed).
    """
    F = np.asarray(faces, dtype=np.int64)
    if F.size == 0:
        return F, 0

    active = np.ones(F.shape[0], dtype=bool)
    changed = True
    iter_count = 0
    n_removed_total = 0
    while changed and iter_count < 10:
        changed = False
        iter_count += 1
        edge_map = _build_edge_face_map(F, active)
        for fl in edge_map.values():
            if len(fl) >= 3:
                drop = max(fl)
                if active[drop]:
                    active[drop] = False
                    n_removed_total += 1
                    changed = True
    return F[active], int(n_removed_total)
