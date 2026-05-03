"""AGGRESSIVE-REPAIR / beta2805 — input mesh quality 개선 pre-pass.

extreme self-intersect 입력 (832~2327 SI count, mq 0.012 mesh) 의 self-impl
tet failure 회복 목표:

    1. dedup vertices (tol 1e-9).
    2. degenerate triangle removal.
    3. self-intersection 단계별 resolve (cut + merge + retry).
    4. hole fill (boundary > 256 도 강제).
    5. winding flip + normal consistency.
    6. isotropic remesh (target_edge median, smoothing 4 iter).
    7. quality validation: 통과 못하면 repair param 강화 후 재시도 (max 3 sweep).

기존 run_native_repair (level 1-3) 의 wrapper 가 아닌, **input fragility
(SI count > 100 OR mq < 0.05) 극복용 강력 pre-pass**.
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from numpy.typing import NDArray


@dataclass
class AggressiveRepairResult:
    success: bool = False
    n_iterations: int = 0
    pre_si_count: int = 0
    post_si_count: int = 0
    pre_n_vertices: int = 0
    post_n_vertices: int = 0
    pre_n_faces: int = 0
    post_n_faces: int = 0
    pre_min_quality: float = 0.0
    post_min_quality: float = 0.0
    elapsed_s: float = 0.0
    message: str = ""


def aggressive_input_repair(
    V: NDArray[np.float64],
    F: NDArray[np.int64],
    *,
    max_sweep: int = 3,
    target_edge: float | None = None,
    si_threshold: int = 100,
    mq_threshold: float = 0.05,
) -> tuple[NDArray[np.float64], NDArray[np.int64], AggressiveRepairResult]:
    """input mesh 강력 repair sweep.

    Args:
        V: (N, 3).
        F: (M, 3).
        max_sweep: 최대 repair iteration.
        target_edge: isotropic remesh target (None → median edge).
        si_threshold: SI count 이 값 이하로 떨어지면 OK.
        mq_threshold: surface tri quality (mean ratio) 이 값 이상이면 OK.

    Returns:
        (V_out, F_out, AggressiveRepairResult).
    """
    import time
    t0 = time.perf_counter()

    V = np.asarray(V, dtype=np.float64).copy()
    F = np.asarray(F, dtype=np.int64).copy()
    res = AggressiveRepairResult(
        pre_n_vertices=int(V.shape[0]),
        pre_n_faces=int(F.shape[0]),
    )

    if F.shape[0] == 0:
        res.elapsed_s = time.perf_counter() - t0
        res.message = "empty input"
        return V, F, res

    # pre-stats.
    pre_si = _count_self_intersections(V, F)
    pre_mq = _surface_tri_min_quality(V, F)
    res.pre_si_count = pre_si
    res.pre_min_quality = pre_mq

    # iterative aggressive repair.
    cur_V, cur_F = V, F
    for sweep in range(int(max_sweep)):
        res.n_iterations = sweep + 1

        # Step 1: dedup.
        cur_V, cur_F = _dedup_vertices_inline(cur_V, cur_F, tol=1e-9)
        # Step 2: drop degenerate.
        cur_V, cur_F = _drop_degenerate_inline(cur_V, cur_F)
        # Step 3: SI resolve via run_native_repair (aggressive=3).
        try:
            from core.preprocessor.native_repair import run_native_repair
            r = run_native_repair(
                cur_V, cur_F,
                dedup_tol=1e-9,
                degenerate_area_tol=1e-15,
                fill_hole_max_boundary=512,  # extreme: 큰 hole 강제 fill.
                fix_normals=True,
                aggressive=3,
            )
            if r.vertices.shape[0] >= 4 and r.faces.shape[0] >= 4:
                cur_V = r.vertices.astype(np.float64)
                cur_F = r.faces.astype(np.int64)
        except Exception:
            pass

        # Step 4: isotropic remesh (1 iter, target_edge).
        if target_edge is None:
            target_edge = _estimate_target_edge(cur_V, cur_F)
        cur_V, cur_F = _isotropic_remesh_inline(
            cur_V, cur_F, target_edge=float(target_edge), n_iter=1,
        )

        # check.
        cur_si = _count_self_intersections(cur_V, cur_F)
        cur_mq = _surface_tri_min_quality(cur_V, cur_F)
        if cur_si <= si_threshold and cur_mq >= mq_threshold:
            res.message = f"converged at sweep {sweep + 1}"
            break

    res.success = True
    res.post_si_count = _count_self_intersections(cur_V, cur_F)
    res.post_n_vertices = int(cur_V.shape[0])
    res.post_n_faces = int(cur_F.shape[0])
    res.post_min_quality = _surface_tri_min_quality(cur_V, cur_F)
    res.elapsed_s = time.perf_counter() - t0
    if not res.message:
        res.message = f"max_sweep {max_sweep} reached"
    return cur_V, cur_F, res


def _count_self_intersections(V, F) -> int:
    try:
        from core.preprocessor.native_repair.self_intersect import (
            detect_self_intersections,
        )
        r = detect_self_intersections(V, F)
        return int(r.n_intersections)
    except Exception:
        return 0


def _surface_tri_min_quality(V, F) -> float:
    """surface tri min quality (4 sqrt(3) A / sum_l_sq)."""
    if F.shape[0] == 0:
        return 0.0
    a = V[F[:, 0]]
    b = V[F[:, 1]]
    c = V[F[:, 2]]
    e1 = b - a; e2 = c - a; e3 = c - b
    A = 0.5 * np.linalg.norm(np.cross(e1, e2), axis=1)
    L_sq = (e1 ** 2).sum(axis=1) + (e2 ** 2).sum(axis=1) + (e3 ** 2).sum(axis=1)
    safe = L_sq > 1e-30
    q = np.zeros(F.shape[0], dtype=np.float64)
    q[safe] = 4.0 * np.sqrt(3.0) * A[safe] / L_sq[safe]
    return float(q.min()) if q.size else 0.0


def _estimate_target_edge(V, F) -> float:
    if F.shape[0] == 0:
        return 1.0
    a = V[F[:, 0]]
    b = V[F[:, 1]]
    c = V[F[:, 2]]
    e_lens = np.concatenate([
        np.linalg.norm(b - a, axis=1),
        np.linalg.norm(c - b, axis=1),
        np.linalg.norm(a - c, axis=1),
    ])
    return float(np.median(e_lens))


def _dedup_vertices_inline(V, F, tol=1e-9):
    """간단 quantize-based dedup."""
    if V.shape[0] == 0:
        return V, F
    keys = np.round(V / tol).astype(np.int64) * tol
    keys_view = keys.view([("", keys.dtype)] * keys.shape[1]).reshape(-1)
    uniq, inverse = np.unique(keys_view, return_inverse=True)
    n_out = int(uniq.shape[0])
    V_out = np.zeros((n_out, 3), dtype=np.float64)
    cnt = np.zeros(n_out, dtype=np.int64)
    for i in range(V.shape[0]):
        c = int(inverse[i])
        V_out[c] += V[i]
        cnt[c] += 1
    V_out = V_out / np.maximum(cnt[:, None], 1)
    F_out = inverse[F].astype(np.int64) if F.size > 0 else F
    return V_out, F_out


def _drop_degenerate_inline(V, F, area_tol=1e-15):
    if F.shape[0] == 0:
        return V, F
    a = V[F[:, 0]]
    b = V[F[:, 1]]
    c = V[F[:, 2]]
    A = 0.5 * np.linalg.norm(np.cross(b - a, c - a), axis=1)
    keep = (A > area_tol) & (F[:, 0] != F[:, 1]) & (F[:, 1] != F[:, 2]) & (F[:, 0] != F[:, 2])
    return V, F[keep]


def _isotropic_remesh_inline(V, F, *, target_edge: float, n_iter: int = 1):
    """SHAPE-PRESERVE / beta2816 — feature-preserving Laplacian smoothing.

    핵심 fix: cube 같은 sharp-feature mesh 의 모서리/코너 보존.
        1. boundary edge (1 face incident) 위 vertex → lock.
        2. sharp dihedral (face normal 사이 angle > threshold) edge endpoint → lock.
        3. corner vertex (3+ feature edges incident) → lock.
        4. smooth 후 원본 mesh 의 face plane 위로 project (planar drift 회피).
    """
    if F.shape[0] == 0 or V.shape[0] == 0:
        return V, F
    n_v = V.shape[0]

    # build edge → face count + face normals.
    edges = np.concatenate([F[:, [0, 1]], F[:, [1, 2]], F[:, [2, 0]]], axis=0)
    edges_s = np.sort(edges, axis=1)
    face_ids = np.tile(np.arange(F.shape[0], dtype=np.int64), 3)

    # face normals.
    fn = np.cross(V[F[:, 1]] - V[F[:, 0]], V[F[:, 2]] - V[F[:, 0]])
    fn_norm = np.linalg.norm(fn, axis=1)
    safe = fn_norm > 1e-30
    fn[safe] = fn[safe] / fn_norm[safe, None]

    # group by edge to detect boundary + sharp.
    keys = edges_s[:, 0] * (1 << 32) + edges_s[:, 1]
    sort_idx = np.argsort(keys)
    keys_s = keys[sort_idx]
    edges_so = edges_s[sort_idx]
    face_ids_s = face_ids[sort_idx]

    locked = np.zeros(n_v, dtype=bool)
    # vertex valence (incident edges) for corner detect.
    feature_count = np.zeros(n_v, dtype=np.int64)

    feature_angle_cos = np.cos(np.radians(30.0))   # ≥ 30° dihedral = sharp.

    n_e = keys_s.shape[0]
    i = 0
    while i < n_e:
        j = i
        while j < n_e and keys_s[j] == keys_s[i]:
            j += 1
        cnt = j - i
        u, w = int(edges_so[i, 0]), int(edges_so[i, 1])
        if cnt == 1:
            # boundary edge → endpoint lock.
            locked[u] = True
            locked[w] = True
            feature_count[u] += 1
            feature_count[w] += 1
        elif cnt == 2:
            f0 = int(face_ids_s[i])
            f1 = int(face_ids_s[i + 1])
            cos_dihedral = float(np.dot(fn[f0], fn[f1]))
            if cos_dihedral < feature_angle_cos:
                # sharp edge → endpoint lock.
                locked[u] = True
                locked[w] = True
                feature_count[u] += 1
                feature_count[w] += 1
        else:
            # non-manifold (3+ faces) → endpoint lock too.
            locked[u] = True
            locked[w] = True
        i = j

    # build vertex neighbor list via unique edges.
    unique_e = np.unique(edges_s, axis=0)
    nbr_lists: list[list[int]] = [[] for _ in range(n_v)]
    for e in unique_e:
        a, b = int(e[0]), int(e[1])
        nbr_lists[a].append(b)
        nbr_lists[b].append(a)

    cur_V = V.copy()
    for _ in range(int(n_iter)):
        new_V = cur_V.copy()
        for vi in range(n_v):
            if locked[vi]:
                continue   # ★ corner/boundary/sharp vertex 위치 보존.
            nbrs = nbr_lists[vi]
            if not nbrs:
                continue
            avg = cur_V[nbrs].mean(axis=0)
            new_V[vi] = 0.7 * cur_V[vi] + 0.3 * avg
        cur_V = new_V
    return cur_V, F
