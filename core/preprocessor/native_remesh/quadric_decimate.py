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

import numpy as np
from numpy.typing import NDArray

# default OFF — 다음 카드에서 ON.
_QED_ENABLED = False


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
    다음 카드 (P4-B-2) 에서. 현재는 입력을 그대로 반환 (no-op).

    Args:
        V: input vertices (N, 3).
        F: input faces (M, 3).
        target_n_faces: 목표 face 수 (priority).
        target_ratio: target_n_faces 미설정 시 사용 (예 0.5 = 절반).
        max_iters: collapse 최대 반복.

    Returns:
        (V_new, F_new). 현재 skeleton 은 (V, F) 그대로.
    """
    # 다음 카드에서 활성화: priority queue + collapse loop.
    if not _QED_ENABLED:
        return V.astype(np.float64).copy(), F.astype(np.int64).copy()

    # placeholder — 다음 카드 (P4-B-2) 에서 구현.
    Q = _vertex_quadrics(V, F)
    return V.astype(np.float64).copy(), F.astype(np.int64).copy()
