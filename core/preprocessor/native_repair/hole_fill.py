"""작은 hole 을 boundary loop + ear-clipping triangulation 으로 채운다.

v0.4.0-beta2 개선:
    - fan triangulation (loop[0] 중심) → ear-clipping 알고리즘 기반.
    - 3D hole 에 대해 loop 의 평균 normal 로 평면 좌표계를 만들고, 2D 에서 이어
      clipping 한다. 긴 loop / non-convex hole 에서 fan 대비 topology 품질 향상.
    - multi-loop 지원은 기존 그대로.
"""
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


def _loop_plane_basis(
    vertices: np.ndarray, loop: list[int],
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """loop 의 평균 평면 basis (centroid, e1, e2) 반환. SVD 로 PCA."""
    pts = vertices[loop]
    c = pts.mean(axis=0)
    A = pts - c
    _, _, vt = np.linalg.svd(A, full_matrices=False)
    n = vt[-1]
    e1 = A[0] - n * float(np.dot(A[0], n))
    if float(np.linalg.norm(e1)) < 1e-30:
        # degenerate: pick any orthogonal
        e1 = np.array([1.0, 0.0, 0.0]) - n * float(n[0])
    e1 = e1 / max(float(np.linalg.norm(e1)), 1e-30)
    e2 = np.cross(n, e1)
    return c, e1, e2


def _triangle_contains_point(
    a: np.ndarray, b: np.ndarray, c: np.ndarray, p: np.ndarray,
) -> bool:
    """2D triangle (CCW) 내부 점 판정 (boundary 포함)."""
    def _sign(p1: np.ndarray, p2: np.ndarray, p3: np.ndarray) -> float:
        return (p1[0] - p3[0]) * (p2[1] - p3[1]) - (p2[0] - p3[0]) * (p1[1] - p3[1])
    d1 = _sign(p, a, b); d2 = _sign(p, b, c); d3 = _sign(p, c, a)
    neg = (d1 < 0) or (d2 < 0) or (d3 < 0)
    pos = (d1 > 0) or (d2 > 0) or (d3 > 0)
    return not (neg and pos)


def _ear_clip_2d(verts_2d: np.ndarray) -> list[tuple[int, int, int]]:
    """2D CCW polygon 의 ear-clipping triangulation — 정점 index tuple 리스트 반환.

    출력 triangle 은 입력 verts_2d 인덱스 기준. O(n^2) — 작은 hole 에 충분.
    polygon winding 은 signed area 로 자동 판정 (CW 면 내부적으로 뒤집음).
    """
    n = verts_2d.shape[0]
    if n < 3:
        return []
    # signed area
    area = 0.0
    for i in range(n):
        x1, y1 = verts_2d[i]
        x2, y2 = verts_2d[(i + 1) % n]
        area += x1 * y2 - x2 * y1
    indices = list(range(n))
    if area < 0:
        indices = indices[::-1]

    triangles: list[tuple[int, int, int]] = []
    guard = 0
    while len(indices) > 2 and guard < 10 * n:
        guard += 1
        ear_found = False
        for i in range(len(indices)):
            prev_i = indices[(i - 1) % len(indices)]
            cur_i = indices[i]
            next_i = indices[(i + 1) % len(indices)]
            a = verts_2d[prev_i]; b = verts_2d[cur_i]; c = verts_2d[next_i]
            # convex vertex (CCW) — cross product z > 0
            cross_z = (b[0] - a[0]) * (c[1] - a[1]) - (b[1] - a[1]) * (c[0] - a[0])
            if cross_z <= 1e-20:
                continue
            # no other polygon vertex inside triangle abc
            inside = False
            for j in indices:
                if j in (prev_i, cur_i, next_i):
                    continue
                if _triangle_contains_point(a, b, c, verts_2d[j]):
                    inside = True
                    break
            if inside:
                continue
            triangles.append((prev_i, cur_i, next_i))
            indices.pop(i)
            ear_found = True
            break
        if not ear_found:
            # numerical fallback — 남은 polygon 을 fan 으로 처리
            for k in range(1, len(indices) - 1):
                triangles.append((indices[0], indices[k], indices[k + 1]))
            break
    return triangles


def fill_small_holes(
    vertices: np.ndarray, faces: np.ndarray,
    *, max_boundary: int = 128,
) -> tuple[np.ndarray, int]:
    """boundary loop 길이가 ``max_boundary`` 이하인 hole 을 ear-clipping 으로 채움.

    Args:
        vertices: (V, 3) mesh vertex 좌표.
        faces: (F, 3) int triangle faces.
        max_boundary: 채울 hole 의 최대 boundary 길이. 기본 128 (v0.4 에서 64→128).

    Returns:
        (new_faces, n_added).
    """
    V = np.asarray(vertices, dtype=np.float64)
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
        if V.size == 0:
            # fallback fan
            for k in range(1, len(loop) - 1):
                added.append([loop[0], loop[k], loop[k + 1]])
            continue
        # 3 → fan 밖에 없음
        if len(loop) == 3:
            added.append([loop[0], loop[1], loop[2]])
            continue
        # 3D loop → 평면 basis → 2D ear-clipping → 3D face index 로 환원
        c, e1, e2 = _loop_plane_basis(V, loop)
        pts_3d = V[loop]
        rel = pts_3d - c
        verts_2d = np.stack([rel @ e1, rel @ e2], axis=1)
        tris_local = _ear_clip_2d(verts_2d)
        for (i0, i1, i2) in tris_local:
            added.append([loop[i0], loop[i1], loop[i2]])

    if not added:
        return F, 0
    new_F = np.vstack([F, np.array(added, dtype=np.int64)])
    return new_F, len(added)
