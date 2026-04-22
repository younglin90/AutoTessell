"""작은 hole 을 boundary loop + fan triangulation 으로 채운다."""
from __future__ import annotations

from collections import defaultdict

import numpy as np


def _extract_boundary_loops(faces: np.ndarray) -> list[list[int]]:
    """boundary edge 들을 연결해 loop 리스트 반환.

    각 edge 를 directed (face 의 winding 방향) 으로 수집한 뒤, 같은 edge 가
    반대 방향 쌍이 없는 경우 boundary directed edge. 이 directed edge 들을 next-map
    (start → end) 으로 이어 loop 구성.
    """
    if faces.size == 0:
        return []

    # directed edges from each face
    dirs = []
    for f in faces:
        dirs.append((int(f[0]), int(f[1])))
        dirs.append((int(f[1]), int(f[2])))
        dirs.append((int(f[2]), int(f[0])))

    # edge set for lookup
    edge_set = set(dirs)
    boundary_dir: list[tuple[int, int]] = []
    for (a, b) in dirs:
        if (b, a) not in edge_set:
            boundary_dir.append((a, b))

    if not boundary_dir:
        return []

    # next map: start vertex → end vertex (directed)
    next_map: dict[int, list[int]] = defaultdict(list)
    for a, b in boundary_dir:
        next_map[a].append(b)

    visited: set[tuple[int, int]] = set()
    loops: list[list[int]] = []
    for a0, b0 in boundary_dir:
        if (a0, b0) in visited:
            continue
        loop = [a0]
        cur = b0
        while cur != a0:
            nexts = next_map.get(cur, [])
            if not nexts:
                break
            nxt = nexts.pop(0)
            visited.add((cur, nxt))
            loop.append(cur)
            cur = nxt
            if len(loop) > len(boundary_dir) + 2:
                break
        visited.add((a0, b0))
        if len(loop) >= 3 and loop[-1] != loop[0]:
            loops.append(loop)
    return loops


def fill_small_holes(
    vertices: np.ndarray, faces: np.ndarray,
    *, max_boundary: int = 64,
) -> tuple[np.ndarray, int]:
    """boundary loop 길이가 ``max_boundary`` 이하인 hole 을 fan triangulation 으로 채움.

    Fan 은 loop 의 첫 vertex 를 중심으로. 더 정교한 최소 면적 triangulation 은
    향후 확장 대상.

    Returns:
        (new_faces, n_added).
    """
    F = np.asarray(faces, dtype=np.int64)
    if F.size == 0:
        return F, 0
    loops = _extract_boundary_loops(F)
    if not loops:
        return F, 0
    added: list[list[int]] = []
    for loop in loops:
        if len(loop) > max_boundary or len(loop) < 3:
            continue
        v0 = loop[0]
        for k in range(1, len(loop) - 1):
            added.append([v0, loop[k], loop[k + 1]])
    if not added:
        return F, 0
    new_F = np.vstack([F, np.array(added, dtype=np.int64)])
    return new_F, len(added)
