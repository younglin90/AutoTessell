"""Non-manifold edge 해결 (3+ face 공유 edge 에서 일부 face 제거)."""
from __future__ import annotations

from collections import defaultdict

import numpy as np


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
        edge_faces: dict[tuple[int, int], list[int]] = defaultdict(list)
        for fi in np.where(active)[0]:
            f = F[fi]
            for a, b in ((f[0], f[1]), (f[1], f[2]), (f[2], f[0])):
                k = (int(min(a, b)), int(max(a, b)))
                edge_faces[k].append(int(fi))
        for _, fl in edge_faces.items():
            if len(fl) >= 3:
                # 마지막 면 (인덱스 가장 큰 것) 제거
                drop = max(fl)
                if active[drop]:
                    active[drop] = False
                    n_removed_total += 1
                    changed = True
    return F[active], int(n_removed_total)
