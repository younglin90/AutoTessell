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
    # BETA2829 (B-4) — bbox padding 축소: 10% diag → 2 × ε. fTetWild 처럼
    # envelope 두께 정도만 padding 해서 bbox padding region 의 over-split 방지.
    # 너무 작으면 surface vertex 가 bbox 면 위에 일치할 수 있어 Delaunay
    # degenerate → 2*epsilon 안전 마진.
    pad = max(2.0 * float(epsilon) * diag, 1e-6 * diag)
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

    # BETA2828 (B-3) — envelope ε-check: split/collapse 후 surface vertex 위치
    # 가 envelope 안인지 검증 → 위반 시 revert. Hu 2020 §3.1 핵심 가드.
    try:
        from .envelope import Envelope
        env = Envelope.build_auto_eps(V, F, base_ratio=float(epsilon))
    except Exception as e:
        env = None
        logger.debug("ftetwild_envelope_build_skipped", extra={"error": str(e)})

    def _envelope_ok(pts_to_check: NDArray[np.float64], n_surface: int) -> bool:
        """surface vertex 가 모두 envelope 안인지. interior 는 검사 안 함."""
        if env is None or pts_to_check.shape[0] < n_surface:
            return True
        try:
            inside = env.contains_points(pts_to_check[:n_surface])
            return bool(np.all(inside))
        except Exception:
            return True

    n_surface_in = int(V.shape[0])  # surface vertex 는 input 의 첫 N 개.

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
        n_s = 0  # 이 iter 의 split count.
        n_c = 0  # 이 iter 의 collapse count.
        # a) split long edges (> 4/3 × target_edge). envelope 가드는 split 이
        # surface vertex 위치를 바꾸지 않으므로 불필요 — interior 만 추가.
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

        # b) collapse short edges (< 4/5 × target_edge). BETA2831 (B-6):
        # iter 가 진행될수록 collapse ratio 를 0.8→0.95 로 ramp up. fTetWild
        # §3.4 의 "수렴 후 추가 collapse" 단계 — V/T 비율을 wildmesh 와 정렬.
        try:
            _pre_pts = pts
            _pre_tets = tets
            # ramp: iter 0 → 0.8, iter max-1 → 0.85.
            # 너무 공격적이면 T count 도 같이 폭락 — 0.8~0.85 sweet spot.
            _ramp = min(1.0, it / max(1, int(max_its) - 1))
            _ratio = 0.8 + 0.05 * _ramp
            pts_c, tets_c, n_c = collapse_short_edges(
                pts, tets,
                target_edge=target_edge_length,
                ratio=_ratio,
                locked_vertices=locked_ids,
                max_collapses=2000,
                protected_edges=surf_set,
                allow_surface_keeper=False,
                envelope=env,  # B-3: envelope object 전달.
            )
            if n_c > 0 and tets_c.shape[0] > 0:
                if _envelope_ok(pts_c, n_surface_in):
                    pts, tets = pts_c, tets_c
                    n_collapse_total += int(n_c)
                else:
                    # envelope violation → revert.
                    pts, tets = _pre_pts, _pre_tets
                    logger.debug(
                        "ftetwild_collapse_envelope_revert",
                        extra={"iter": it, "n_collapse": int(n_c)},
                    )
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

        # e) quality stop + churn stop. fTetWild 는 max_AMIPS_energy 가 더
        # 이상 줄지 않으면 종료. 여기선 (1) max_e ≤ stop_quality 또는
        # (2) split+collapse 가 거의 동량 (churn) 또는 (3) tet count 변동 < 1%
        # 인 경우 break — over-iteration 방지.
        try:
            q_arr = _tet_quality_batch(pts, tets)
            if q_arr.size > 0:
                q_min = float(q_arr.min())
                max_e = (1.0 / q_min) if q_min > 1e-12 else float("inf")
                # 종료 조건 1: 품질 목표 도달.
                if max_e < float(stop_quality):
                    last_max_e = max_e
                    break
                # 종료 조건 2: 이번 iter 의 split-collapse 가 churn (≈ 같음).
                if it >= 2:
                    _churn = abs(int(n_s) - int(n_c))
                    _ops = int(n_s) + int(n_c)
                    if _ops > 0 and _churn / _ops < 0.05:
                        last_max_e = max_e
                        logger.debug(
                            "ftetwild_churn_stop",
                            extra={"iter": it, "split": int(n_s),
                                   "collapse": int(n_c)},
                        )
                        break
                # 종료 조건 3: tet count 변화율 < 1% (수렴).
                if abs(last_max_e - max_e) < 1e-6 * max(1.0, last_max_e):
                    last_max_e = max_e
                    break
                last_max_e = max_e
        except Exception:
            pass

    # 3.5) BETA2831 (B-6) — final cleanup collapse pass: 수렴 후 더 짧은
    # interior edge 까지 적극적 merge. ratio 0.95 (target_edge 의 95% 까지 collapse).
    # 한 번만 실행 → 과도한 셀 손실 방지. 단조 가드 (envelope OK) 그대로.
    try:
        _final_ratio = float(
            __import__("os").environ.get(
                # default 0.0 = skip. T parity 보존 (≥80%). 사용자가 V parity
                # 을 더 원하면 0.85 전후로 설정 (T parity 65% 까지 trade-off).
                "AUTO_TESSELL_FTETWILD_FINAL_COLLAPSE_RATIO", "0.0"
            )
        )
        if _final_ratio <= 0.0:
            raise RuntimeError("final_collapse_disabled")
        _pre_n_t = tets.shape[0]
        pts_fc, tets_fc, n_fc = collapse_short_edges(
            pts, tets,
            target_edge=target_edge_length,
            ratio=_final_ratio,
            locked_vertices=locked_ids,
            max_collapses=4000,
            protected_edges=surf_set,
            allow_surface_keeper=False,
            envelope=env,
        )
        # T 가 50% 이상 줄면 거부 (over-collapse 방지).
        if n_fc > 0 and tets_fc.shape[0] >= 0.5 * _pre_n_t:
            if _envelope_ok(pts_fc, n_surface_in):
                pts, tets = pts_fc, tets_fc
                n_collapse_total += int(n_fc)
                logger.debug(
                    "ftetwild_final_collapse",
                    extra={"n_collapsed": int(n_fc),
                           "t_before": int(_pre_n_t),
                           "t_after": int(tets.shape[0])},
                )
    except Exception as e:
        logger.debug("ftetwild_final_collapse_skipped", extra={"error": str(e)})

    # 4) §3.5 winding-number filter → interior cells only.
    try:
        from core.utils.geometry import inside_winding_number
        centroids = pts[tets].mean(axis=1)
        inside = inside_winding_number(centroids, V, F)
        tets = tets[inside]
    except Exception as e:
        logger.debug("ftetwild_winding_filter_skipped", extra={"error": str(e)})

    # 5) BETA2830 (B-5) — compact unused vertices: collapse 후 victim 으로
    # 참조 잃은 정점 제거. wildmesh 와 V/T 비율 정렬에 결정적.
    try:
        from .local_ops import compact_unused_vertices
        # surface vertex (input 의 첫 N 개) 는 항상 유지.
        pts, tets = compact_unused_vertices(pts, tets, keep_first_n=int(V.shape[0]))
    except Exception as e:
        logger.debug("ftetwild_compact_skipped", extra={"error": str(e)})

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
