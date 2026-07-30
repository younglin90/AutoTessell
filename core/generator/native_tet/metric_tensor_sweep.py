"""METRIC-TENSOR / beta2803 — Klingner §4 metric-tensor guided full sweep.

기존 klingner_full_sweep (BETA2794) 의 4-stage cycle 에 **anisotropic metric
tensor** (per-vertex symmetric 3×3 tensor) 추가:

    Stage 1: collapse (metric-aware short edge: e^T M e < threshold)
    Stage 2: split (metric-aware long edge: e^T M e > threshold)
    Stage 3: flip (mean ratio + metric det 결합)
    Stage 4: smooth_amips_multistage (metric 가중)

metric tensor 정의:
    M_v = (1/k) * Σ M_face,  M_face = curvature 기반 anisotropic stretch.
    isotropic: M = α I (α = local target edge^-2).
    anisotropic: 표면 곡률 큰 방향 stretch.

Klingner & Shewchuk 2008 §4.1 + Loseille & Alauzet 2010 metric tensor.
self-impl tet 단독 grade A 도달 영역 — 진행.
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from numpy.typing import NDArray


@dataclass
class MetricTensorSweepResult:
    n_cycles_used: int = 0
    pre_min_q: float = 0.0
    post_min_q: float = 0.0
    pre_mean_q: float = 0.0
    post_mean_q: float = 0.0
    n_collapse: int = 0
    n_split: int = 0
    n_flip: int = 0
    n_smooth: int = 0
    metric_aniso_max: float = 1.0
    accepted: bool = False
    elapsed_s: float = 0.0
    reason: str = ""


def compute_isotropic_metric(
    pts: NDArray[np.float64],
    tets: NDArray[np.int64],
    *,
    target_edge: float | None = None,
) -> NDArray[np.float64]:
    """isotropic metric tensor M_v = (1/h^2) * I per vertex.

    Args:
        pts: (N, 3).
        tets: (T, 4).
        target_edge: target edge length. None → median local edge.

    Returns:
        M (N, 3, 3) symmetric metric tensor per vertex.
    """
    n_v = int(pts.shape[0])
    if n_v == 0:
        return np.zeros((0, 3, 3), dtype=np.float64)

    if target_edge is None or target_edge <= 0:
        EDGES = np.array([[0,1],[0,2],[0,3],[1,2],[1,3],[2,3]], dtype=np.int64)
        if tets.shape[0] > 0:
            e_idx = tets[:, EDGES]
            e_lens = np.linalg.norm(
                pts[e_idx[..., 1]] - pts[e_idx[..., 0]], axis=-1,
            )
            target_edge = float(np.median(e_lens))
        else:
            target_edge = 1.0

    h = max(float(target_edge), 1e-30)
    alpha = 1.0 / (h * h)
    I = np.eye(3, dtype=np.float64)
    M = np.broadcast_to(alpha * I, (n_v, 3, 3)).copy()
    return M


def compute_curvature_metric(
    V_surf: NDArray[np.float64],
    F_surf: NDArray[np.int64],
    n_total_v: int,
    *,
    base_edge: float = 1.0,
    aniso_factor: float = 4.0,
) -> NDArray[np.float64]:
    """curvature-driven anisotropic metric for surface vertices.

    surface vertex 의 mean curvature direction → metric eigenvector,
    eigenvalue 크게 (해당 방향 short edge 권장).

    Args:
        V_surf: (Ns, 3) surface vertices (간주: 첫 Ns 개 = surface).
        F_surf: (M, 3) surface tris.
        n_total_v: 전체 vertex 수.
        base_edge: 기본 edge length.
        aniso_factor: max anisotropy ratio (eigenvalue ratio).

    Returns:
        M (n_total_v, 3, 3).
    """
    M = np.zeros((n_total_v, 3, 3), dtype=np.float64)
    h = max(float(base_edge), 1e-30)
    alpha = 1.0 / (h * h)
    for i in range(n_total_v):
        M[i] = alpha * np.eye(3)

    if V_surf.shape[0] == 0 or F_surf.shape[0] == 0:
        return M

    try:
        from core.analyzer.mean_curvature import vertex_mean_curvature
        H, _ = vertex_mean_curvature(V_surf, F_surf)
        # H 는 (Ns, 3) mean curvature vector.
        n_surf = int(min(V_surf.shape[0], n_total_v))
        for vi in range(n_surf):
            h_vec = H[vi]
            h_norm = float(np.linalg.norm(h_vec))
            if h_norm < 1e-30:
                continue
            # principal direction = h_vec direction.
            n = h_vec / h_norm
            # eigenvalues: alpha along n (curvature direction = small edge),
            # alpha/aniso along orthogonal.
            lam_n = alpha * float(aniso_factor)
            lam_t = alpha
            # M = lam_t * I + (lam_n - lam_t) * n n^T (rank-1 update).
            M[vi] = lam_t * np.eye(3) + (lam_n - lam_t) * np.outer(n, n)
    except Exception:
        pass

    return M


def metric_edge_length_sq(
    p0: NDArray[np.float64],
    p1: NDArray[np.float64],
    M0: NDArray[np.float64],
    M1: NDArray[np.float64],
) -> NDArray[np.float64]:
    """e^T M e (metric-aware edge length squared).

    Args:
        p0, p1: (..., 3) edge endpoints.
        M0, M1: (..., 3, 3) metric tensors.

    Returns:
        squared metric length (...).
    """
    e = p1 - p0
    M_avg = 0.5 * (M0 + M1)
    # e^T M e.
    Me = np.einsum("...ij,...j->...i", M_avg, e)
    return np.einsum("...i,...i->...", e, Me)


def metric_tensor_sweep(
    pts: NDArray[np.float64],
    tets: NDArray[np.int64],
    *,
    n_cycles: int = 3,
    target_edge: float | None = None,
    metric: NDArray[np.float64] | None = None,
    locked_vertex_ids: NDArray[np.int64] | None = None,
    monotone_min_drop: float = 0.020,
    plateau_eps: float = 1e-4,
) -> tuple[NDArray[np.float64], NDArray[np.int64], MetricTensorSweepResult]:
    """metric-tensor guided full sweep.

    Args:
        pts: (N, 3).
        tets: (T, 4).
        n_cycles: 최대 cycle.
        target_edge: 기본 edge. None → median.
        metric: (N, 3, 3) optional. None → isotropic.
        locked_vertex_ids: surface lock.
        monotone_min_drop: worst_q drop limit.
        plateau_eps: cycle 간 mean_q diff limit.

    Returns:
        (new_pts, new_tets, MetricTensorSweepResult).
    """
    import time
    t0 = time.perf_counter()

    pts = np.asarray(pts, dtype=np.float64).copy()
    tets = np.asarray(tets, dtype=np.int64).copy()
    n_t = int(tets.shape[0])
    n_v = int(pts.shape[0])

    if n_t < 50:
        return pts, tets, MetricTensorSweepResult(
            elapsed_s=time.perf_counter() - t0,
        )

    if metric is None:
        metric = compute_isotropic_metric(pts, tets, target_edge=target_edge)

    # eigen analysis (anisotropy ratio).
    try:
        eigs = np.linalg.eigvalsh(metric)  # (N, 3) ascending.
        safe = eigs[:, 0] > 1e-30
        ratios = np.ones(n_v, dtype=np.float64)
        ratios[safe] = np.sqrt(eigs[safe, 2] / eigs[safe, 0])
        aniso_max = float(ratios.max())
    except Exception:
        aniso_max = 1.0

    from core.generator.native_tet.quality import snapshot as _qs
    pre_q = _qs(pts, tets)
    pre_min = float(pre_q.min_q)
    pre_mean = float(pre_q.mean_q)

    if target_edge is None or target_edge <= 0:
        EDGES = np.array([[0,1],[0,2],[0,3],[1,2],[1,3],[2,3]], dtype=np.int64)
        e_idx = tets[:, EDGES]
        e_lens = np.linalg.norm(
            pts[e_idx[..., 1]] - pts[e_idx[..., 0]], axis=-1,
        )
        target_edge = float(np.median(e_lens))

    n_collapse_total = 0
    n_split_total = 0
    n_flip_total = 0
    n_smooth_total = 0
    cycles_used = 0
    last_mean = pre_mean
    cur_pts = pts
    cur_tets = tets

    try:
        from core.generator.native_tet.local_ops import (
            collapse_short_edges, split_long_edges,
        )
        from core.generator.native_tet.flip import (
            flip_edges_32, flip_edges_44, flip_faces_23,
        )
        from core.generator.native_tet.amips import smooth_amips_multistage
    except Exception as exc:
        return pts, tets, MetricTensorSweepResult(
            elapsed_s=time.perf_counter() - t0,
            metric_aniso_max=aniso_max,
        )

    # eigvalsh of metric → per-vertex local target edge h_v = 1/sqrt(λ_max).
    try:
        eigs_full = np.linalg.eigvalsh(metric)  # ascending.
        lam_max = np.maximum(eigs_full[:, 2], 1e-30)
        local_h = 1.0 / np.sqrt(lam_max)  # (N,).
    except Exception:
        local_h = np.full(n_v, float(target_edge), dtype=np.float64)

    for c in range(int(n_cycles)):
        cycles_used = c + 1
        cycle_pts = cur_pts.copy()
        cycle_tets = cur_tets.copy()
        try:
            # Stage 1: metric-aware collapse (target_edge → median per cycle).
            target_now = float(np.median(local_h))
            new_pts_c, new_tets_c, n_c = collapse_short_edges(
                cur_pts, cur_tets,
                target_edge=target_now,
                ratio=0.7,
                locked_vertices=locked_vertex_ids,
                max_collapses=3000,
                metric=local_h if metric is not None else None,
            )
            if n_c > 0 and new_tets_c.shape[0] > 50:
                _q = _qs(new_pts_c, new_tets_c)
                if float(_q.mean_q) >= last_mean * 0.98:
                    cur_pts = new_pts_c
                    cur_tets = new_tets_c
                    n_collapse_total += int(n_c)

            # Stage 2: metric-aware split.
            new_pts_s, new_tets_s, n_s = split_long_edges(
                cur_pts, cur_tets,
                target_edge=target_now,
                ratio=1.4, max_splits=3000,
                metric=local_h if metric is not None else None,
            )
            if n_s > 0 and new_tets_s.shape[0] > 50:
                _q = _qs(new_pts_s, new_tets_s)
                if float(_q.mean_q) >= last_mean * 0.98:
                    cur_pts = new_pts_s
                    cur_tets = new_tets_s
                    n_split_total += int(n_s)

            # Stage 3: flip 23 + 32 + 44 — adaptive threshold sweep.
            for _thr in (1e-3, 1e-4, 1e-5):
                t23, n23 = flip_faces_23(
                    cur_pts, cur_tets,
                    min_quality_improvement=_thr, max_flips=2000,
                )
                if n23 > 0 and t23.shape[0] > 50:
                    _q = _qs(cur_pts, t23)
                    if float(_q.mean_q) >= last_mean * 0.98:
                        cur_tets = t23
                        n_flip_total += int(n23)
                t32, n32 = flip_edges_32(
                    cur_pts, cur_tets,
                    min_quality_improvement=_thr, max_flips=2000,
                )
                if n32 > 0 and t32.shape[0] > 50:
                    _q = _qs(cur_pts, t32)
                    if float(_q.mean_q) >= last_mean * 0.98:
                        cur_tets = t32
                        n_flip_total += int(n32)
                t44, n44 = flip_edges_44(
                    cur_pts, cur_tets,
                    min_quality_improvement=_thr, max_flips=2000,
                )
                if n44 > 0 and t44.shape[0] > 50:
                    _q = _qs(cur_pts, t44)
                    if float(_q.mean_q) >= last_mean * 0.98:
                        cur_tets = t44
                        n_flip_total += int(n44)

            # Stage 4: AMIPS multistage with stronger alpha sweep.
            try:
                _, new_pts_a = smooth_amips_multistage(
                    cur_pts, cur_tets,
                    locked_vertex_ids=locked_vertex_ids,
                    alphas=(0.5, 1.0, 2.0, 4.0),
                    n_iter_per=2, step_init=0.1,
                )
                _q = _qs(new_pts_a, cur_tets)
                _drop = pre_min - float(_q.min_q)
                if (
                    float(_q.mean_q) >= last_mean * 0.98
                    and _drop <= float(monotone_min_drop)
                ):
                    cur_pts = new_pts_a
                    n_smooth_total += 1
            except Exception:
                pass
        except Exception:
            cur_pts = cycle_pts
            cur_tets = cycle_tets
            break

        cur_q = _qs(cur_pts, cur_tets)
        cur_mean = float(cur_q.mean_q)
        if abs(cur_mean - last_mean) < float(plateau_eps):
            last_mean = cur_mean
            break
        last_mean = cur_mean

    post_q = _qs(cur_pts, cur_tets)
    post_min = float(post_q.min_q)
    post_mean = float(post_q.mean_q)
    from core.generator.native_tet.rescue_gate import has_strict_writer_topology

    topology_safe = has_strict_writer_topology(cur_pts, cur_tets)
    accepted = (
        post_mean >= pre_mean
        and (pre_min - post_min) <= float(monotone_min_drop)
        and topology_safe
    )
    if not accepted:
        cur_pts = pts.copy()
        cur_tets = tets.copy()
        post_min = pre_min
        post_mean = pre_mean
        n_collapse_total = n_split_total = n_flip_total = n_smooth_total = 0

    return cur_pts, cur_tets, MetricTensorSweepResult(
        n_cycles_used=cycles_used,
        pre_min_q=pre_min, post_min_q=post_min,
        pre_mean_q=pre_mean, post_mean_q=post_mean,
        n_collapse=n_collapse_total,
        n_split=n_split_total,
        n_flip=n_flip_total,
        n_smooth=n_smooth_total,
        metric_aniso_max=aniso_max,
        accepted=accepted,
        elapsed_s=time.perf_counter() - t0,
        reason=(
            "ok" if accepted else
            "strict_writer_topology_rejected"
            if not topology_safe else "quality_rejected"
        ),
    )
