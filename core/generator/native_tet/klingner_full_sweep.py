"""KLINGNER-FULL / beta2794 — Klingner §4 full topology swap sweep.

Klingner & Shewchuk 2008 §4 "Aggressive Tetrahedral Mesh Improvement" 의
4-op stage cycling 통합 sweep:

    Stage 1: edge_collapse (priority sorted, BETA2785)
    Stage 2: split_long_edges (target_edge adaptive)
    Stage 3: flip_edges_32 + flip_edges_44 (adaptive threshold, BETA2782)
    Stage 4: smooth_amips_multistage (alphas 0.5-4.0)

cycle 단위 monotone guard + plateau early-exit (worst_mq 향상 < 1e-4 시).
self-impl tet 단독 grade A 도달 목표 — 외부 fallback 없는 환경.

기존 분산된 op 들을 **하나의 통합 sweep** 으로 묶어 cross-stage 효과 누적.
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from numpy.typing import NDArray


@dataclass
class FullSweepResult:
    n_cycles_used: int = 0
    pre_min_q: float = 0.0
    post_min_q: float = 0.0
    pre_mean_q: float = 0.0
    post_mean_q: float = 0.0
    n_collapse: int = 0
    n_split: int = 0
    n_flip32: int = 0
    n_flip44: int = 0
    n_smooth_iters: int = 0
    accepted: bool = False
    elapsed_s: float = 0.0
    reason: str = ""


def klingner_full_sweep(
    pts: NDArray[np.float64],
    tets: NDArray[np.int64],
    *,
    n_cycles: int = 4,
    target_edge: float | None = None,
    locked_vertex_ids: NDArray[np.int64] | None = None,
    plateau_eps: float = 1e-4,
    monotone_min_drop: float = 0.020,
) -> tuple[NDArray[np.float64], NDArray[np.int64], FullSweepResult]:
    """Klingner §4 full sweep: collapse → split → flip(3-2,4-4) → smooth.

    Args:
        pts: (N, 3).
        tets: (T, 4).
        n_cycles: 최대 cycle 수 (default 4).
        target_edge: split/collapse target. None → 평균 edge × 1.0.
        locked_vertex_ids: surface vertex IDs (이동/병합 보호).
        plateau_eps: 두 cycle 의 mean_q 차이 < eps 면 break.
        monotone_min_drop: cycle 종료 시 worst_mq drop 허용 한계.

    Returns:
        (new_pts, new_tets, FullSweepResult).
    """
    import time
    t0 = time.perf_counter()

    pts = np.asarray(pts, dtype=np.float64).copy()
    tets = np.asarray(tets, dtype=np.int64).copy()
    n_t = int(tets.shape[0])

    if n_t < 50:
        return pts, tets, FullSweepResult(
            elapsed_s=time.perf_counter() - t0, reason="too_small",
        )

    # quality snapshot.
    from core.generator.native_tet.quality import snapshot as _qs
    pre_q = _qs(pts, tets)
    pre_min = float(pre_q.min_q)
    pre_mean = float(pre_q.mean_q)

    # target_edge 자동 추정.
    if target_edge is None:
        EDGES = np.array([[0,1],[0,2],[0,3],[1,2],[1,3],[2,3]], dtype=np.int64)
        e_idx = tets[:, EDGES]
        e_lens = np.linalg.norm(
            pts[e_idx[..., 1]] - pts[e_idx[..., 0]], axis=-1,
        )
        target_edge = float(np.median(e_lens))

    n_collapse_total = 0
    n_split_total = 0
    n_flip32_total = 0
    n_flip44_total = 0
    n_smooth_iters_total = 0
    cycles_used = 0
    last_mean = pre_mean
    cur_pts = pts
    cur_tets = tets

    try:
        from core.generator.native_tet.local_ops import (
            collapse_short_edges, split_long_edges,
        )
        from core.generator.native_tet.flip import (
            flip_edges_32, flip_edges_44,
        )
        from core.generator.native_tet.amips import smooth_amips_multistage
        from core.generator.native_tet.plane_coverage import _tet_boundary_faces
    except Exception as exc:
        return pts, tets, FullSweepResult(
            elapsed_s=time.perf_counter() - t0,
            reason=f"import_failed: {exc!s:.50}",
        )

    def _boundary_signature(
        points: NDArray[np.float64], cells: NDArray[np.int64],
    ) -> tuple[set[tuple[int, int, int]], float]:
        faces = _tet_boundary_faces(cells)
        keys = {tuple(sorted(face)) for face in faces.tolist()}
        if not keys:
            return keys, 0.0
        tri = np.asarray(points, dtype=np.float64)[faces]
        area = 0.5 * np.linalg.norm(
            np.cross(tri[:, 1] - tri[:, 0], tri[:, 2] - tri[:, 0]), axis=1
        ).sum()
        return keys, float(area)

    def _boundary_preserved(
        before_points: NDArray[np.float64],
        before_cells: NDArray[np.int64],
        candidate_points: NDArray[np.float64],
        candidate_cells: NDArray[np.int64],
    ) -> bool:
        before_keys, before_area = _boundary_signature(before_points, before_cells)
        candidate_keys, candidate_area = _boundary_signature(candidate_points, candidate_cells)
        area_tol = 1e-10 * max(abs(before_area), 1e-30)
        return before_keys == candidate_keys and abs(candidate_area - before_area) <= area_tol

    for c in range(int(n_cycles)):
        cycles_used = c + 1
        cycle_start_pts = cur_pts.copy()
        cycle_start_tets = cur_tets.copy()
        try:
            # Stage 1: collapse short edges (ratio 0.7 보수적).
            new_pts_c, new_tets_c, n_c = collapse_short_edges(
                cur_pts, cur_tets,
                target_edge=float(target_edge),
                ratio=0.7,
                locked_vertices=locked_vertex_ids,
                max_collapses=2000,
            )
            if n_c > 0 and new_tets_c.shape[0] > 50:
                _q = _qs(new_pts_c, new_tets_c)
                if (
                    float(_q.mean_q) >= last_mean * 0.99
                    and _boundary_preserved(cur_pts, cur_tets, new_pts_c, new_tets_c)
                ):
                    cur_pts = new_pts_c
                    cur_tets = new_tets_c
                    n_collapse_total += int(n_c)

            # Stage 2: split long edges (target × 1.4).
            new_pts_s, new_tets_s, n_s = split_long_edges(
                cur_pts, cur_tets,
                target_edge=float(target_edge),
                ratio=1.4, max_splits=2000,
            )
            if n_s > 0 and new_tets_s.shape[0] > 50:
                _q = _qs(new_pts_s, new_tets_s)
                if (
                    float(_q.mean_q) >= last_mean * 0.99
                    and _boundary_preserved(cur_pts, cur_tets, new_pts_s, new_tets_s)
                ):
                    cur_pts = new_pts_s
                    cur_tets = new_tets_s
                    n_split_total += int(n_s)

            # Stage 3: flip 3-2 + 4-4 with adaptive threshold.
            for _thr in (1e-3, 1e-4):
                t32, n32 = flip_edges_32(
                    cur_pts, cur_tets,
                    min_quality_improvement=_thr, max_flips=2000,
                )
                if n32 > 0 and t32.shape[0] > 50:
                    _q = _qs(cur_pts, t32)
                    if (
                        float(_q.mean_q) >= last_mean * 0.99
                        and _boundary_preserved(cur_pts, cur_tets, cur_pts, t32)
                    ):
                        cur_tets = t32
                        n_flip32_total += int(n32)
                t44, n44 = flip_edges_44(
                    cur_pts, cur_tets,
                    min_quality_improvement=_thr, max_flips=2000,
                )
                if n44 > 0 and t44.shape[0] > 50:
                    _q = _qs(cur_pts, t44)
                    if (
                        float(_q.mean_q) >= last_mean * 0.99
                        and _boundary_preserved(cur_pts, cur_tets, cur_pts, t44)
                    ):
                        cur_tets = t44
                        n_flip44_total += int(n44)

            # Stage 4: AMIPS multistage smoothing.
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
                    float(_q.mean_q) >= last_mean * 0.99
                    and _drop <= float(monotone_min_drop)
                    and _boundary_preserved(cur_pts, cur_tets, new_pts_a, cur_tets)
                ):
                    cur_pts = new_pts_a
                    n_smooth_iters_total += 1
            except Exception:
                pass

        except Exception as exc:
            # cycle revert.
            cur_pts = cycle_start_pts
            cur_tets = cycle_start_tets
            break

        # plateau check.
        cur_q = _qs(cur_pts, cur_tets)
        cur_mean = float(cur_q.mean_q)
        if abs(cur_mean - last_mean) < float(plateau_eps):
            last_mean = cur_mean
            break
        last_mean = cur_mean

    # global monotone guard.
    post_q = _qs(cur_pts, cur_tets)
    post_min = float(post_q.min_q)
    post_mean = float(post_q.mean_q)
    accepted = (
        post_mean >= pre_mean
        and (pre_min - post_min) <= float(monotone_min_drop)
    )
    if not accepted:
        cur_pts = pts.copy()
        cur_tets = tets.copy()
        post_min = pre_min
        post_mean = pre_mean

    return cur_pts, cur_tets, FullSweepResult(
        n_cycles_used=cycles_used,
        pre_min_q=pre_min, post_min_q=post_min,
        pre_mean_q=pre_mean, post_mean_q=post_mean,
        n_collapse=n_collapse_total,
        n_split=n_split_total,
        n_flip32=n_flip32_total,
        n_flip44=n_flip44_total,
        n_smooth_iters=n_smooth_iters_total,
        accepted=accepted,
        elapsed_s=time.perf_counter() - t0,
        reason="ok" if accepted else "rejected",
    )
