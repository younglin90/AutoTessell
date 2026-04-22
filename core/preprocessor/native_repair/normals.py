"""Face winding 일관성 — BFS 기반 조정."""
from __future__ import annotations

from collections import defaultdict, deque

import numpy as np


def fix_face_winding(
    vertices: np.ndarray, faces: np.ndarray,
) -> tuple[np.ndarray, int]:
    """최대 connected component 내에서 face winding 을 BFS 로 일관되게 조정.

    두 face 가 edge 를 공유할 때, 같은 edge 가 서로 다른 방향 (a→b vs b→a) 으로
    등장해야 consistent. 그렇지 않으면 한 쪽 face 를 flip.

    Returns:
        (new_faces, n_flipped).
    """
    F = np.asarray(faces, dtype=np.int64).copy()
    if F.size == 0:
        return F, 0

    # edge → face indices + edge direction
    edge_faces: dict[tuple[int, int], list[tuple[int, tuple[int, int]]]] = defaultdict(list)
    for fi in range(F.shape[0]):
        f = F[fi]
        for a, b in ((f[0], f[1]), (f[1], f[2]), (f[2], f[0])):
            k = (int(min(a, b)), int(max(a, b)))
            edge_faces[k].append((fi, (int(a), int(b))))

    visited = np.zeros(F.shape[0], dtype=bool)
    n_flipped = 0
    for seed in range(F.shape[0]):
        if visited[seed]:
            continue
        visited[seed] = True
        queue = deque([seed])
        while queue:
            cur = queue.popleft()
            f_cur = F[cur]
            cur_dirs = {
                (int(f_cur[0]), int(f_cur[1])),
                (int(f_cur[1]), int(f_cur[2])),
                (int(f_cur[2]), int(f_cur[0])),
            }
            for a, b in ((f_cur[0], f_cur[1]),
                         (f_cur[1], f_cur[2]),
                         (f_cur[2], f_cur[0])):
                k = (int(min(a, b)), int(max(a, b)))
                for (nb, nb_dir) in edge_faces.get(k, []):
                    if nb == cur or visited[nb]:
                        continue
                    visited[nb] = True
                    # neighbour 가 같은 edge 를 방향 (b, a) 로 사용해야 일관적.
                    # 현재 winding 은 (a, b). neighbour directed edge 가 (a, b) 와
                    # 같다 → flip 필요.
                    if nb_dir in cur_dirs:
                        F[nb] = F[nb][::-1]
                        n_flipped += 1
                    queue.append(nb)
    return F, int(n_flipped)
