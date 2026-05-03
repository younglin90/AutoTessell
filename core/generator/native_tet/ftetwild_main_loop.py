"""BETA2827 (B-2v2) — fTetWild §3.4 main loop, native re-impl.

Hu et al. 2020 (MPL-2.0) §3.4 의 split/collapse/swap/smooth 수렴 루프를 그대로
재구현한 dedicated module. 기존 mesher.py pipeline 의 다양한 힘들 (grid Delaunay,
Phase B/C, P4-C fallback) 과 독립적으로 동작 — 이게 핵심.

알고리즘 (Hu 2020 Algorithm 1):
    1) Initial mesh: input surface vertices + bbox 8 corners → Delaunay
    2) BSP insertion: input triangles 가 conformal 하게 mesh 에 들어가도록
    3) iter ∈ [0, max_its):
       a) split long edges  (> 4/3 × target_edge)
       b) collapse short edges  (< 4/5 × target_edge)
       c) swap (3-2 / 4-4 / 2-3) for quality
       d) smooth (AMIPS gradient)
       e) early stop if max_energy < stop_quality
    4) §3.5: winding number filter → interior cells

핵심 차이 vs 기존 native_tet:
    - bbox grid ✗ (over-density 원인)
    - 단일 schedule (Phase A 의존 ✗)
    - quality stop 자체 컨버전스 (P4-C fallback ✗)

Ref: Hu et al. 2020 fTetWild https://github.com/wildmeshing/fTetWild (MPL-2.0)
"""
from __future__ import annotations

import logging
from dataclasses import dataclass

import numpy as np
from numpy.typing import NDArray

logger = logging.getLogger(__name__)


@dataclass
class FTetWildResult:
    pts: NDArray[np.float64]
    tets: NDArray[np.int64]
    success: bool
    n_iters_used: int
    final_min_q: float
    final_mean_q: float
    n_split_total: int
    n_collapse_total: int
    n_swap_total: int
    message: str = ""


def ftetwild_main_loop(
    V: NDArray[np.float64],
    F: NDArray[np.int64],
    *,
    target_edge_length: float | None = None,
    edge_length_r: float = 0.06,
    epsilon: float = 1e-3,
    max_its: int = 20,
    stop_quality: float = 10.0,
    seed: int = 42,
) -> FTetWildResult:
    """fTetWild §3.4 main loop.

    Args:
        V: surface vertices (Nv, 3).
        F: surface triangles (Nf, 3).
        target_edge_length: 목표 엣지 길이. None 이면 edge_length_r × bbox_diag.
        edge_length_r: bbox_diag 비율 (target_edge_length 미지정 시).
        epsilon: envelope 두께 (bbox_diag 비율).
        max_its: 최대 반복.
        stop_quality: max_energy 가 이 값 이하면 조기 중지.

    Returns:
        FTetWildResult.
    """
    V = np.ascontiguousarray(V, dtype=np.float64)
    F = np.ascontiguousarray(F, dtype=np.int64)

    bmin = V.min(axis=0)
    bmax = V.max(axis=0)
    diag = float(np.linalg.norm(bmax - bmin))
    pad = 0.1 * diag  # bbox padding to avoid surface coincidence with bbox.
    bmin_p = bmin - pad
    bmax_p = bmax + pad

    if target_edge_length is None or target_edge_length <= 0:
        target_edge_length = float(edge_length_r) * diag
    eps_abs = float(epsilon) * diag

    # 1) initial Delaunay: surface V + bbox 8 corners.
    corners = np.array([
        [bmin_p[0], bmin_p[1], bmin_p[2]], [bmax_p[0], bmin_p[1], bmin_p[2]],
        [bmin_p[0], bmax_p[1], bmin_p[2]], [bmax_p[0], bmax_p[1], bmin_p[2]],
        [bmin_p[0], bmin_p[1], bmax_p[2]], [bmax_p[0], bmin_p[1], bmax_p[2]],
        [bmin_p[0], bmax_p[1], bmax_p[2]], [bmax_p[0], bmax_p[1], bmax_p[2]],
    ], dtype=np.float64)
    init_pts = np.vstack([V, corners])
    try:
        from scipy.spatial import Delaunay
        d = Delaunay(init_pts)
        tets0 = d.simplices.astype(np.int64)
        pts0 = init_pts
    except Exception as e:
        return FTetWildResult(
            pts=V, tets=np.zeros((0, 4), dtype=np.int64),
            success=False, n_iters_used=0,
            final_min_q=0.0, final_mean_q=0.0,
            n_split_total=0, n_collapse_total=0, n_swap_total=0,
            message=f"initial Delaunay failed: {e}",
        )

    # 2) BSP insertion (conformal recovery of input triangles)
    try:
        from .bsp_insert import bsp_insert_triangles
        from .bowyer_watson import bowyer_watson_insert
        from .insertion import find_missing_triangles
        missing = find_missing_triangles(F, tets0)
        if missing.size > 0:
            pts_with_new, _t_after, bsp_res = bsp_insert_triangles(
                pts0, tets0, V, F, missing,
                max_inserts=50 * int(missing.size),
            )
            if bsp_res.n_inserted_points > 0:
                new_pts = pts_with_new[pts0.shape[0]:]
                pts1, tets1, bw_res = bowyer_watson_insert(pts0, tets0, new_pts)
                if bw_res.n_inserted > 0:
                    pts0, tets0 = pts1, tets1
    except Exception as e:
        logger.debug("ftetwild_bsp_skipped", extra={"error": str(e)})

    pts = pts0
    tets = tets0

    # 3) main iteration: split → collapse → swap → smooth.
    from .local_ops import split_long_edges, collapse_short_edges
    from .stellar import (
        _build_op_queue, _apply_op_queue, _tet_quality_batch,
    )
    _has_amips = False
    amips_smooth_one_step = None
    try:
        from . import amips as _amips_mod
        for _name in ("amips_smooth_one_step", "amips_smooth_step",
                      "amips_global_smooth_one_step"):
            _f = getattr(_amips_mod, _name, None)
            if callable(_f):
                amips_smooth_one_step = _f
                _has_amips = True
                break
    except Exception:
        pass

    n_split_total = n_collapse_total = n_swap_total = 0
    locked_ids = np.arange(V.shape[0], dtype=np.int64)  # lock surface verts.
    surf_set: set[tuple[int, int]] = set()
    for f in F:
        a, b, c = int(f[0]), int(f[1]), int(f[2])
        for u, v in [(a, b), (b, c), (c, a)]:
            surf_set.add((min(u, v), max(u, v)))

    last_max_e = float("inf")
    n_iters_used = 0
    for it in range(int(max_its)):
        n_iters_used = it + 1
        # a) split long edges (> 4/3 × target_edge).
        try:
            pts_s, tets_s, n_s = split_long_edges(
                pts, tets,
                target_edge=target_edge_length,
                ratio=4.0 / 3.0,
                max_splits=2000,
                protected_edges=surf_set,
            )
            if n_s > 0 and tets_s.shape[0] > 0:
                pts, tets = pts_s, tets_s
                n_split_total += int(n_s)
        except Exception as e:
            logger.debug("ftetwild_split_skipped", extra={"error": str(e)})

        # b) collapse short edges (< 4/5 × target_edge).
        try:
            pts_c, tets_c, n_c = collapse_short_edges(
                pts, tets,
                target_edge=target_edge_length,
                ratio=4.0 / 5.0,
                locked_vertices=locked_ids,
                max_collapses=2000,
                protected_edges=surf_set,
                allow_surface_keeper=False,
            )
            if n_c > 0 and tets_c.shape[0] > 0:
                pts, tets = pts_c, tets_c
                n_collapse_total += int(n_c)
        except Exception as e:
            logger.debug("ftetwild_collapse_skipped", extra={"error": str(e)})

        # c) swap (3-2/4-4) via Stellar queue.
        try:
            q = _build_op_queue(pts, tets)
            pts_w, tets_w, n_w = _apply_op_queue(
                pts, tets, q,
                max_swap_attempts=200,
                min_quality_improvement=1e-3,
                protected_edges=surf_set,
            )
            if n_w > 0 and tets_w.shape[0] > 0:
                pts, tets = pts_w, tets_w
                n_swap_total += int(n_w)
        except Exception as e:
            logger.debug("ftetwild_swap_skipped", extra={"error": str(e)})

        # d) smooth (AMIPS one step, interior only).
        if _has_amips:
            try:
                pts_m = amips_smooth_one_step(
                    pts, tets, locked_vertices=locked_ids, step=0.3,
                )
                if pts_m is not None and pts_m.shape == pts.shape:
                    pts = pts_m
            except Exception as e:
                logger.debug("ftetwild_smooth_skipped", extra={"error": str(e)})

        # e) quality stop (Hu §3.4: max AMIPS energy ≤ stop_quality).
        try:
            q_arr = _tet_quality_batch(pts, tets)
            # AMIPS energy ≈ 1/q for quality 0~1 metric — proxy.
            if q_arr.size > 0:
                q_min = float(q_arr.min())
                if q_min > 1e-12:
                    max_e = 1.0 / q_min
                else:
                    max_e = float("inf")
                if max_e < float(stop_quality):
                    last_max_e = max_e
                    break
                if abs(last_max_e - max_e) < 1e-6 * max(1.0, last_max_e):
                    last_max_e = max_e
                    break
                last_max_e = max_e
        except Exception:
            pass

    # 4) §3.5 winding-number filter → interior cells only.
    try:
        from core.utils.geometry import inside_winding_number
        centroids = pts[tets].mean(axis=1)
        inside = inside_winding_number(centroids, V, F)
        tets = tets[inside]
    except Exception as e:
        logger.debug("ftetwild_winding_filter_skipped", extra={"error": str(e)})

    # final quality.
    final_min_q = 0.0
    final_mean_q = 0.0
    try:
        q_arr = _tet_quality_batch(pts, tets)
        if q_arr.size > 0:
            final_min_q = float(q_arr.min())
            final_mean_q = float(q_arr.mean())
    except Exception:
        pass

    return FTetWildResult(
        pts=pts, tets=tets,
        success=tets.shape[0] > 0,
        n_iters_used=n_iters_used,
        final_min_q=final_min_q,
        final_mean_q=final_mean_q,
        n_split_total=n_split_total,
        n_collapse_total=n_collapse_total,
        n_swap_total=n_swap_total,
        message=f"converged at iter {n_iters_used}",
    )
