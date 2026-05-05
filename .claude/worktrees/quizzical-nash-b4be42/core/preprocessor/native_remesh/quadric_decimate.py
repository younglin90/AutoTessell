"""quadric_decimate.py — Garland & Heckbert 1997 surface simplification.

P4-B 첫 카드 (beta2240, skeleton).

알고리즘:
    1. 각 vertex 의 quadric Q_v = sum over incident face f of K_f
       where K_f = p p^T (p = (a, b, c, d), face plane equation).
    2. edge collapse cost = target Q_e × target_pos × target_pos^T.
    3. priority queue (heap) 로 lowest cost edge 부터 collapse.
    4. target_face_count 도달 시 종료.

레퍼런스:
    - Garland & Heckbert 1997 "Surface Simplification Using Quadric Error Metrics"
    - Hoppe 1999 (extension for color/normal)
    - fTetWild §3.4 (Hu 2020) — input simplification 단계

사용 가이드:
    >>> V_new, F_new = quadric_decimate(V, F, target_n_faces=200)

본 스켈레톤은 helper 정의만. 실제 호출은 다음 카드 (P4-B-2).
"""
from __future__ import annotations

import heapq

import numpy as np
from numpy.typing import NDArray

# P4-B-3 (beta2242) — collapse loop 활성. 단 default 동작은 target_n_faces=None 시 no-op.
_QED_ENABLED = True


def _face_plane(V: NDArray[np.float64], face: NDArray[np.int64]) -> NDArray[np.float64]:
    """face (3 vertex) 의 plane equation (a, b, c, d) — n·x + d = 0.

    Returns:
        (4,) array. n = unit normal, d = -n·v0.
    """
    v0 = V[face[0]]; v1 = V[face[1]]; v2 = V[face[2]]
    n = np.cross(v1 - v0, v2 - v0)
    n_len = float(np.linalg.norm(n))
    if n_len < 1e-30:
        return np.zeros(4, dtype=np.float64)
    n = n / n_len
    d = -float(np.dot(n, v0))
    return np.array([n[0], n[1], n[2], d], dtype=np.float64)


def _vertex_quadrics(
    V: NDArray[np.float64], F: NDArray[np.int64],
) -> NDArray[np.float64]:
    """vertex 별 quadric Q_v 누적. (N, 4, 4).

    Q_v = sum over incident face f of (p_f) (p_f)^T where p_f is plane eqn.
    """
    N = V.shape[0]
    Q = np.zeros((N, 4, 4), dtype=np.float64)
    for fi in range(F.shape[0]):
        p = _face_plane(V, F[fi])
        if np.allclose(p, 0):
            continue
        Kp = np.outer(p, p)
        for v in F[fi]:
            Q[int(v)] += Kp
    return Q


def _edge_cost(
    Q_pair: NDArray[np.float64], v_target: NDArray[np.float64],
) -> float:
    """edge collapse cost = v_target^T (Q_a + Q_b) v_target.

    v_target: 4-vector (x, y, z, 1). cost = quadric error at target position.
    """
    return float(v_target @ Q_pair @ v_target)


def _optimal_target(
    Q_pair: NDArray[np.float64], v_a: NDArray[np.float64], v_b: NDArray[np.float64],
) -> NDArray[np.float64]:
    """Q_pair 의 minimum 위치 — closed-form 해.

    minimize v^T Q v subject to v[3]=1.
    Q[:3, :3] x = -Q[:3, 3] (linear system) — singular 면 midpoint fallback.
    """
    A = Q_pair[:3, :3]
    b = -Q_pair[:3, 3]
    try:
        x = np.linalg.solve(A, b)
        return np.array([x[0], x[1], x[2], 1.0], dtype=np.float64)
    except np.linalg.LinAlgError:
        mid = 0.5 * (v_a[:3] + v_b[:3])
        return np.array([mid[0], mid[1], mid[2], 1.0], dtype=np.float64)


def _enumerate_edges(F: NDArray[np.int64]) -> set[tuple[int, int]]:
    """face 의 unique edge set. canonical (min, max) tuple."""
    edges: set[tuple[int, int]] = set()
    for fi in range(F.shape[0]):
        a, b, c = int(F[fi, 0]), int(F[fi, 1]), int(F[fi, 2])
        edges.add((min(a, b), max(a, b)))
        edges.add((min(b, c), max(b, c)))
        edges.add((min(c, a), max(c, a)))
    return edges


def _build_collapse_heap(
    V: NDArray[np.float64], F: NDArray[np.int64], Q: NDArray[np.float64],
) -> list[tuple[float, int, int, int, NDArray[np.float64]]]:
    """모든 unique edge 의 collapse cost + optimal target heap.

    P4-B-3 (beta2242): version stamp (4-th element) 추가 — 변경된 vertex 의
    edge 는 heap 의 옛 entry 가 stale 표시되어 lazy invalidation.

    Returns:
        heap (heapq) of (cost, a, b, version_pair, v_target_4d).
        version_pair = vertex_version[a] + vertex_version[b] at heap-push time.
    """
    edges = _enumerate_edges(F)
    out: list[tuple[float, int, int, int, NDArray[np.float64]]] = []
    for (a, b) in edges:
        Q_pair = Q[a] + Q[b]
        v_a = np.array([V[a, 0], V[a, 1], V[a, 2], 1.0], dtype=np.float64)
        v_b = np.array([V[b, 0], V[b, 1], V[b, 2], 1.0], dtype=np.float64)
        v_t = _optimal_target(Q_pair, v_a, v_b)
        c = _edge_cost(Q_pair, v_t)
        out.append((c, a, b, 0, v_t))
    heapq.heapify(out)
    return out


def _build_v2f(F: NDArray[np.int64], n_v: int) -> list[set[int]]:
    """vertex → set of incident face indices."""
    v2f: list[set[int]] = [set() for _ in range(n_v)]
    for fi in range(F.shape[0]):
        v2f[int(F[fi, 0])].add(fi)
        v2f[int(F[fi, 1])].add(fi)
        v2f[int(F[fi, 2])].add(fi)
    return v2f


def _collapse_edge(
    V: NDArray[np.float64],
    F: NDArray[np.int64],
    Q: NDArray[np.float64],
    v2f: list[set[int]],
    alive_v: NDArray[np.bool_],
    alive_f: NDArray[np.bool_],
    a: int,
    b: int,
    v_target: NDArray[np.float64],
) -> int:
    """edge (a, b) 를 collapse — b 를 a 에 병합. v2f index 동기화.

    Returns:
        n_faces_removed.
    """
    V[a, 0] = v_target[0]; V[a, 1] = v_target[1]; V[a, 2] = v_target[2]
    Q[a] = Q[a] + Q[b]
    alive_v[b] = False

    n_removed = 0
    incident_b = list(v2f[b])
    for fi in incident_b:
        if not alive_f[fi]:
            continue
        v0, v1, v2 = int(F[fi, 0]), int(F[fi, 1]), int(F[fi, 2])
        v0 = a if v0 == b else v0
        v1 = a if v1 == b else v1
        v2 = a if v2 == b else v2
        if v0 == v1 or v1 == v2 or v0 == v2:
            alive_f[fi] = False
            n_removed += 1
            for v in (int(F[fi, 0]), int(F[fi, 1]), int(F[fi, 2])):
                v2f[v].discard(fi)
        else:
            F[fi, 0] = v0; F[fi, 1] = v1; F[fi, 2] = v2
            v2f[a].add(fi)
            v2f[b].discard(fi)
    v2f[b].clear()
    return n_removed


def _push_incident_edges(
    V: NDArray[np.float64],
    F: NDArray[np.int64],
    Q: NDArray[np.float64],
    v2f: list[set[int]],
    alive_f: NDArray[np.bool_],
    vertex_version: NDArray[np.int64],
    heap: list[tuple[float, int, int, int, NDArray[np.float64]]],
    a: int,
) -> None:
    """vertex a 와 incident 한 모든 alive edge 의 신규 cost 를 heap 에 push."""
    nbrs: set[int] = set()
    for fi in v2f[a]:
        if not alive_f[fi]:
            continue
        v0, v1, v2 = int(F[fi, 0]), int(F[fi, 1]), int(F[fi, 2])
        for x in (v0, v1, v2):
            if x != a:
                nbrs.add(x)
    v_a = np.array([V[a, 0], V[a, 1], V[a, 2], 1.0], dtype=np.float64)
    for x in nbrs:
        Q_pair = Q[a] + Q[x]
        v_x = np.array([V[x, 0], V[x, 1], V[x, 2], 1.0], dtype=np.float64)
        v_t = _optimal_target(Q_pair, v_a, v_x)
        c = _edge_cost(Q_pair, v_t)
        ver = int(vertex_version[a] + vertex_version[x])
        u, w = (a, x) if a < x else (x, a)
        heapq.heappush(heap, (c, u, w, ver, v_t))


def quadric_decimate(
    V: NDArray[np.float64],
    F: NDArray[np.int64],
    *,
    target_n_faces: int | None = None,
    target_ratio: float | None = None,
    max_iters: int = 10000,
) -> tuple[NDArray[np.float64], NDArray[np.int64]]:
    """Garland & Heckbert 1997 surface simplification.

    skeleton (P4-B-1, beta2240): 본 함수는 정의만, 실제 collapse loop 는
    다음 카드 (P4-B-3) 에서. 현재는 입력을 그대로 반환 (no-op).

    Args:
        V: input vertices (N, 3).
        F: input faces (M, 3).
        target_n_faces: 목표 face 수 (priority).
        target_ratio: target_n_faces 미설정 시 사용 (예 0.5 = 절반).
        max_iters: collapse 최대 반복.

    Returns:
        (V_new, F_new). 현재 skeleton 은 (V, F) 그대로.
    """
    if not _QED_ENABLED:
        return V.astype(np.float64).copy(), F.astype(np.int64).copy()

    # target 결정 — 명시 없으면 no-op (현 face 수 그대로).
    n_faces_in = int(F.shape[0])
    if target_n_faces is None:
        if target_ratio is None:
            return V.astype(np.float64).copy(), F.astype(np.int64).copy()
        target_n_faces = max(4, int(round(n_faces_in * float(target_ratio))))
    target_n_faces = max(4, int(target_n_faces))
    if target_n_faces >= n_faces_in:
        return V.astype(np.float64).copy(), F.astype(np.int64).copy()

    V_w = V.astype(np.float64).copy()
    F_w = F.astype(np.int64).copy()
    Q = _vertex_quadrics(V_w, F_w)
    heap = _build_collapse_heap(V_w, F_w, Q)
    v2f = _build_v2f(F_w, V_w.shape[0])

    alive_v = np.ones(V_w.shape[0], dtype=np.bool_)
    alive_f = np.ones(F_w.shape[0], dtype=np.bool_)
    vertex_version = np.zeros(V_w.shape[0], dtype=np.int64)

    n_alive = n_faces_in
    n_iter = 0
    while n_alive > target_n_faces and heap and n_iter < int(max_iters):
        c, a, b, ver, v_t = heapq.heappop(heap)
        n_iter += 1
        if not alive_v[a] or not alive_v[b]:
            continue
        cur_ver = int(vertex_version[a] + vertex_version[b])
        if cur_ver != ver:
            continue
        n_removed = _collapse_edge(V_w, F_w, Q, v2f, alive_v, alive_f, a, b, v_t)
        if n_removed == 0:
            continue
        n_alive -= n_removed
        vertex_version[a] += 1
        _push_incident_edges(V_w, F_w, Q, v2f, alive_f, vertex_version, heap, a)

    # alive vertex 만 compact, F remap.
    new_v_idx = -np.ones(V_w.shape[0], dtype=np.int64)
    keep_v = np.where(alive_v)[0]
    new_v_idx[keep_v] = np.arange(keep_v.shape[0])
    V_out = V_w[keep_v]
    keep_f = np.where(alive_f)[0]
    F_out = new_v_idx[F_w[keep_f]]
    return V_out, F_out.astype(np.int64)
