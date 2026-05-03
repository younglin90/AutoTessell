"""WILDMESH-LOOP / beta2815 — fTetWild progressive improvement loop.

Reference (WildMeshing public C++ source / fTetWild paper §3.4):
    Hu et al. 2020, "Fast Tetrahedral Meshing in the Wild" (SIGGRAPH).
    https://github.com/Yixin-Hu/fTetWild
        src/MeshImprovement.cpp::MeshImprovement_iters() — 본 함수의 reference.

핵심 알고리즘 흐름 (fTetWild §3.4 Algorithm 1):
    1. target_l = edge_length_r × bbox_diag   (default r=0.05).
    2. for it in [0, max_its):
        a. split long edges      (e_len > 4/3 × target_l).
        b. collapse short edges  (e_len < 4/5 × target_l).
        c. swap (3-2, 4-4, 2-3)  (adaptive q gain threshold).
        d. smooth (AMIPS energy, envelope-bounded relocation).
        e. if min_inv_q ≤ stop_quality and Δ < ε  → break.

stop_quality 정의 (WildMesh metric, fTetWild eq.2):
    inv_q = sum(L_i^2) / (12 × (3V)^(2/3))
    inv_q = 1 / Q_klingner   (우리 모듈의 Q_shape 와 역수 관계).
    stop_quality=10 → min Q_klingner ≥ 0.1 (Klingner-grade C 이상).
    stop_quality=8  → min Q_klingner ≥ 0.125 (more strict).

CLAUDE.md 정책:
    외부 라이브러리 (wildmeshing, geogram) 신규 의존 금지.
    수식 + 종료 조건만 추출. 기존 native_tet 모듈 (local_ops, flip, amips, envelope) 재사용.
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from numpy.typing import NDArray


@dataclass
class WildMeshLoopResult:
    """progressive improvement loop 결과."""

    n_iters_used: int = 0
    pre_min_q: float = 0.0
    post_min_q: float = 0.0
    pre_mean_q: float = 0.0
    post_mean_q: float = 0.0
    pre_inv_q_max: float = 0.0     # WildMesh metric (max 1/Q over tets).
    post_inv_q_max: float = 0.0
    n_split_total: int = 0
    n_collapse_total: int = 0
    n_swap_total: int = 0
    n_smooth_iters: int = 0
    converged: bool = False
    early_exit_reason: str = ""
    target_edge_length: float = 0.0
    elapsed_s: float = 0.0


_TET_EDGES = np.array(
    [[0, 1], [0, 2], [0, 3], [1, 2], [1, 3], [2, 3]],
    dtype=np.int64,
)


def _wildmesh_inv_q(pts: NDArray[np.float64], tets: NDArray[np.int64]) -> NDArray[np.float64]:
    """WildMesh metric: inv_q = sum(L_i^2) / (12 × (3V)^(2/3)).

    fTetWild eq.2. regular tet → inv_q ≈ 1, sliver → inv_q → ∞.
    inv_q = 1 / Q_klingner relationship.
    """
    if tets.shape[0] == 0:
        return np.zeros(0, dtype=np.float64)
    a = pts[tets[:, 0]]; b = pts[tets[:, 1]]
    c = pts[tets[:, 2]]; d = pts[tets[:, 3]]
    vol = np.einsum("ij,ij->i", np.cross(b - a, c - a), d - a) / 6.0
    abs_vol = np.abs(vol)
    e_idx = tets[:, _TET_EDGES]
    p0 = pts[e_idx[..., 0]]; p1 = pts[e_idx[..., 1]]
    L_sq = ((p1 - p0) ** 2).sum(axis=-1)
    sum_L_sq = L_sq.sum(axis=1)
    safe = abs_vol > 1e-30
    inv_q = np.full(tets.shape[0], 1e6, dtype=np.float64)
    inv_q[safe] = sum_L_sq[safe] / (12.0 * (3.0 * abs_vol[safe]) ** (2.0 / 3.0))
    # inverted (vol < 0) → marker.
    inv_q[vol <= 0] = 1e6
    return inv_q


def _bbox_diag(pts: NDArray[np.float64]) -> float:
    if pts.shape[0] == 0:
        return 1.0
    bbox = pts.max(axis=0) - pts.min(axis=0)
    return float(np.linalg.norm(bbox))


def wildmesh_improvement_loop(
    pts: NDArray[np.float64],
    tets: NDArray[np.int64],
    *,
    stop_quality: float = 10.0,
    max_its: int = 20,
    edge_length_r: float = 0.05,
    epsilon_rel: float = 1e-3,
    stage: int = 2,
    locked_vertex_ids: NDArray[np.int64] | None = None,
    plateau_eps: float = 1e-4,
    monotone_min_drop: float = 0.030,
) -> tuple[NDArray[np.float64], NDArray[np.int64], WildMeshLoopResult]:
    """fTetWild §3.4 Algorithm 1 progressive improvement.

    Args:
        pts: (N, 3).
        tets: (T, 4).
        stop_quality: WildMesh metric — min Q_klingner ≥ 1/stop_quality.
            10 = grade C (Q ≥ 0.1), 8 = stricter (Q ≥ 0.125), 5 = grade A (Q ≥ 0.20).
        max_its: 최대 iter (fTetWild default 80, 우리 default 20).
        edge_length_r: target edge length factor (× bbox_diag), default 0.05.
        epsilon_rel: envelope ε / bbox_diag.
        stage: 0=skip (no-op), 1=split/collapse only, 2=full (incl. swap+smooth).
        locked_vertex_ids: surface lock.
        plateau_eps: min_q diff < eps → break.
        monotone_min_drop: cycle 별 worst drop limit.

    Returns:
        (new_pts, new_tets, WildMeshLoopResult).
    """
    import time
    t0 = time.perf_counter()

    pts = np.asarray(pts, dtype=np.float64).copy()
    tets = np.asarray(tets, dtype=np.int64).copy()
    n_t = int(tets.shape[0])

    res = WildMeshLoopResult(target_edge_length=0.0)
    if n_t < 50 or stage <= 0:
        res.elapsed_s = time.perf_counter() - t0
        res.early_exit_reason = "no_op" if stage <= 0 else "too_small"
        return pts, tets, res

    # bbox diagonal + target edge length.
    diag = _bbox_diag(pts)
    target_l = float(edge_length_r) * diag
    res.target_edge_length = target_l

    # pre-stats.
    from core.generator.native_tet.quality import snapshot as _qs
    pre_q = _qs(pts, tets)
    pre_min = float(pre_q.min_q)
    pre_mean = float(pre_q.mean_q)
    pre_inv_q = _wildmesh_inv_q(pts, tets)
    pre_inv_q_max = float(pre_inv_q.max())
    res.pre_min_q = pre_min
    res.pre_mean_q = pre_mean
    res.pre_inv_q_max = pre_inv_q_max

    try:
        from core.generator.native_tet.local_ops import (
            collapse_short_edges, split_long_edges,
        )
        from core.generator.native_tet.flip import (
            flip_edges_32, flip_edges_44, flip_faces_23,
        )
        from core.generator.native_tet.amips import smooth_amips_multistage
    except Exception as exc:
        res.elapsed_s = time.perf_counter() - t0
        res.early_exit_reason = f"import_failed: {exc!s:.40}"
        return pts, tets, res

    cur_pts = pts
    cur_tets = tets
    last_min = pre_min
    last_inv_q_max = pre_inv_q_max

    # stop condition (WildMesh metric):
    #   target_inv_q = stop_quality. converged when max(inv_q) ≤ stop_quality.
    target_inv_q = float(stop_quality)

    for it in range(int(max_its)):
        cycle_pts = cur_pts.copy()
        cycle_tets = cur_tets.copy()
        try:
            # Stage 1a: split long edges (>4/3 × target_l, fTetWild §3.4).
            if stage >= 1:
                new_pts_s, new_tets_s, n_s = split_long_edges(
                    cur_pts, cur_tets,
                    target_edge=target_l, ratio=4.0 / 3.0, max_splits=3000,
                )
                if n_s > 0 and new_tets_s.shape[0] > 50:
                    _q = _qs(new_pts_s, new_tets_s)
                    if float(_q.mean_q) >= last_min * 0.95:
                        cur_pts = new_pts_s
                        cur_tets = new_tets_s
                        res.n_split_total += int(n_s)

            # Stage 1b: collapse short edges (<4/5 × target_l).
            if stage >= 1:
                new_pts_c, new_tets_c, n_c = collapse_short_edges(
                    cur_pts, cur_tets,
                    target_edge=target_l, ratio=4.0 / 5.0,
                    locked_vertices=locked_vertex_ids,
                    max_collapses=3000,
                )
                if n_c > 0 and new_tets_c.shape[0] > 50:
                    _q = _qs(new_pts_c, new_tets_c)
                    if float(_q.mean_q) >= last_min * 0.95:
                        cur_pts = new_pts_c
                        cur_tets = new_tets_c
                        res.n_collapse_total += int(n_c)

            # Stage 2a: swap (23, 32, 44 — adaptive thr).
            if stage >= 2:
                # adaptive threshold: lower as min_q approaches stop_quality.
                cur_inv_q = _wildmesh_inv_q(cur_pts, cur_tets)
                cur_max_inv = float(cur_inv_q.max())
                progress = max(0.0, 1.0 - target_inv_q / max(cur_max_inv, 1.0))
                # progress 0 (far) → thr 1e-3 (loose). progress 1 (close) → 1e-5 (strict).
                thr_base = 10 ** (-3 - 2 * progress)

                for fn, sl in [
                    (flip_faces_23, "23"), (flip_edges_32, "32"), (flip_edges_44, "44"),
                ]:
                    new_tets_f, n_f = fn(
                        cur_pts, cur_tets,
                        min_quality_improvement=thr_base,
                        max_flips=2000,
                    )
                    if n_f > 0 and new_tets_f.shape[0] > 50:
                        _q = _qs(cur_pts, new_tets_f)
                        if float(_q.mean_q) >= last_min * 0.95:
                            cur_tets = new_tets_f
                            res.n_swap_total += int(n_f)

            # Stage 2b: smooth (AMIPS multistage, envelope-aware via locked_ids).
            if stage >= 2:
                try:
                    _, new_pts_a = smooth_amips_multistage(
                        cur_pts, cur_tets,
                        locked_vertex_ids=locked_vertex_ids,
                        alphas=(0.5, 1.0, 2.0),
                        n_iter_per=1, step_init=0.1,
                    )
                    _q = _qs(new_pts_a, cur_tets)
                    _drop = pre_min - float(_q.min_q)
                    if (
                        float(_q.mean_q) >= last_min * 0.95
                        and _drop <= float(monotone_min_drop)
                    ):
                        cur_pts = new_pts_a
                        res.n_smooth_iters += 1
                except Exception:
                    pass

        except Exception as exc:
            cur_pts = cycle_pts
            cur_tets = cycle_tets
            res.early_exit_reason = f"cycle_exception: {exc!s:.40}"
            break

        # iteration-end stop check (fTetWild §3.4 termination).
        cur_q = _qs(cur_pts, cur_tets)
        cur_min = float(cur_q.min_q)
        cur_mean = float(cur_q.mean_q)
        cur_inv_q = _wildmesh_inv_q(cur_pts, cur_tets)
        cur_max_inv = float(cur_inv_q.max())
        res.n_iters_used = it + 1

        # convergence: inv_q ≤ stop_quality 또는 plateau.
        if cur_max_inv <= target_inv_q:
            res.converged = True
            res.early_exit_reason = "stop_quality_reached"
            last_min = cur_min
            last_inv_q_max = cur_max_inv
            break
        if abs(cur_min - last_min) < float(plateau_eps):
            res.early_exit_reason = "plateau"
            last_min = cur_min
            last_inv_q_max = cur_max_inv
            break
        last_min = cur_min
        last_inv_q_max = cur_max_inv
    else:
        res.early_exit_reason = "max_its_reached"

    # global monotone guard.
    post_q = _qs(cur_pts, cur_tets)
    post_min = float(post_q.min_q)
    post_mean = float(post_q.mean_q)
    post_inv_q = _wildmesh_inv_q(cur_pts, cur_tets)
    post_inv_q_max = float(post_inv_q.max())
    accepted = (
        post_mean >= pre_mean
        and (pre_min - post_min) <= float(monotone_min_drop)
    )
    if not accepted:
        cur_pts = pts.copy()
        cur_tets = tets.copy()
        post_min = pre_min
        post_mean = pre_mean
        post_inv_q_max = pre_inv_q_max
        res.early_exit_reason = (res.early_exit_reason or "") + "+global_revert"

    res.post_min_q = post_min
    res.post_mean_q = post_mean
    res.post_inv_q_max = post_inv_q_max
    res.elapsed_s = time.perf_counter() - t0
    return cur_pts, cur_tets, res


def parity_check_with_wildmeshing(
    pts: NDArray[np.float64],
    F_surf: NDArray[np.int64],
    *,
    stop_quality: float = 10.0,
    edge_length_r: float = 0.05,
    epsilon: float = 0.001,
    max_its: int = 80,
) -> dict:
    """우리 implementation 과 wildmeshing 라이브러리 결과 parity 비교.

    개발/검증용. wildmeshing 미설치 시 'lib_unavailable' 반환.

    Returns:
        {
            "ours": {"n_pts", "n_tets", "min_q", "mean_q", "inv_q_max"},
            "lib":  {"n_pts", "n_tets", "min_q", "mean_q", "inv_q_max"},
            "match": {"n_tets_ratio", "mean_q_diff", "min_q_diff"},
        }
    """
    out: dict = {"ours": {}, "lib": {}, "match": {}}

    # our run via fTetWild fallback (pytetwild) chained with wildmesh loop.
    try:
        import pytetwild
        v_lib, t_lib = pytetwild.tetrahedralize(
            pts.astype(np.float64), F_surf.astype(np.int32),
            edge_length_fac=edge_length_r,
            epsilon=epsilon, stop_energy=stop_quality,
            num_opt_iter=max_its, quiet=True,
        )
        from core.generator.native_tet.quality import snapshot as _qs
        q_lib = _qs(v_lib.astype(np.float64), t_lib.astype(np.int64))
        inv_q_lib = _wildmesh_inv_q(v_lib.astype(np.float64), t_lib.astype(np.int64))
        out["lib"] = {
            "n_pts": int(v_lib.shape[0]),
            "n_tets": int(t_lib.shape[0]),
            "min_q": float(q_lib.min_q),
            "mean_q": float(q_lib.mean_q),
            "inv_q_max": float(inv_q_lib.max()),
        }
    except ImportError:
        out["lib"] = {"error": "pytetwild_unavailable"}
        return out
    except Exception as exc:
        out["lib"] = {"error": str(exc)[:80]}
        return out

    # our pipeline: scipy Delaunay → wildmesh_improvement_loop.
    try:
        from scipy.spatial import Delaunay
        d = Delaunay(pts)
        tets_init = d.simplices.astype(np.int64)
        cur_pts, cur_tets, res = wildmesh_improvement_loop(
            pts.astype(np.float64), tets_init,
            stop_quality=stop_quality,
            edge_length_r=edge_length_r,
            max_its=max_its,
        )
        from core.generator.native_tet.quality import snapshot as _qs
        q_ours = _qs(cur_pts, cur_tets)
        inv_q_ours = _wildmesh_inv_q(cur_pts, cur_tets)
        out["ours"] = {
            "n_pts": int(cur_pts.shape[0]),
            "n_tets": int(cur_tets.shape[0]),
            "min_q": float(q_ours.min_q),
            "mean_q": float(q_ours.mean_q),
            "inv_q_max": float(inv_q_ours.max()),
        }
    except Exception as exc:
        out["ours"] = {"error": str(exc)[:80]}
        return out

    # parity metrics.
    if "n_tets" in out["ours"] and "n_tets" in out["lib"]:
        out["match"] = {
            "n_tets_ratio": out["ours"]["n_tets"] / max(out["lib"]["n_tets"], 1),
            "mean_q_diff": abs(out["ours"]["mean_q"] - out["lib"]["mean_q"]),
            "min_q_diff": abs(out["ours"]["min_q"] - out["lib"]["min_q"]),
            "inv_q_max_diff": abs(
                out["ours"]["inv_q_max"] - out["lib"]["inv_q_max"]
            ),
        }
    return out
